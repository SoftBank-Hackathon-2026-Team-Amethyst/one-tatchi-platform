mock_provider "google" {}
variables {
  project_id          = "test-project"
  repository_id       = "1408704749"
  repository_owner_id = "338407242"
  oidc_subject_prefix = "repo:example@338407242/demo-app@1408704749"
  state_bucket        = "test-project-state"
}
run "separate_trust_and_lock_permissions" {
  command = plan
  assert {
    condition     = strcontains(google_iam_workload_identity_pool_provider.github["plan"].attribute_condition, "assertion.repository_id == '1408704749'") && !strcontains(google_iam_workload_identity_pool_provider.github["plan"].attribute_condition, "assertion.sub in") && strcontains(google_iam_workload_identity_pool_provider.github["deploy"].attribute_condition, "assertion.sub in")
    error_message = "Numeric caller trust is mandatory and only deploy may require protected subjects."
  }
  assert {
    condition     = google_storage_bucket_iam_member.plan_lock.condition[0].expression == "resource.name.endsWith('.tflock')" && google_storage_bucket_iam_member.plan_read.role == "roles/storage.objectViewer"
    error_message = "Plan may read state and write locks, but must not write state."
  }
  assert {
    condition     = google_iam_workload_identity_pool_provider.github["deploy"].attribute_mapping["attribute.access"] == "'deploy'" && google_iam_workload_identity_pool_provider.github["plan"].attribute_mapping["attribute.access"] == "'plan'" && !contains(local.deploy_roles, "roles/owner") && !contains(local.deploy_roles, "roles/editor")
    error_message = "The providers must map access independently and deploy must not receive Owner or Editor."
  }
}
