output "secret_ids" {
  description = "시크릿 이름 → 클라우드 시크릿 ID"
  value       = { for name, secret in aws_secretsmanager_secret.this : name => secret.arn }
}
