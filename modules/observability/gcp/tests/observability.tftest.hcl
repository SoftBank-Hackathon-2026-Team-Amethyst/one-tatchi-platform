mock_provider "google" {}
variables {
  project_id   = "test-project"
  cluster_name = "one-tatchi-gcp"
}
run "eks_grafana_only" {
  command = plan
  variables {
    grafana_eks_oidc_issuer = "https://oidc.eks.ap-northeast-2.amazonaws.com/id/EXAMPLE"
  }
  assert {
    condition     = length(google_iam_workload_identity_pool.grafana[0].display_name) <= 32
    error_message = "GCP Workload Identity Pool display names cannot exceed 32 characters."
  }
  assert {
    condition     = google_project_iam_member.grafana[0].role == "roles/monitoring.viewer" && google_iam_workload_identity_pool_provider.grafana[0].attribute_condition == "assertion.sub == 'system:serviceaccount:monitoring:grafana'"
    error_message = "Only the central Grafana Kubernetes identity may read Monitoring."
  }
}
run "cluster_scoped_metrics" {
  command = plan
  assert {
    condition     = length(jsondecode(google_monitoring_dashboard.this.dashboard_json).gridLayout.widgets) == 3 && strcontains(google_monitoring_dashboard.this.dashboard_json, "one-tatchi-gcp") && strcontains(google_monitoring_dashboard.this.dashboard_json, "cpu/core_usage_time") && strcontains(google_monitoring_dashboard.this.dashboard_json, "memory/used_bytes")
    error_message = "The dashboard must show cluster-scoped CPU and memory plus its logs link."
  }
}
