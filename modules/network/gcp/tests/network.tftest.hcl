mock_provider "google" {}

variables {
  name = "test-network"
}

run "default_ranges" {
  command = plan

  assert {
    condition     = google_compute_subnetwork.nodes.ip_cidr_range == "10.0.0.0/20" && length(google_compute_subnetwork.nodes.secondary_ip_range) == 2
    error_message = "The node subnet and two GKE secondary ranges must be configured."
  }
  assert {
    condition     = google_compute_subnetwork.nodes.private_ip_google_access && !google_compute_network.this.auto_create_subnetworks && length(output.public_subnet_ids) == 0
    error_message = "Private Google access and custom subnet configuration are required."
  }
}

run "reject_node_pod_overlap" {
  command = plan
  variables {
    pods_cidr = "10.0.0.0/16"
  }
  expect_failures = [google_compute_subnetwork.nodes]
}

run "reject_secondary_overlap" {
  command = plan
  variables {
    services_cidr = "10.100.0.0/20"
  }
  expect_failures = [google_compute_subnetwork.nodes]
}
