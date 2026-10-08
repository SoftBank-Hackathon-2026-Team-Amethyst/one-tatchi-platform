# apply 후 이 값들을 GitHub 레포 Variables에 등록한다 (README 참고).
output "github_variables" {
  value = {
    AWS_REGION          = var.region
    AWS_PLAN_ROLE_ARN   = module.ci_identity.plan_role_arn
    AWS_DEPLOY_ROLE_ARN = module.ci_identity.deploy_role_arn
    TF_STATE_BUCKET     = aws_s3_bucket.state.bucket
    AUDIT_LOG_BUCKET    = aws_s3_bucket.audit_log.bucket
  }
}
