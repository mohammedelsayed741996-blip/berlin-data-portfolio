variable "project" {
  description = "Name prefix for all resources."
  type        = string
  default     = "agentic-lakehouse"
}

variable "environment" {
  description = "Deployment stage, for example dev or prod."
  type        = string
  default     = "dev"
}

variable "region" {
  description = "AWS region. Frankfurt keeps data in the EU."
  type        = string
  default     = "eu-central-1"
}

variable "bedrock_model_id" {
  description = "Bedrock model or inference profile the planner may call, for example an EU cross-region inference profile for Claude."
  type        = string
  default     = "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"
}

variable "log_retention_days" {
  description = "How long CloudWatch keeps logs and traces."
  type        = number
  default     = 30
}

variable "approval_retention_days" {
  description = "How long decided approval requests are kept before DynamoDB expires them."
  type        = number
  default     = 365
}
