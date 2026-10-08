output "cluster_name" {
  value = var.name
}

output "endpoint" {
  value = data.external.kubeconfig.result.endpoint
}

output "ca_certificate" {
  description = "base64로 인코딩된 클러스터 CA"
  value       = data.external.kubeconfig.result.ca_certificate
}

output "client_certificate" {
  description = "base64로 인코딩된 관리자 클라이언트 인증서 (k3d 전용)"
  value       = data.external.kubeconfig.result.client_certificate
  sensitive   = true
}

output "client_key" {
  description = "base64로 인코딩된 관리자 클라이언트 키 (k3d 전용)"
  value       = data.external.kubeconfig.result.client_key
  sensitive   = true
}

output "kube_context" {
  description = "kubectl · helm에서 쓰는 컨텍스트 이름"
  value       = "k3d-${var.name}"
}
