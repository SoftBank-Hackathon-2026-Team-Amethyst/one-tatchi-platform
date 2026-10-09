output "github_variables" {
  value = {
    GCP_PROJECT           = var.project_id
    GCP_REGION            = var.region
    GCP_WIF_PROVIDER      = module.ci_identity.workload_identity_provider
    GCP_PLAN_WIF_PROVIDER = module.ci_identity.plan_workload_identity_provider
    GCP_PLAN_IDENTITY     = module.ci_identity.plan_identity
    GCP_DEPLOY_IDENTITY   = module.ci_identity.deploy_identity
    GCP_TF_STATE_BUCKET   = google_storage_bucket.state.name
    GCP_CLUSTER           = "one-tatchi-gcp"
  }
}
