output "host" {
  value      = google_sql_database_instance.this.private_ip_address
  depends_on = [google_sql_user.app, google_sql_database.app]
}
output "port" {
  value = 5432
}
output "database_name" {
  value = google_sql_database.app.name
}
output "credentials_secret_id" {
  description = "username/password JSON secret name for gcpsm"
  value       = google_secret_manager_secret.credentials.secret_id
  depends_on  = [google_sql_user.app, google_secret_manager_secret_version.credentials]
}
