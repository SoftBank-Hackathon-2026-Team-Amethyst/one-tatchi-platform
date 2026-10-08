terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

# 관리 계정 자격증명으로 실행한다: AWS_PROFILE=mgmt
provider "aws" {
  region = "ap-northeast-2"

  allowed_account_ids = [local.management_account_id]

  default_tags {
    tags = {
      Project   = "one-tatchi"
      ManagedBy = "terraform"
      Stack     = "org"
    }
  }
}
