locals {
  full_name = "${var.prefix}-${var.function_name}"
  zip_path  = "${path.root}/dist/${var.function_name}.zip"
}

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = var.source_dir
  output_path = local.zip_path
}

resource "aws_lambda_function" "this" {
  function_name    = local.full_name
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  handler          = var.handler
  runtime          = "python3.12"
  architectures    = ["arm64"]
  memory_size      = var.memory_size
  timeout          = var.timeout
  role             = var.execution_role_arn

  dynamic "environment" {
    for_each = length(var.environment_variables) > 0 ? [1] : []
    content {
      variables = var.environment_variables
    }
  }
}

resource "aws_iam_role_policy" "extra" {
  count  = var.extra_policy_json != "" ? 1 : 0
  name   = "${local.full_name}-extra-policy"
  role   = var.execution_role_name
  policy = var.extra_policy_json
}
