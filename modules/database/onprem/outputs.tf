output "host" {
  value = "${kubernetes_service_v1.this.metadata[0].name}.${var.namespace}.svc.cluster.local"
}

output "port" {
  value = 5432
}

output "database_name" {
  value = var.database_name
}

output "credentials_secret_id" {
  description = "username/password가 든 k8s Secret 이름 (cloud-secrets로 가져온다)"
  value       = kubernetes_secret_v1.credentials.metadata[0].name
  depends_on  = [kubernetes_stateful_set_v1.this]
}
