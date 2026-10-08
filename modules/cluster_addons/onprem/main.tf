# ---------- Argo Rollouts: 릴리스 전략 엔진 ----------
resource "helm_release" "argo_rollouts" {
  # 이전 apply에서 실패 상태로 남은 릴리스는 같은 이름으로 덮어쓴다.
  replace = true

  name             = "argo-rollouts"
  namespace        = "argo-rollouts"
  create_namespace = true
  repository       = "https://argoproj.github.io/argo-helm"
  chart            = "argo-rollouts"
  version          = var.chart_versions.argo_rollouts

  # UI는 공개하지 않는다. kubectl port-forward로만 연다.
  values = [yamlencode({
    dashboard = { enabled = true }
  })]
}

# ---------- External Secrets: 클러스터 안 k8s Secret → 서비스 네임스페이스 ----------
# 클라우드와 같은 ClusterSecretStore(cloud-secrets)를 두어 service-base 차트를 그대로 쓴다.
resource "helm_release" "external_secrets" {
  # 이전 apply에서 실패 상태로 남은 릴리스는 같은 이름으로 덮어쓴다.
  replace = true

  name             = "external-secrets"
  namespace        = "external-secrets"
  create_namespace = true
  repository       = "https://charts.external-secrets.io"
  chart            = "external-secrets"
  version          = var.chart_versions.external_secrets

  values = [yamlencode({
    serviceAccount = { create = true, name = "external-secrets" }
  })]
}

resource "kubernetes_namespace_v1" "secrets" {
  metadata {
    name = var.secret_namespace
  }
}

# 원본 네임스페이스의 Secret만 읽는 계정
resource "kubernetes_service_account_v1" "secret_reader" {
  metadata {
    name      = "secret-reader"
    namespace = kubernetes_namespace_v1.secrets.metadata[0].name
  }
}

resource "kubernetes_role_v1" "secret_reader" {
  metadata {
    name      = "secret-reader"
    namespace = kubernetes_namespace_v1.secrets.metadata[0].name
  }

  rule {
    api_groups = [""]
    resources  = ["secrets"]
    verbs      = ["get", "list", "watch"]
  }

  rule {
    api_groups = ["authorization.k8s.io"]
    resources  = ["selfsubjectrulesreviews"]
    verbs      = ["create"]
  }
}

resource "kubernetes_role_binding_v1" "secret_reader" {
  metadata {
    name      = "secret-reader"
    namespace = kubernetes_namespace_v1.secrets.metadata[0].name
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "Role"
    name      = kubernetes_role_v1.secret_reader.metadata[0].name
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account_v1.secret_reader.metadata[0].name
    namespace = kubernetes_namespace_v1.secrets.metadata[0].name
  }
}

# CRD가 먼저 설치돼야 하므로 ClusterSecretStore는 별도 릴리스로 올린다.
resource "helm_release" "secret_store" {
  # 이전 apply에서 실패 상태로 남은 릴리스는 같은 이름으로 덮어쓴다.
  replace = true

  name      = "platform-config"
  namespace = "external-secrets"
  chart     = "${path.module}/../../../charts/platform-config"

  values = [yamlencode({
    secretStore = {
      name = "cloud-secrets"
      provider = {
        kubernetes = {
          remoteNamespace = var.secret_namespace
          server = {
            caProvider = { type = "ConfigMap", name = "kube-root-ca.crt", key = "ca.crt", namespace = var.secret_namespace }
          }
          auth = {
            serviceAccount = { name = kubernetes_service_account_v1.secret_reader.metadata[0].name, namespace = var.secret_namespace }
          }
        }
      }
    }
  })]

  depends_on = [helm_release.external_secrets, kubernetes_role_binding_v1.secret_reader]
}

# ---------- Cloudflare Tunnel: 바깥 방향 연결로 고정 HTTPS 주소를 연다 ----------
# tunnel(하나)은 Deployment "cloudflared", tunnels(환경별)는 "cloudflared-<이름>"으로 뜬다.
locals {
  tunnels = merge(
    var.tunnel == null ? {} : { default = var.tunnel },
    var.tunnels,
  )
}

moved {
  from = kubernetes_deployment_v1.cloudflared
  to   = kubernetes_deployment_v1.cloudflared["default"]
}

resource "kubernetes_namespace_v1" "tunnel" {
  metadata {
    name = "cloudflared"
  }
}

resource "kubernetes_deployment_v1" "cloudflared" {
  for_each = local.tunnels

  metadata {
    name      = each.key == "default" ? "cloudflared" : "cloudflared-${each.key}"
    namespace = kubernetes_namespace_v1.tunnel.metadata[0].name
  }

  spec {
    # Quick Tunnel은 복제본마다 다른 주소가 생기므로 1개로 고정한다.
    replicas = each.value.token_secret != "" ? each.value.replicas : 1

    selector {
      match_labels = { app = "cloudflared", tunnel = each.key }
    }

    template {
      metadata {
        labels = { app = "cloudflared", tunnel = each.key }
      }

      spec {
        automount_service_account_token = false

        security_context {
          run_as_non_root = true
          run_as_user     = 65532
          seccomp_profile {
            type = "RuntimeDefault"
          }
        }

        container {
          name  = "cloudflared"
          image = var.cloudflared_image
          args = concat(
            ["tunnel", "--no-autoupdate", "--metrics", "0.0.0.0:2000"],
            each.value.token_secret != "" ? ["run"] : ["--url", each.value.origin_url],
          )

          dynamic "env" {
            for_each = each.value.token_secret != "" ? [1] : []
            content {
              name = "TUNNEL_TOKEN"
              value_from {
                secret_key_ref {
                  name = each.value.token_secret
                  key  = "token"
                }
              }
            }
          }

          liveness_probe {
            http_get {
              path = "/ready"
              port = 2000
            }
            initial_delay_seconds = 10
            period_seconds        = 10
            failure_threshold     = 3
          }

          resources {
            requests = { cpu = "10m", memory = "32Mi" }
            limits   = { memory = "128Mi" }
          }

          security_context {
            allow_privilege_escalation = false
            read_only_root_filesystem  = true
            capabilities {
              drop = ["ALL"]
            }
          }
        }
      }
    }
  }
}
