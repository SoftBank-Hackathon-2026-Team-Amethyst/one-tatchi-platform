resource "helm_release" "gcp_credentials" {
  count            = var.gcp_monitoring == null ? 0 : 1
  name             = "grafana-gcp-wif"
  namespace        = "monitoring"
  create_namespace = true
  chart            = "${path.module}/../../../charts/grafana-wif"
  values = [yamlencode({
    credentials = {
      type                              = "external_account"
      audience                          = "//iam.googleapis.com/${var.gcp_monitoring.workload_provider}"
      subject_token_type                = "urn:ietf:params:oauth:token-type:jwt"
      token_url                         = "https://sts.googleapis.com/v1/token"
      service_account_impersonation_url = "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/${var.gcp_monitoring.service_account_email}:generateAccessToken"
      credential_source                 = { file = "/var/run/gcp/token" }
    }
  })]
}
