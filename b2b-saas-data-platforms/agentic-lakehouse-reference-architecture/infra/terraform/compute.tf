# The agent runs as a Lambda function behind an HTTP API with a JWT authoriser (Cognito).
# Identity and role come from the token's claims, never from the request body.

locals {
  name              = "${var.project}-${var.environment}"
  bedrock_model_arn = startswith(var.bedrock_model_id, "eu.") || startswith(var.bedrock_model_id, "us.") ? "arn:aws:bedrock:${var.region}:${data.aws_caller_identity.current.account_id}:inference-profile/${var.bedrock_model_id}" : "arn:aws:bedrock:${var.region}::foundation-model/${var.bedrock_model_id}"
}

data "aws_caller_identity" "current" {}

data "archive_file" "agent" {
  type        = "zip"
  source_dir  = "${path.module}/../../src"
  output_path = "${path.module}/build/agent.zip"
}

resource "aws_cloudwatch_log_group" "agent" {
  name              = "/aws/lambda/${local.name}-agent"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.lake.arn
}

resource "aws_iam_role" "agent" {
  name = "${local.name}-agent"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

# Least privilege: read gold only, query through one workgroup, call one model, write own logs and approvals.
resource "aws_iam_role_policy" "agent" {
  name = "${local.name}-agent"
  role = aws_iam_role.agent.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Sid = "ReadGold", Effect = "Allow", Action = ["s3:GetObject", "s3:ListBucket"],
      Resource = [aws_s3_bucket.lake.arn, "${aws_s3_bucket.lake.arn}/gold/*"] },
      { Sid = "AthenaResults", Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:GetBucketLocation"],
      Resource = [aws_s3_bucket.lake.arn, "${aws_s3_bucket.lake.arn}/athena-results/*"] },
      { Sid = "Athena", Effect = "Allow", Action = ["athena:StartQueryExecution", "athena:GetQueryExecution", "athena:GetQueryResults"],
      Resource = aws_athena_workgroup.agent.arn },
      { Sid = "Catalog", Effect = "Allow", Action = ["glue:GetTable", "glue:GetTables", "glue:GetDatabase", "glue:GetPartitions"],
        Resource = [
          "arn:aws:glue:${var.region}:${data.aws_caller_identity.current.account_id}:catalog",
          "arn:aws:glue:${var.region}:${data.aws_caller_identity.current.account_id}:database/${aws_glue_catalog_database.gold.name}",
          "arn:aws:glue:${var.region}:${data.aws_caller_identity.current.account_id}:table/${aws_glue_catalog_database.gold.name}/*",
      ] },
      # the Converse API is authorised by the InvokeModel actions
      { Sid = "Model", Effect = "Allow", Action = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
      Resource = [local.bedrock_model_arn, "arn:aws:bedrock:*::foundation-model/anthropic.*"] },
      { Sid = "Approvals", Effect = "Allow", Action = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:Query"],
      Resource = aws_dynamodb_table.approvals.arn },
      { Sid = "Kms", Effect = "Allow", Action = ["kms:Decrypt", "kms:GenerateDataKey"], Resource = aws_kms_key.lake.arn },
      { Sid = "Logs", Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.agent.arn}:*" },
    ]
  })
}

resource "aws_lambda_function" "agent" {
  function_name    = "${local.name}-agent"
  role             = aws_iam_role.agent.arn
  runtime          = "python3.12"
  handler          = "agentlake.lambda_handler.handler"
  filename         = data.archive_file.agent.output_path
  source_code_hash = data.archive_file.agent.output_base64sha256
  timeout          = 30
  memory_size      = 1024
  # dependencies (pandas, scikit-learn, jsonschema) come from a Lambda layer built in CI; omitted here

  environment {
    variables = {
      PLANNER          = "bedrock"
      BEDROCK_MODEL_ID = var.bedrock_model_id
      LAKE_BUCKET      = aws_s3_bucket.lake.bucket
      ATHENA_WORKGROUP = aws_athena_workgroup.agent.name
      GLUE_DATABASE    = aws_glue_catalog_database.gold.name
      APPROVALS_TABLE  = aws_dynamodb_table.approvals.name
      MAX_STEPS        = "6"
    }
  }

  tracing_config {
    mode = "Active"
  }

  depends_on = [aws_cloudwatch_log_group.agent]
}

resource "aws_cognito_user_pool" "users" {
  name = "${local.name}-users"
  schema {
    name                = "role"
    attribute_data_type = "String"
    mutable             = true
    string_attribute_constraints {
      min_length = 4
      max_length = 32
    }
  }
  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_numbers   = true
    require_symbols   = true
    require_uppercase = true
  }
}

resource "aws_cognito_user_pool_client" "app" {
  name            = "${local.name}-app"
  user_pool_id    = aws_cognito_user_pool.users.id
  generate_secret = false
}

resource "aws_apigatewayv2_api" "agent" {
  name          = "${local.name}-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_authorizer" "jwt" {
  api_id           = aws_apigatewayv2_api.agent.id
  name             = "cognito"
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  jwt_configuration {
    audience = [aws_cognito_user_pool_client.app.id]
    issuer   = "https://cognito-idp.${var.region}.amazonaws.com/${aws_cognito_user_pool.users.id}"
  }
}

resource "aws_apigatewayv2_integration" "agent" {
  api_id                 = aws_apigatewayv2_api.agent.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.agent.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "ask" {
  api_id             = aws_apigatewayv2_api.agent.id
  route_key          = "POST /api/agent"
  target             = "integrations/${aws_apigatewayv2_integration.agent.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt.id
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.agent.id
  name        = "$default"
  auto_deploy = true
  default_route_settings {
    throttling_burst_limit = 20
    throttling_rate_limit  = 10
  }
}

resource "aws_lambda_permission" "api" {
  statement_id  = "AllowApiGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.agent.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.agent.execution_arn}/*/*"
}
