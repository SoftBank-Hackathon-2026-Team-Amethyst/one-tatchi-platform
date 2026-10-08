output "secret_store_name" {
  description = "서비스가 시크릿을 가져올 때 참조하는 ClusterSecretStore 이름"
  value       = "cloud-secrets"
  depends_on  = [helm_release.secret_store]
}

output "ingress_class" {
  value      = "alb"
  depends_on = [helm_release.lb_controller]
}
