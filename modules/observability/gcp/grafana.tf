variable "grafana_eks_oidc_issuer" {
  description = "중앙 Grafana가 있는 EKS OIDC issuer. 비우면 기존 GCP 관측만 만든다."
  type        = string
  default     = ""
}
resource "google_iam_workload_identity_pool" "grafana" {
  count                     = var.grafana_eks_oidc_issuer == "" ? 0 : 1
  project                   = var.project_id
  workload_identity_pool_id = "grafana-eks"
  display_name              = "Central Grafana Monitoring"
}
resource "google_iam_workload_identity_pool_provider" "grafana" {
  count                              = var.grafana_eks_oidc_issuer == "" ? 0 : 1
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.grafana[0].workload_identity_pool_id
  workload_identity_pool_provider_id = "eks-grafana"
  attribute_mapping                  = { "google.subject" = "assertion.sub" }
  attribute_condition                = "assertion.sub == 'system:serviceaccount:monitoring:grafana'"
  oidc { issuer_uri = var.grafana_eks_oidc_issuer }
}
resource "google_service_account" "grafana" {
  count        = var.grafana_eks_oidc_issuer == "" ? 0 : 1
  project      = var.project_id
  account_id   = "grafana-monitoring"
  display_name = "Central Grafana Monitoring Viewer"
}
resource "google_project_iam_member" "grafana" {
  count   = var.grafana_eks_oidc_issuer == "" ? 0 : 1
  project = var.project_id
  role    = "roles/monitoring.viewer"
  member  = "serviceAccount:${google_service_account.grafana[0].email}"
}
resource "google_service_account_iam_member" "grafana" {
  count              = var.grafana_eks_oidc_issuer == "" ? 0 : 1
  service_account_id = google_service_account.grafana[0].name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principal://iam.googleapis.com/${google_iam_workload_identity_pool.grafana[0].name}/subject/system:serviceaccount:monitoring:grafana"
}
output "grafana_workload_provider" {
  value = try(google_iam_workload_identity_pool_provider.grafana[0].name, "")
}
output "grafana_service_account" {
  value = try(google_service_account.grafana[0].email, "")
}
