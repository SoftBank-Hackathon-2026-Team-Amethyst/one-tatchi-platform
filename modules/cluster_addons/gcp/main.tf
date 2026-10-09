resource "google_service_account" "external_secrets" {
  project      = var.project_id
  account_id   = "${substr(var.cluster_name, 0, 17)}-eso-${substr(md5(var.cluster_name), 0, 5)}"
  display_name = "${var.cluster_name} External Secrets"
}

resource "google_service_account_iam_member" "workload_identity" {
  service_account_id = google_service_account.external_secrets.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[external-secrets/external-secrets]"
}

resource "google_secret_manager_secret_iam_member" "read" {
  count     = length(var.readable_secret_ids)
  project   = var.project_id
  secret_id = var.readable_secret_ids[count.index]
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.external_secrets.email}"
}

resource "helm_release" "argo_rollouts" {
  name             = "argo-rollouts"
  namespace        = "argo-rollouts"
  create_namespace = true
  repository       = "https://argoproj.github.io/argo-helm"
  chart            = "argo-rollouts"
  version          = var.chart_versions.argo_rollouts
  replace          = true
  values           = [yamlencode({ dashboard = { enabled = true } })]
}

resource "helm_release" "external_secrets" {
  name             = "external-secrets"
  namespace        = "external-secrets"
  create_namespace = true
  repository       = "https://charts.external-secrets.io"
  chart            = "external-secrets"
  version          = var.chart_versions.external_secrets
  replace          = true
  values = [yamlencode({
    serviceAccount = {
      create      = true
      name        = "external-secrets"
      annotations = { "iam.gke.io/gcp-service-account" = google_service_account.external_secrets.email }
    }
  })]
  depends_on = [google_service_account_iam_member.workload_identity, google_secret_manager_secret_iam_member.read]
}

resource "helm_release" "secret_store" {
  name      = "platform-config"
  namespace = "external-secrets"
  chart     = "${path.module}/../../../charts/platform-config"
  replace   = true
  values = [yamlencode({
    secretStore = {
      name     = "cloud-secrets"
      provider = { gcpsm = { projectID = var.project_id } }
    }
  })]
  depends_on = [helm_release.external_secrets]
}
