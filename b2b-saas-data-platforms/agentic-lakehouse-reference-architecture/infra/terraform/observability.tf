# Alarms on the signals the evaluation cares about: errors, latency and guard blocks.
# Guard blocks are counted from the structured span logs the Lambda writes.

resource "aws_cloudwatch_log_metric_filter" "guard_blocks" {
  name           = "${local.name}-guard-blocks"
  log_group_name = aws_cloudwatch_log_group.agent.name
  pattern        = "{ $.span = \"tool.call\" && $.allowed IS FALSE }"
  metric_transformation {
    name      = "GuardBlocks"
    namespace = "AgenticLakehouse"
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "guard_blocks" {
  alarm_name          = "${local.name}-guard-blocks-spike"
  alarm_description   = "Many blocked tool calls: a misbehaving model, a prompt-injection campaign or a broken release."
  namespace           = "AgenticLakehouse"
  metric_name         = "GuardBlocks"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 20
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
}

resource "aws_cloudwatch_metric_alarm" "errors" {
  alarm_name          = "${local.name}-agent-errors"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.agent.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 5
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
}

resource "aws_cloudwatch_metric_alarm" "latency" {
  alarm_name          = "${local.name}-agent-p95-latency"
  namespace           = "AWS/Lambda"
  metric_name         = "Duration"
  dimensions          = { FunctionName = aws_lambda_function.agent.function_name }
  extended_statistic  = "p95"
  period              = 300
  evaluation_periods  = 3
  threshold           = 15000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
}
