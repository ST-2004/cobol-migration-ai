# Phase 0 outputs
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

# Phase 1 outputs
output "api_endpoint" {
  description = "HTTP API base URL — written to frontend/.env.local as VITE_API_URL"
  value       = module.api_gateway.invoke_url
}

# Phase 2 outputs
output "ws_endpoint" {
  description = "WebSocket API endpoint (wss://...) — written to frontend/.env.local as VITE_WS_URL"
  value       = module.websocket.ws_endpoint
}

output "connections_table_name" {
  description = "DynamoDB table for WebSocket connections"
  value       = module.dynamodb.connections_table_name
}

output "state_machine_arn" {
  description = "Step Functions Express state machine ARN"
  value       = module.step_functions.state_machine_arn
}
