resource "google_secret_manager_secret" "this" {
  for_each  = var.names
  secret_id = each.value
  replication {
    auto {}
  }
}
