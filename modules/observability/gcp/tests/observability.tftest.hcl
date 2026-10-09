mock_provider "google" {}
variables {
  project_id   = "test-project"
  cluster_name = "one-tatchi-gcp"
}
run "cluster_scoped_metrics" {
  command = plan
  assert {
    condition     = length(jsondecode(google_monitoring_dashboard.this.dashboard_json).gridLayout.widgets) == 3 && strcontains(google_monitoring_dashboard.this.dashboard_json, "one-tatchi-gcp") && strcontains(google_monitoring_dashboard.this.dashboard_json, "cpu/core_usage_time") && strcontains(google_monitoring_dashboard.this.dashboard_json, "memory/used_bytes")
    error_message = "The dashboard must show cluster-scoped CPU and memory plus its logs link."
  }
}
