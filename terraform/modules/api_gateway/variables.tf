variable "prefix" {
  description = "Resource name prefix (e.g. cobol-mig-dev)"
  type        = string
}

variable "parse_cobol_invoke_arn" {
  description = "Invoke ARN of the parse_cobol Lambda"
  type        = string
}

variable "parse_cobol_function_name" {
  description = "Name of the parse_cobol Lambda function"
  type        = string
}

variable "trigger_migrate_invoke_arn" {
  description = "Invoke ARN of the trigger_migrate Lambda"
  type        = string
}

variable "trigger_migrate_function_name" {
  description = "Name of the trigger_migrate Lambda function"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
}

variable "account_id" {
  description = "AWS account ID"
  type        = string
}

variable "env_local_path" {
  description = "Absolute path to frontend/.env.local for local-exec write"
  type        = string
}

variable "ws_endpoint" {
  description = "WebSocket endpoint URL (wss://...) to write to .env.local"
  type        = string
  default     = ""
}
