terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    # Values supplied via backend.hcl — never hardcode here
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project = "cobol-migration"
      Env     = var.env
    }
  }
}

locals {
  prefix = "${var.project_prefix}-${var.env}"
}

module "kms" {
  source     = "./modules/kms"
  prefix     = local.prefix
  aws_region = var.aws_region
  account_id = var.account_id
}

module "iam" {
  source     = "./modules/iam"
  prefix     = local.prefix
  account_id = var.account_id
  aws_region = var.aws_region
}

module "s3" {
  source      = "./modules/s3"
  prefix      = local.prefix
  kms_key_arn = module.kms.key_arn
}

module "dynamodb" {
  source      = "./modules/dynamodb"
  prefix      = local.prefix
  kms_key_arn = module.kms.key_arn
}

# ─── Phase 1: parse_cobol Lambda ────────────────────────────────────────────

module "lambda_parse_cobol" {
  source              = "./modules/lambda"
  prefix              = local.prefix
  function_name       = "parse-cobol"
  source_dir          = "${path.root}/../lambdas/parse_cobol"
  memory_size         = 256
  timeout             = 30
  execution_role_arn  = module.iam.lambda_execution_role_arn
  execution_role_name = module.iam.lambda_execution_role_name

  environment_variables = {
    JOBS_TABLE   = module.dynamodb.jobs_table_name
    FILES_BUCKET = module.s3.files_bucket_name
  }

  extra_policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "${module.s3.files_bucket_arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem"]
        Resource = module.dynamodb.jobs_table_arn
      }
    ]
  })
}

# ─── Phase 2: WebSocket + migrate pipeline ───────────────────────────────────

module "lambda_ws_connect" {
  source              = "./modules/lambda"
  prefix              = local.prefix
  function_name       = "ws-connect"
  source_dir          = "${path.root}/../lambdas/ws_connect"
  memory_size         = 128
  timeout             = 10
  execution_role_arn  = module.iam.lambda_execution_role_arn
  execution_role_name = module.iam.lambda_execution_role_name

  environment_variables = {
    CONNECTIONS_TABLE = module.dynamodb.connections_table_name
  }

  extra_policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["dynamodb:PutItem"]
      Resource = module.dynamodb.connections_table_arn
    }]
  })
}

module "lambda_ws_disconnect" {
  source              = "./modules/lambda"
  prefix              = local.prefix
  function_name       = "ws-disconnect"
  source_dir          = "${path.root}/../lambdas/ws_disconnect"
  memory_size         = 128
  timeout             = 10
  execution_role_arn  = module.iam.lambda_execution_role_arn
  execution_role_name = module.iam.lambda_execution_role_name

  environment_variables = {
    CONNECTIONS_TABLE = module.dynamodb.connections_table_name
  }

  extra_policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["dynamodb:DeleteItem"]
      Resource = module.dynamodb.connections_table_arn
    }]
  })
}

module "websocket" {
  source                      = "./modules/websocket"
  prefix                      = local.prefix
  aws_region                  = var.aws_region
  account_id                  = var.account_id
  ws_connect_function_name    = module.lambda_ws_connect.function_name
  ws_connect_invoke_arn       = module.lambda_ws_connect.invoke_arn
  ws_disconnect_function_name = module.lambda_ws_disconnect.function_name
  ws_disconnect_invoke_arn    = module.lambda_ws_disconnect.invoke_arn
}

module "lambda_migrate" {
  source              = "./modules/lambda"
  prefix              = local.prefix
  function_name       = "migrate"
  source_dir          = "${path.root}/../lambdas/migrate"
  memory_size         = 512
  timeout             = 300
  execution_role_arn  = module.iam.lambda_execution_role_arn
  execution_role_name = module.iam.lambda_execution_role_name

  environment_variables = {
    JOBS_TABLE        = module.dynamodb.jobs_table_name
    FILES_BUCKET      = module.s3.files_bucket_name
    WS_ENDPOINT       = module.websocket.ws_management_endpoint
    BEDROCK_MODEL_ID  = var.bedrock_model_id
    CONNECTIONS_TABLE = module.dynamodb.connections_table_name
  }

  extra_policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = "${module.s3.files_bucket_arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:Query"]
        Resource = [
          module.dynamodb.jobs_table_arn,
          module.dynamodb.connections_table_arn,
          "${module.dynamodb.connections_table_arn}/index/*",
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
        Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/*"
      },
      {
        Effect   = "Allow"
        Action   = ["execute-api:ManageConnections"]
        Resource = "${module.websocket.ws_api_execution_arn}/*"
      }
    ]
  })
}

module "lambda_review_migration" {
  source              = "./modules/lambda"
  prefix              = local.prefix
  function_name       = "review-migration"
  source_dir          = "${path.root}/../lambdas/review_migration"
  memory_size         = 512
  timeout             = 300
  execution_role_arn  = module.iam.lambda_execution_role_arn
  execution_role_name = module.iam.lambda_execution_role_name

  environment_variables = {
    JOBS_TABLE       = module.dynamodb.jobs_table_name
    FILES_BUCKET     = module.s3.files_bucket_name
    WS_ENDPOINT      = module.websocket.ws_management_endpoint
    BEDROCK_MODEL_ID = var.bedrock_model_id
  }

  extra_policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject"]
        Resource = "${module.s3.files_bucket_arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:Query"]
        Resource = module.dynamodb.jobs_table_arn
      },
      {
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
        Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/*"
      },
      {
        Effect   = "Allow"
        Action   = ["execute-api:ManageConnections"]
        Resource = "${module.websocket.ws_api_execution_arn}/*"
      }
    ]
  })
}

module "step_functions" {
  source                = "./modules/step_functions"
  prefix                = local.prefix
  aws_region            = var.aws_region
  account_id            = var.account_id
  migrate_function_arn  = module.lambda_migrate.function_arn
  review_function_arn   = module.lambda_review_migration.function_arn
}

module "lambda_trigger_migrate" {
  source              = "./modules/lambda"
  prefix              = local.prefix
  function_name       = "trigger-migrate"
  source_dir          = "${path.root}/../lambdas/trigger_migrate"
  memory_size         = 128
  timeout             = 30
  execution_role_arn  = module.iam.lambda_execution_role_arn
  execution_role_name = module.iam.lambda_execution_role_name

  environment_variables = {
    JOBS_TABLE        = module.dynamodb.jobs_table_name
    CONNECTIONS_TABLE = module.dynamodb.connections_table_name
    STATE_MACHINE_ARN = module.step_functions.state_machine_arn
  }

  extra_policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["dynamodb:Query", "dynamodb:GetItem"]
        Resource = [
          module.dynamodb.jobs_table_arn,
          module.dynamodb.connections_table_arn,
          "${module.dynamodb.connections_table_arn}/index/*",
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["states:StartExecution"]
        Resource = module.step_functions.state_machine_arn
      }
    ]
  })
}

module "api_gateway" {
  source                        = "./modules/api_gateway"
  prefix                        = local.prefix
  parse_cobol_invoke_arn        = module.lambda_parse_cobol.invoke_arn
  parse_cobol_function_name     = module.lambda_parse_cobol.function_name
  trigger_migrate_invoke_arn    = module.lambda_trigger_migrate.invoke_arn
  trigger_migrate_function_name = module.lambda_trigger_migrate.function_name
  aws_region                    = var.aws_region
  account_id                    = var.account_id
  env_local_path                = "${path.root}/../frontend/.env.local"
  ws_endpoint                   = module.websocket.ws_endpoint
}
