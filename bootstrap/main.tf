# 맨 처음 한 번만 로컬에서 apply한다. 이후 변경은 PR → GHA로만 반영한다.
# 만드는 것: Terraform state 버킷, 감사 로그 버킷, GHA OIDC 역할.
# destroy 워크플로는 이 스택을 건드리지 않는다.

terraform {
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # 첫 apply는 이 블록을 주석 처리하고 로컬 state로 실행한 뒤,
  # terraform init -migrate-state -backend-config="bucket=<TF_STATE_BUCKET>" 으로 옮긴다.
  backend "s3" {
    key          = "bootstrap.tfstate"
    region       = "ap-northeast-2"
    use_lockfile = true
    encrypt      = true
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = { Project = var.project, ManagedBy = "terraform", Stack = "bootstrap" }
  }
}

data "aws_caller_identity" "current" {}

locals {
  bucket_prefix = "${var.project}-${data.aws_caller_identity.current.account_id}"
}

# ---------- Terraform state ----------
resource "aws_s3_bucket" "state" {
  bucket = "${local.bucket_prefix}-tfstate"
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ---------- 감사 로그: 배포 파이프라인 작업 기록, 수정·삭제 불가 ----------
resource "aws_s3_bucket" "audit_log" {
  bucket              = "${local.bucket_prefix}-audit-log"
  object_lock_enabled = true
}

resource "aws_s3_bucket_versioning" "audit_log" {
  bucket = aws_s3_bucket.audit_log.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_object_lock_configuration" "audit_log" {
  bucket = aws_s3_bucket.audit_log.id
  rule {
    default_retention {
      mode = var.audit_log_lock_mode
      days = var.audit_log_retention_days
    }
  }
  depends_on = [aws_s3_bucket_versioning.audit_log]
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit_log" {
  bucket = aws_s3_bucket.audit_log.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "audit_log" {
  bucket                  = aws_s3_bucket.audit_log.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ---------- GHA가 AWS에 들어올 권한 (OIDC) ----------
module "ci_identity" {
  source = "../modules/ci_identity/aws"

  name_prefix         = var.project
  oidc_subject_prefix = var.github_oidc_subject_prefix
  deploy_environments = var.deploy_environments
  state_bucket_arn    = aws_s3_bucket.state.arn

  # demo-app 자신의 워크플로가 아니라 이 레포의 재사용 워크플로(태그 · main)에서만 역할을 받는다.
  allowed_workflow_refs = var.allowed_workflow_refs
}
