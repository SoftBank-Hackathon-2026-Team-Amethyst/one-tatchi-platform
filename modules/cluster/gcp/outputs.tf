output "cluster_name" {
  description = "GKE cluster name; waits for all node pools."
  value       = google_container_cluster.this.name
  depends_on  = [google_container_node_pool.this]
}

output "endpoint" {
  description = "HTTPS Kubernetes API address for Helm and kubectl."
  value       = "https://${google_container_cluster.this.endpoint}"
}

output "ca_certificate" {
  description = "Base64-encoded cluster CA, matching the common contract."
  value       = google_container_cluster.this.master_auth[0].cluster_ca_certificate
}

output "node_service_account" {
  description = "Dedicated node identity email; not the identity of application pods."
  value       = google_service_account.nodes.email
}
