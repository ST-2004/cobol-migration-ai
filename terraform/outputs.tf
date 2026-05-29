# Phase 0 outputs — extended in later phases

output "files_bucket_name" {
  description = "S3 bucket for COBOL source files and migration outputs"
  value       = module.s3.files_bucket_name
}

output "jobs_table_name" {
  description = "DynamoDB table for migration job state"
  value       = module.dynamodb.jobs_table_name
}

output "lambda_execution_role_arn" {
  description = "Base IAM role ARN for Lambda functions"
  value       = module.iam.lambda_execution_role_arn
}

output "kms_key_arn" {
  description = "KMS CMK ARN for S3 and DynamoDB encryption"
  value       = module.kms.key_arn
}
