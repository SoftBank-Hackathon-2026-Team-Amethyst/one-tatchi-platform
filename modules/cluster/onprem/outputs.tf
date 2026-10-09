output "cluster_name" {
  value = var.name
}

output "endpoint" {
  value = "https://127.0.0.1:${var.api_port}"
}

output "kube_context" {
  description = "kubectl · helm 컨텍스트. 인증정보는 onpremctl이 메모리에서 공급한다"
  value       = "k3d-${var.name}"
}
