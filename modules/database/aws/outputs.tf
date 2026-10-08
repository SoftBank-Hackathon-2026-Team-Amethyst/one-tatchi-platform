output "host" {
  value = aws_db_instance.this.address
}

output "port" {
  value = aws_db_instance.this.port
}

output "database_name" {
  value = aws_db_instance.this.db_name
}

output "credentials_secret_id" {
  description = "username/password JSON이 든 시크릿 식별자"
  value       = aws_db_instance.this.master_user_secret[0].secret_arn
}
