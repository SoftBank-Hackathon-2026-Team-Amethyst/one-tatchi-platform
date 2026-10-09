output "secret_store_name" {
  value      = "cloud-secrets"
  depends_on = [helm_release.secret_store]
}
output "ingress_class" {
  description = "GKE built-in controller; use kubernetes.io/ingress.class annotation"
  value       = "gce"
}
