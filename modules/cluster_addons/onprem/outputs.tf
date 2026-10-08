output "secret_store_name" {
  description = "서비스가 시크릿을 가져올 때 참조하는 ClusterSecretStore 이름"
  value       = "cloud-secrets"
  depends_on  = [helm_release.secret_store]
}

output "secret_namespace" {
  description = "시크릿 원본 네임스페이스 (database · secret 모듈 입력)"
  value       = kubernetes_namespace_v1.secrets.metadata[0].name
}

output "ingress_class" {
  description = "온프레미스는 Ingress 대신 터널이 Service로 바로 연결한다"
  value       = "cloudflare-tunnel"
  depends_on  = [kubernetes_deployment_v1.cloudflared]
}

output "public_url_commands" {
  description = "터널 이름 → Quick Tunnel 주소 확인 명령. Named Tunnel이면 Cloudflare 대시보드에서 정한 도메인을 쓴다"
  value = {
    for name, d in kubernetes_deployment_v1.cloudflared :
    name => "kubectl -n cloudflared logs deploy/${d.metadata[0].name} | grep -o 'https://[a-z0-9-]*\\.trycloudflare\\.com' | tail -1"
  }
}

# v1.1.0 호환: tunnel(하나)을 쓸 때의 확인 명령. tunnels만 쓰면 null
output "public_url_command" {
  value = var.tunnel == null ? null : "kubectl -n cloudflared logs deploy/cloudflared | grep -o 'https://[a-z0-9-]*\\.trycloudflare\\.com' | tail -1"
}
