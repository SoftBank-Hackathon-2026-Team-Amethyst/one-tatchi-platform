resource "google_monitoring_dashboard" "this" {
  project = var.project_id
  dashboard_json = jsonencode({
    displayName = "${var.cluster_name} deployment overview"
    gridLayout = {
      # Monitoring API serializes this int64 field as a JSON string.
      columns = "2"
      widgets = concat([
        for item in [
          { title = "Container CPU", metric = "kubernetes.io/container/cpu/core_usage_time", aligner = "ALIGN_RATE", label = "CPU cores" },
          { title = "Container memory", metric = "kubernetes.io/container/memory/used_bytes", aligner = "ALIGN_MEAN", label = "Bytes" },
          ] : {
          title = item.title
          xyChart = {
            dataSets = [{
              plotType = "LINE"
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "resource.type=\"k8s_container\" AND resource.labels.cluster_name=\"${var.cluster_name}\" AND metric.type=\"${item.metric}\""
                  aggregation = {
                    alignmentPeriod    = "60s"
                    perSeriesAligner   = item.aligner
                    crossSeriesReducer = "REDUCE_SUM"
                    groupByFields      = ["resource.label.container_name"]
                  }
                }
              }
            }]
            yAxis = { label = item.label, scale = "LINEAR" }
          }
        }
        ], [{
          title = "Cluster logs"
          text = {
            format  = "MARKDOWN"
            content = "[Open Logs Explorer](https://console.cloud.google.com/logs/query?project=${var.project_id}). Filter by cluster_name=${var.cluster_name}. GKE system and workload logs are enabled in cluster/gcp."
          }
      }])
    }
  })
}
