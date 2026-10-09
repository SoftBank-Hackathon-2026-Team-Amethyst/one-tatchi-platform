output "dashboard_path" {
  description = "Ingress 주소 뒤에 붙는 Grafana 경로"
  value       = "/grafana"
}
output "evidence_log_group" {
  value = var.central_metrics.enabled ? aws_cloudwatch_log_group.evidence[0].name : ""
}
output "remote_write_url" {
  value = var.central_metrics.enabled ? "https://${var.central_metrics.receiver_host}/api/v1/write" : ""
}
