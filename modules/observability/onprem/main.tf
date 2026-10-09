resource "helm_release" "metrics" {
  name             = "deploy-metrics"
  namespace        = "monitoring"
  create_namespace = true
  chart            = "${path.module}/../../../charts/observability"
  values = [yamlencode({
    target  = "onprem"
    cluster = var.cluster_name
    remoteWrite = {
      url        = var.remote_write_url
      secretName = var.remote_write_secret_name
    }
    storage = {
      persistent = true
      className  = var.storage_class
      size       = "5Gi"
    }
  })]
}
