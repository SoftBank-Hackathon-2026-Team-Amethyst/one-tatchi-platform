output "plan_identity" {
  description = "인프라 계획을 실행할 CI 주체 식별자 (AWS에서는 IAM 역할 ARN)"
  value       = aws_iam_role.plan.arn
}

output "deploy_identity" {
  description = "인프라 반영과 배포를 실행할 CI 주체 식별자 (AWS에서는 IAM 역할 ARN)"
  value       = aws_iam_role.deploy.arn
}

output "plan_role_arn" {
  description = "plan_identity의 호환 출력"
  value       = aws_iam_role.plan.arn
}

output "deploy_role_arn" {
  description = "deploy_identity의 호환 출력"
  value       = aws_iam_role.deploy.arn
}
