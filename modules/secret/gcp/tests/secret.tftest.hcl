mock_provider "google" {}
variables {
  names = ["app-config"]
}
run "secret_names_without_values" {
  command = plan
  assert {
    condition     = output.secret_ids["app-config"] == "app-config" && length(google_secret_manager_secret.this) == 1
    error_message = "Secret containers must use caller names and expose their IDs without reading values."
  }
}
