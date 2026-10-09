locals {
  dashboard = jsondecode(templatefile("${path.module}/dashboards/${var.central_metrics.enabled ? "deploy-overview" : "deploy-overview-legacy"}.json.tftpl", {
    cluster_name       = var.cluster_name
    evidence_log_group = var.evidence_log_group
    gcp_project        = var.gcp_monitoring == null ? "" : var.gcp_monitoring.project_id
    gcp_hidden         = var.gcp_monitoring == null
  }))
  # Mixed panels resolve even hidden datasource references. Remove unconfigured
  # GCP targets so AWS/onprem panels remain usable before GCP is connected.
  dashboard_json = jsonencode(merge(local.dashboard, {
    panels = [for panel in local.dashboard.panels : merge(panel, {
      targets = [for target in try(panel.targets, []) : target
      if var.gcp_monitoring != null || try(target.datasource.uid, "") != "cloud-monitoring"]
    }) if var.gcp_monitoring != null || !startswith(panel.title, "GCP 컨테이너")]
  }))
}
