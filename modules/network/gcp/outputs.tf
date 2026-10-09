output "network_id" {
  description = "GCP VPC resource ID."
  value       = google_compute_network.this.id
}

output "network_cidr" {
  description = "Node address pool supplied through cidr; GCP VPC has no single CIDR."
  value       = var.cidr
}

output "private_subnet_ids" {
  description = "Regional node subnet IDs; wait for NAT before creating private nodes."
  value       = [google_compute_subnetwork.nodes.id]
  depends_on  = [google_compute_router_nat.this]
}

output "public_subnet_ids" {
  description = "Empty: GCP does not have a separate public subnet category."
  value       = []
}

output "pods_range_name" {
  description = "GKE pod secondary range name."
  value       = "${var.name}-pods"
}

output "services_range_name" {
  description = "GKE service secondary range name."
  value       = "${var.name}-services"
}
