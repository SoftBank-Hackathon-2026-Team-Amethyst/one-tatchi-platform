output "plan_identity" {
  value = google_service_account.ci["plan"].email
}
output "deploy_identity" {
  value = google_service_account.ci["deploy"].email
}
output "workload_identity_provider" {
  description = "Deploy provider; use plan_workload_identity_provider for read-only planning"
  value       = google_iam_workload_identity_pool_provider.github["deploy"].name
}
output "plan_workload_identity_provider" {
  value = google_iam_workload_identity_pool_provider.github["plan"].name
}
