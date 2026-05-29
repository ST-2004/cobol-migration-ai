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
  source         = "./modules/kms"
  prefix         = local.prefix
  aws_region     = var.aws_region
  account_id     = var.account_id
}

module "iam" {
  source     = "./modules/iam"
  prefix     = local.prefix
  account_id = var.account_id
  aws_region = var.aws_region
}

module "s3" {
  source  = "./modules/s3"
  prefix  = local.prefix
  kms_key_arn = module.kms.key_arn
}

module "dynamodb" {
  source      = "./modules/dynamodb"
  prefix      = local.prefix
  kms_key_arn = module.kms.key_arn
}
