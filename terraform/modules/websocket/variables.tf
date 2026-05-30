variable "prefix" {
  description = "Resource name prefix (e.g. cobol-mig-dev)"
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

variable "ws_connect_function_name" {
  description = "Name of the ws_connect Lambda"
  type        = string
}

variable "ws_connect_invoke_arn" {
  description = "Invoke ARN of the ws_connect Lambda"
  type        = string
}

variable "ws_disconnect_function_name" {
  description = "Name of the ws_disconnect Lambda"
  type        = string
}

variable "ws_disconnect_invoke_arn" {
  description = "Invoke ARN of the ws_disconnect Lambda"
  type        = string
}
