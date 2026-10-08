# 서비스 도메인의 존과 인증서 (T2). 존은 오래 유지해야 해서(지우면 상위 DNS 위임이 깨진다) bootstrap에 둔다.
# domain_name을 비우면 만들지 않는다.

variable "domain_name" {
  description = "서비스 도메인. 운영 <도메인>, 테스트 yolo.<도메인>. 비우면 DNS · 인증서를 만들지 않는다"
  type        = string
  default     = "onetatchi.soulee.dev"
}

module "dns" {
  source = "../modules/dns/aws"
  count  = var.domain_name == "" ? 0 : 1

  domain_name = var.domain_name
}

# 상위 DNS(soulee.dev, Cloudflare)에 NS 레코드로 등록한다
output "dns_name_servers" {
  value = one(module.dns[*].name_servers)
}

output "dns_zone_id" {
  value = one(module.dns[*].zone_id)
}
