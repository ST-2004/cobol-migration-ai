output "ws_api_id" {
  value = aws_apigatewayv2_api.ws.id
}

output "ws_api_execution_arn" {
  value = aws_apigatewayv2_api.ws.execution_arn
}

# wss://<id>.execute-api.<region>.amazonaws.com/<stage>
output "ws_endpoint" {
  value = "${aws_apigatewayv2_api.ws.api_endpoint}/${aws_apigatewayv2_stage.ws_default.name}"
}

# https endpoint used by migrate Lambda to push tokens via management API
output "ws_management_endpoint" {
  value = "https://${aws_apigatewayv2_api.ws.id}.execute-api.${var.aws_region}.amazonaws.com/${aws_apigatewayv2_stage.ws_default.name}"
}
