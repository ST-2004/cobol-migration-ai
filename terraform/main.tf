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

# Phase 1: parse_cobol Lambda + HTTP API Gateway

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

module "api_gateway" {
  source                    = "./modules/api_gateway"
  prefix                    = local.prefix
  parse_cobol_invoke_arn    = module.lambda_parse_cobol.invoke_arn
  parse_cobol_function_name = module.lambda_parse_cobol.function_name
  aws_region                = var.aws_region
  account_id                = var.account_id
  env_local_path            = "${path.root}/../frontend/.env.local"
}
