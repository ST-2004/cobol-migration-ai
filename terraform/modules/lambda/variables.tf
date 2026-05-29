variable "prefix" {
  description = "Resource name prefix (e.g. cobol-mig-dev)"
  type        = string
}

variable "function_name" {
  description = "Short name for the Lambda function (appended to prefix)"
  type        = string
}

variable "source_dir" {
  description = "Absolute path to the Lambda source directory containing handler.py"
  type        = string
}

variable "handler" {
  description = "Lambda handler in module.function format"
  type        = string
  default     = "handler.handler"
}

variable "memory_size" {
  description = "Lambda memory in MB"
  type        = number
  default     = 256
}

variable "timeout" {
  description = "Lambda timeout in seconds"
  type        = number
  default     = 30
}

variable "execution_role_arn" {
  description = "IAM role ARN for Lambda execution"
  type        = string
}

variable "execution_role_name" {
  description = "IAM role name for attaching additional policies"
  type        = string
}

variable "environment_variables" {
  description = "Environment variables for the Lambda function"
  type        = map(string)
  default     = {}
}

variable "extra_policy_json" {
  description = "Optional additional IAM policy JSON to attach to the execution role"
  type        = string
  default     = ""
}
