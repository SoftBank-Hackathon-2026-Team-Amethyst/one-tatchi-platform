output "secret_ids" {
  value = { for name, secret in google_secret_manager_secret.this : name => secret.secret_id }
}
