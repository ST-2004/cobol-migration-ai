output "lambda_execution_role_arn" {
  value = aws_iam_role.lambda_execution.arn
}

output "lambda_execution_role_name" {
  value = aws_iam_role.lambda_execution.name
}

output "sfn_execution_role_arn" {
  value = aws_iam_role.sfn_execution.arn
}
