locals {
  # Build list of non-empty Lambda ARNs for IAM policy
  lambda_arns = compact([
    var.migrate_function_arn,
    var.review_function_arn,
    var.verify_function_arn,
    var.compare_graphs_function_arn,
    var.generate_commands_function_arn,
  ])
}

resource "aws_iam_role" "sfn" {
  name = "${var.prefix}-sfn-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "states.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "sfn_lambda_invoke" {
  name = "${var.prefix}-sfn-lambda-invoke"
  role = aws_iam_role.sfn.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = local.lambda_arns
    }]
  })
}

# ASL: Migrate → ReviewMigration → Done
# Phases 3 & 4 will add Verify, CompareGraphs, GenerateCommands states
resource "aws_sfn_state_machine" "pipeline" {
  name     = "${var.prefix}-pipeline"
  role_arn = aws_iam_role.sfn.arn
  type     = "EXPRESS"

  definition = jsonencode({
    Comment = "COBOL Migration Pipeline — Migrate + Review"
    StartAt = "Migrate"
    States = {
      Migrate = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = var.migrate_function_arn
          "Payload.$"  = "$"
        }
        Retry = [{
          ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException"]
          IntervalSeconds = 2
          MaxAttempts     = 3
          BackoffRate     = 2
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "FailedState"
          ResultPath  = "$.error"
        }]
        ResultSelector = {
          "job_id.$"        = "$.Payload.job_id"
          "created_at.$"    = "$.Payload.created_at"
          "connection_id.$" = "$.Payload.connection_id"
          "status.$"        = "$.Payload.status"
        }
        ResultPath = "$"
        Next       = "ReviewMigration"
      }

      ReviewMigration = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = var.review_function_arn
          "Payload.$"  = "$"
        }
        Retry = [{
          ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException"]
          IntervalSeconds = 2
          MaxAttempts     = 3
          BackoffRate     = 2
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          Next        = "FailedState"
          ResultPath  = "$.error"
        }]
        ResultSelector = {
          "job_id.$"     = "$.Payload.job_id"
          "created_at.$" = "$.Payload.created_at"
          "status.$"     = "$.Payload.status"
        }
        ResultPath = "$"
        Next       = "Done"
      }

      Done = {
        Type = "Succeed"
      }

      FailedState = {
        Type  = "Fail"
        Error = "MigrationFailed"
        Cause = "Pipeline step failed — see $.error for details"
      }
    }
  })
}
