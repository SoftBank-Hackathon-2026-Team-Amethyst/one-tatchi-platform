mock_provider "google" {}

variables {
  project_id          = "test-project"
  name                = "one-tatchi"
  network_id          = "projects/test-project/global/networks/one-tatchi"
  subnet_ids          = ["projects/test-project/regions/asia-northeast3/subnetworks/one-tatchi-nodes"]
  pods_range_name     = "one-tatchi-pods"
  services_range_name = "one-tatchi-services"
}

run "three_nodes_in_two_zones" {
  command = plan
  assert {
    condition     = sum([for pool in google_container_node_pool.this : pool.initial_node_count]) == 3 && length(google_container_node_pool.this) == 2
    error_message = "Three nodes must be created in total, not three per zone."
  }
  assert {
    condition     = alltrue([for pool in google_container_node_pool.this : length(pool.node_locations) == 1]) && sum([for pool in google_container_node_pool.this : pool.autoscaling[0].max_node_count]) == 3
    error_message = "Each pool must stay in its assigned zone and total scaling limit must be three."
  }
  assert {
    condition     = google_container_cluster.this.private_cluster_config[0].enable_private_nodes && !google_container_cluster.this.private_cluster_config[0].enable_private_endpoint
    error_message = "Nodes must be private while the API remains reachable by hosted runners."
  }
  assert {
    condition     = google_container_cluster.this.workload_identity_config[0].workload_pool == "test-project.svc.id.goog" && google_container_cluster.this.ip_allocation_policy[0].cluster_secondary_range_name == var.pods_range_name
    error_message = "Workload Identity and network module ranges must be wired."
  }
}

run "reject_inverted_node_counts" {
  command = plan
  variables {
    node_count = { min = 4, desired = 3, max = 3 }
  }
  expect_failures = [var.node_count]
}

run "reject_foreign_zone" {
  command = plan
  variables {
    node_locations = ["us-central1-a", "asia-northeast3-b"]
  }
  expect_failures = [var.node_locations]
}
