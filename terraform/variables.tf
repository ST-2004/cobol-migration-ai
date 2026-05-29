variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "project_prefix" {
  description = "Prefix for all AWS resource names"
  type        = string
  default     = "cobol-mig"
}

variable "account_id" {
  description = "AWS account ID"
  type        = string
}

variable "env" {
  description = "Deployment environment"
  type        = string
  default     = "dev"
}

variable "bedrock_model_id" {
  description = "Amazon Bedrock model ID for Claude"
  type        = string
  default     = "anthropic.claude-sonnet-4-5"
}

variable "alert_email" {
  description = "Email address for CloudWatch alarms"
  type        = string
  default     = ""
}

variable "cognito_allowed_domains" {
  description = "Allowed email domains for Cognito sign-up"
  type        = list(string)
  default     = []
}
