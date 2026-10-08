output "repository_urls" {
  description = "저장소 이름 → 이미지 push 주소"
  value       = { for name, repo in aws_ecr_repository.this : name => repo.repository_url }
}
