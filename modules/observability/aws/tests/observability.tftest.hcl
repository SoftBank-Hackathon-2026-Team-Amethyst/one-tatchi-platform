mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/test" }
  }
}
mock_provider "helm" {}
variables {
  cluster_name  = "test-eks"
  region        = "ap-northeast-2"
  ingress_class = "alb"
  ingress_group = "demo-app"
}
run "existing_installation_unchanged" {
  command = plan
  assert {
    condition     = length(yamldecode(helm_release.grafana.values[0]).ingress.hosts) == 0 && !contains(keys(yamldecode(helm_release.grafana.values[0]).ingress.annotations), "alb.ingress.kubernetes.io/listen-ports") && output.dashboard_url == ""
    error_message = "Legacy callers must retain hostless ingress without adding a TLS listener."
  }
  assert {
    condition     = length(helm_release.metrics) == 0 && length(helm_release.gcp_credentials) == 0 && length(aws_eks_addon.ebs) == 0
    error_message = "Existing module callers must not create new collectors or credentials."
  }
  assert {
    condition     = length(yamldecode(helm_release.grafana.values[0]).datasources["datasources.yaml"].datasources) == 1
    error_message = "CloudWatch remains the sole datasource until explicitly enabled."
  }
}

run "dashboard_on_production_https_listener" {
  command = plan
  variables {
    ingress_group   = "demo-app-prod"
    dashboard_host  = "onetatchi.soulee.dev"
    central_metrics = { enabled = true, receiver_host = "metrics.onetatchi.soulee.dev", receiver_secret_name = "metrics-auth" }
  }
  assert {
    condition     = yamldecode(helm_release.grafana.values[0]).ingress.hosts[0] == "onetatchi.soulee.dev" && jsondecode(yamldecode(helm_release.grafana.values[0]).ingress.annotations["alb.ingress.kubernetes.io/listen-ports"])[0].HTTPS == 443
    error_message = "Grafana must install its host/path rule on the public HTTPS listener."
  }
  assert {
    condition     = yamldecode(helm_release.grafana.values[0]).ingress.annotations["alb.ingress.kubernetes.io/group.name"] == yamldecode(helm_release.metrics[0].values[0]).receiver.ingressGroup && yamldecode(helm_release.metrics[0].values[0]).receiver.ingressGroup == "demo-app-prod"
    error_message = "Grafana and the receiver must share the production app ALB."
  }
  assert {
    condition     = yamldecode(helm_release.grafana.values[0])["grafana.ini"].server.root_url == "https://onetatchi.soulee.dev/grafana/" && output.dashboard_url == "https://onetatchi.soulee.dev/grafana/d/deploy-overview"
    error_message = "Redirects and published dashboard links must retain HTTPS and the Grafana subpath."
  }
}

run "reject_url_in_host" {
  command = plan
  variables { dashboard_host = "https://example.com/grafana" }
  expect_failures = [var.dashboard_host]
}
run "integrated_dashboard_and_keyless_auth" {
  command = plan
  variables {
    central_metrics = { enabled = true, receiver_host = "metrics.example.com", receiver_secret_name = "metrics-auth" }
    gcp_monitoring = {
      project_id            = "test-project"
      workload_provider     = "projects/123/locations/global/workloadIdentityPools/grafana-eks/providers/eks-grafana"
      service_account_email = "grafana@test-project.iam.gserviceaccount.com"
    }
  }
  assert {
    condition     = length(yamldecode(helm_release.grafana.values[0]).datasources["datasources.yaml"].datasources) == 3
    error_message = "Integrated mode needs all three explicitly provisioned datasources."
  }
  assert {
    condition     = jsondecode(yamldecode(helm_release.grafana.values[0]).dashboards.default.deploy-overview.json).uid == "deploy-overview"
    error_message = "Terraform must render valid dashboard JSON with the existing stable UID."
  }
  assert {
    condition = alltrue([for panel in jsondecode(local.dashboard_json).panels :
      strcontains(panel.targets[0].promQLQuery.expr, "pod_name=~\"($${service:raw})-.*\"")
      if startswith(panel.title, "GCP 컨테이너")
    ])
    error_message = "GCP resource panels must honor the selected service, including All regex."
  }
  assert {
    condition     = yamldecode(helm_release.gcp_credentials[0].values[0]).credentials.type == "external_account"
    error_message = "GCP authentication must use projected identity, never a service account private key."
  }
  assert {
    condition     = yamldecode(helm_release.gcp_credentials[0].values[0]).credentials.project_id == "test-project"
    error_message = "ADC must identify the project for Grafana health and resource lookups."
  }
  assert {
    condition = alltrue(flatten([for panel in jsondecode(local.dashboard_json).panels : [
      for target in try(panel.targets, []) : contains(keys(target), "timeSeriesList")
      if try(target.queryType, "") == "promQL"
    ]]))
    error_message = "PromQL targets must bypass the plugin's legacy metric migration."
  }
  assert {
    condition     = yamldecode(helm_release.grafana.values[0]).extraContainerVolumes[0].projected.sources[0].serviceAccountToken.audience == "https://iam.googleapis.com/projects/123/locations/global/workloadIdentityPools/grafana-eks/providers/eks-grafana" && yamldecode(helm_release.grafana.values[0]).extraVolumeMounts[0].mountPath == "/var/run/gcp"
    error_message = "The Grafana chart must preserve the projected token volume instead of rendering an emptyDir."
  }
  assert {
    condition     = yamldecode(helm_release.grafana.values[0])["grafana.ini"].plugins.forward_host_env_vars == "stackdriver" && yamldecode(helm_release.grafana.values[0]).env.GOOGLE_APPLICATION_CREDENTIALS == "/etc/gcp-wif/credentials.json"
    error_message = "The Cloud Monitoring plugin must receive the ADC path in Grafana 13."
  }
}
run "aws_onprem_before_gcp" {
  command = plan
  variables {
    central_metrics = { enabled = true, receiver_host = "metrics.example.com", receiver_secret_name = "metrics-auth" }
  }
  assert {
    condition     = !strcontains(local.dashboard_json, "cloud-monitoring") && strcontains(local.dashboard_json, "prometheus")
    error_message = "Hidden GCP targets must be removed when that datasource is not provisioned."
  }
}
