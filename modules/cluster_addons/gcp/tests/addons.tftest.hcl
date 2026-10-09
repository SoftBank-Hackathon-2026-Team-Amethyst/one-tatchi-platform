mock_provider "google" {}
mock_provider "helm" {}
variables {
  project_id          = "test-project"
  cluster_name        = "one-tatchi-gcp"
  readable_secret_ids = ["demo-app-db"]
}
run "scoped_secrets_and_provider" {
  command = plan
  assert {
    condition     = length(google_secret_manager_secret_iam_member.read) == 1 && google_secret_manager_secret_iam_member.read[0].secret_id == "demo-app-db" && google_secret_manager_secret_iam_member.read[0].role == "roles/secretmanager.secretAccessor"
    error_message = "External Secrets must read only the explicitly listed secrets."
  }
  assert {
    condition     = yamldecode(helm_release.secret_store.values[0]).secretStore.provider.gcpsm.projectID == "test-project" && output.ingress_class == "gce"
    error_message = "The common chart must receive gcpsm and expose the GKE controller class."
  }
}
