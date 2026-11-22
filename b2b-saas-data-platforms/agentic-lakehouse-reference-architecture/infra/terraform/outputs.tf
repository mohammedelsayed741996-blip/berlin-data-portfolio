output "api_endpoint" {
  description = "Base URL of the agent API."
  value       = aws_apigatewayv2_api.agent.api_endpoint
}

output "lake_bucket" {
  description = "S3 bucket holding bronze, silver and gold."
  value       = aws_s3_bucket.lake.bucket
}

output "athena_workgroup" {
  value = aws_athena_workgroup.agent.name
}

output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.users.id
}
