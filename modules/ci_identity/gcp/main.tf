locals {
  workflow_conditions = [for file in sort(tolist(var.allowed_workflows)) : "(assertion.job_workflow_ref == '${var.workflow_repository}/.github/workflows/${file}@refs/heads/main' || assertion.job_workflow_ref.startsWith('${var.workflow_repository}/.github/workflows/${file}@refs/tags/v'))"]
  deploy_subjects = concat(
    ["${var.oidc_subject_prefix}:ref:refs/heads/main"],
    [for env in var.deploy_environments : "${var.oidc_subject_prefix}:environment:${env}"]
  )
  deploy_condition = "assertion.sub in ${jsonencode(local.deploy_subjects)}"
  deploy_roles = toset([
    "roles/compute.networkAdmin", "roles/container.admin", "roles/cloudsql.admin",
    "roles/secretmanager.admin", "roles/artifactregistry.admin", "roles/monitoring.editor",
    "roles/iam.serviceAccountAdmin", "roles/iam.serviceAccountUser", "roles/resourcemanager.projectIamAdmin",
    "roles/servicenetworking.networksAdmin",
  ])
}

resource "google_iam_workload_identity_pool" "github" {
  project                   = var.project_id
  workload_identity_pool_id = "${var.name_prefix}-github"
  display_name              = "${var.name_prefix} GitHub"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  for_each = toset(["plan", "deploy"])

  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = each.key
  attribute_mapping = {
    "google.subject"                = "assertion.sub"
    "attribute.repository_id"       = "assertion.repository_id"
    "attribute.repository_owner_id" = "assertion.repository_owner_id"
    "attribute.access"              = "'${each.key}'"
  }
  attribute_condition = join(" && ", concat([
    "assertion.repository_id == '${var.repository_id}'",
    "assertion.repository_owner_id == '${var.repository_owner_id}'",
    "(${join(" || ", local.workflow_conditions)})",
  ], each.key == "deploy" ? [local.deploy_condition] : []))
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "ci" {
  for_each     = toset(["plan", "deploy"])
  project      = var.project_id
  account_id   = "${var.name_prefix}-gha-${each.key}"
  display_name = "${var.name_prefix} Terraform ${each.key}"
}

resource "google_service_account_iam_member" "federated" {
  for_each           = google_service_account.ci
  service_account_id = each.value.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.access/${each.key}"
  depends_on         = [google_iam_workload_identity_pool_provider.github]
}

resource "google_project_iam_member" "plan" {
  project = var.project_id
  role    = "roles/viewer"
  member  = "serviceAccount:${google_service_account.ci["plan"].email}"
}

resource "google_project_iam_member" "deploy" {
  for_each = local.deploy_roles
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.ci["deploy"].email}"
}

resource "google_storage_bucket_iam_member" "plan_read" {
  bucket = var.state_bucket
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.ci["plan"].email}"
}

resource "google_storage_bucket_iam_member" "plan_lock" {
  bucket = var.state_bucket
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.ci["plan"].email}"
  condition {
    title       = "terraform-locks-only"
    expression  = "resource.name.endsWith('.tflock')"
    description = "Write and delete lock objects, never state objects"
  }
}

resource "google_storage_bucket_iam_member" "deploy_state" {
  bucket = var.state_bucket
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.ci["deploy"].email}"
}
