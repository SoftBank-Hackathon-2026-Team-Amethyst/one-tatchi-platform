output "domain_name" {
  value = var.domain_name
}

output "zone_id" {
  description = "external-dns가 레코드를 쓸 존"
  value       = aws_route53_zone.this.zone_id
}

output "name_servers" {
  description = "상위 DNS에 NS 레코드로 등록할 값"
  value       = aws_route53_zone.this.name_servers
}

output "certificate_arn" {
  description = "<도메인>, *.<도메인> 인증서 (검증 완료 후)"
  value       = aws_acm_certificate_validation.this.certificate_arn
}
