# 온프레미스는 별도 레지스트리를 두지 않고 GHCR을 쓴다. 저장소는 처음 push할 때 생긴다.
output "repository_urls" {
  description = "저장소 이름 → 이미지 push 주소"
  value       = { for name in var.repositories : name => "ghcr.io/${lower(var.owner)}/${name}" }
}
