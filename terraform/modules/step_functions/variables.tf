variable "prefix" {
  description = "Resource name prefix"
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

variable "migrate_function_arn" {
  description = "ARN of the migrate Lambda"
  type        = string
}

# Placeholders for future phases — included in IAM now to avoid policy updates later
variable "verify_function_arn" {
  description = "ARN of the verify Lambda (Phase 3)"
  type        = string
  default     = ""
}

variable "compare_graphs_function_arn" {
  description = "ARN of the compare_graphs Lambda (Phase 3)"
  type        = string
  default     = ""
}

variable "generate_commands_function_arn" {
  description = "ARN of the generate_commands Lambda (Phase 4)"
  type        = string
  default     = ""
}

variable "review_function_arn" {
  description = "ARN of the review_migration Lambda"
  type        = string
  default     = ""
}
