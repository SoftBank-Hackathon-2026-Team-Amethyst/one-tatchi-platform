output "dashboard_path" {
  description = "Dashboard path relative to https://console.cloud.google.com"
  value       = "/monitoring/dashboards/builder/${basename(google_monitoring_dashboard.this.id)}?project=${var.project_id}"
}
output "dashboard_url" {
  value = "https://console.cloud.google.com/monitoring/dashboards/builder/${basename(google_monitoring_dashboard.this.id)}?project=${var.project_id}"
}
