# DB 링크(Tailscale 구현). 계층별 배포(T32 · T33)에서 앱과 DB가 다른 클러스터에 있을 때,
# DB 옆에서는 publish(클러스터 안 DB를 tailnet에만 노출), 앱 옆에서는 consume(tailnet의 DB를 클러스터 안 Service로)을 쓴다.
# 양쪽 다 같은 모듈이라 방향을 바꿔도(앱=온프레미스, DB=AWS) 입력만 달라진다.
# 데이터 경로는 WireGuard(P2P)이고 DB 포트는 인터넷에 열리지 않는다. 앱이 보는 것은 보통의 ClusterIP Service 하나다.

locals {
  namespace = "tailscale"
}

resource "kubernetes_namespace_v1" "tailscale" {
  count = var.manage_namespace ? 1 : 0

  metadata {
    name = local.namespace
  }
}

# OAuth 값은 ephemeral 입력 → write-only Secret. 차트에는 값을 넘기지 않고 operator가 이 Secret을 읽는다 (이름 · 키는 차트 규약).
# create_oauth_secret = false면 External Secrets 등이 같은 이름 · 키로 미리 만들어 둔다.
resource "kubernetes_secret_v1" "operator_oauth" {
  count = var.create_oauth_secret ? 1 : 0

  metadata {
    name      = "operator-oauth"
    namespace = local.namespace
  }

  data_wo = {
    client_id     = var.oauth_client_id
    client_secret = var.oauth_client_secret
  }
  data_wo_revision = var.oauth_revision

  depends_on = [kubernetes_namespace_v1.tailscale]
}

resource "helm_release" "operator" {
  name       = "tailscale-operator"
  namespace  = local.namespace
  repository = "https://pkgs.tailscale.com/helmcharts"
  chart      = "tailscale-operator"
  version    = var.operator_chart_version
  wait       = true
  timeout    = 300

  values = [yamlencode({
    # oauth 값을 비우면 차트가 Secret을 만들지 않고 위의 operator-oauth를 쓴다
    oauth = { clientId = "", clientSecret = "" }
    operatorConfig = {
      hostname    = "${var.cluster_name}-operator"
      defaultTags = ["tag:k8s"]
    }
  })]

  depends_on = [kubernetes_namespace_v1.tailscale, kubernetes_secret_v1.operator_oauth]
}

# publish: ExternalName Service에 expose 어노테이션을 달면 operator가 프록시 파드를 만들어 target을 tailnet에 내보낸다.
# DB Service 자체(database/onprem이 관리)는 건드리지 않는다. 이름이 겹치지 않게 operator 네임스페이스에 publish-<키>로 둔다.
resource "kubernetes_service_v1" "publish" {
  for_each = var.publish

  metadata {
    name      = "publish-${each.key}"
    namespace = local.namespace
    annotations = {
      "tailscale.com/expose"   = "true"
      "tailscale.com/hostname" = each.key
      "tailscale.com/tags"     = join(",", each.value.tags)
    }
  }

  spec {
    type          = "ExternalName"
    external_name = each.value.target
    port {
      name     = "postgres"
      port     = each.value.port
      protocol = "TCP"
    }
  }

  depends_on = [helm_release.operator]
}

# consume: tailnet-fqdn 어노테이션을 단 ExternalName Service. operator가 egress 프록시를 만들고 externalName을 그쪽으로 바꾼다.
resource "kubernetes_service_v1" "consume" {
  for_each = var.consume

  metadata {
    name      = coalesce(each.value.name, each.key)
    namespace = each.value.namespace
    annotations = {
      "tailscale.com/tailnet-fqdn" = each.value.fqdn
      "tailscale.com/tags"         = join(",", each.value.tags)
    }
  }

  spec {
    type          = "ExternalName"
    external_name = "placeholder"
    port {
      name     = "postgres"
      port     = each.value.port
      protocol = "TCP"
    }
  }

  lifecycle {
    # operator가 externalName을 프록시의 headless Service로 바꾼다
    ignore_changes = [spec[0].external_name]
  }

  depends_on = [helm_release.operator]
}

# consume.allow_from가 있으면 egress 프록시 파드(operator가 tailscale.com/parent-resource=<Service 이름>으로 라벨을 단다)에
# ingress 정책을 건다. 목록의 파드만 DB 포트로 들어올 수 있고, 다른 네임스페이스 · 파드는 거부된다. 프록시의 바깥 방향(tailnet)은 제한하지 않는다.
resource "kubernetes_network_policy_v1" "consume" {
  for_each = { for k, v in var.consume : k => v if length(v.allow_from) > 0 }

  metadata {
    name      = "db-link-${coalesce(each.value.name, each.key)}"
    namespace = local.namespace
  }

  spec {
    pod_selector {
      match_labels = {
        "tailscale.com/parent-resource"      = coalesce(each.value.name, each.key)
        "tailscale.com/parent-resource-ns"   = each.value.namespace
        "tailscale.com/parent-resource-type" = "svc"
      }
    }
    policy_types = ["Ingress"]

    ingress {
      dynamic "from" {
        for_each = each.value.allow_from
        content {
          namespace_selector {
            match_labels = { "kubernetes.io/metadata.name" = from.value.namespace }
          }
          pod_selector {
            match_labels = from.value.pod_labels
          }
        }
      }
      ports {
        port     = each.value.port
        protocol = "TCP"
      }
    }
  }

  depends_on = [kubernetes_service_v1.consume]
}
