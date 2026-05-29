output "api_id" {
  description = "ID of the HTTP API"
  value       = aws_apigatewayv2_api.this.id
}

output "invoke_url" {
  description = "Base URL for API invocation (e.g. https://xxx.execute-api.us-east-1.amazonaws.com)"
  value       = aws_apigatewayv2_api.this.api_endpoint
}

output "execution_arn" {
  description = "Execution ARN for Lambda permission source_arn"
  value       = aws_apigatewayv2_api.this.execution_arn
}
