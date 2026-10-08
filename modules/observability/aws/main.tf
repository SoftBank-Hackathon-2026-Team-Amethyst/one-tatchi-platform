# ---------- 수집: CloudWatch Container Insights (EKS 애드온) ----------
module "cloudwatch_agent_identity" {
  source  = "terraform-aws-modules/eks-pod-identity/aws"
  version = "~> 2.9"

  name                                       = "${var.cluster_name}-cloudwatch-agent"
  attach_aws_cloudwatch_observability_policy = true
}

resource "aws_eks_addon" "cloudwatch" {
  cluster_name = var.cluster_name
  addon_name   = "amazon-cloudwatch-observability"

  pod_identity_association {
    role_arn        = module.cloudwatch_agent_identity.iam_role_arn
    service_account = "cloudwatch-agent"
  }
}

# ---------- 시각화: Grafana (CloudWatch를 데이터 소스로) ----------
data "aws_iam_policy_document" "grafana_trust" {
  statement {
    actions = ["sts:AssumeRole", "sts:TagSession"]
    principals {
      type        = "Service"
      identifiers = ["pods.eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "grafana" {
  name               = "${var.cluster_name}-grafana"
  assume_role_policy = data.aws_iam_policy_document.grafana_trust.json
}

resource "aws_iam_role_policy_attachment" "grafana_cloudwatch" {
  role       = aws_iam_role.grafana.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchReadOnlyAccess"
}

resource "aws_eks_pod_identity_association" "grafana" {
  cluster_name    = var.cluster_name
  namespace       = "monitoring"
  service_account = "grafana"
  role_arn        = aws_iam_role.grafana.arn
}

resource "helm_release" "grafana" {
  # 이전 apply에서 실패 상태로 남은 릴리스는 같은 이름으로 덮어쓴다.
  replace = true

  name             = "grafana"
  namespace        = "monitoring"
  create_namespace = true
  repository       = "https://grafana-community.github.io/helm-charts"
  chart            = "grafana"
  version          = var.grafana_chart_version

  values = [yamlencode({
    serviceAccount = { create = true, name = "grafana" }

    "grafana.ini" = {
      server = {
        root_url            = "%(protocol)s://%(domain)s/grafana/"
        serve_from_sub_path = true
      }
      # 누구나 대시보드를 볼 수 있게 익명 읽기 전용. 관리자 비밀번호는 차트가 만든 k8s Secret에 있다.
      "auth.anonymous" = { enabled = true, org_role = "Viewer" }
    }

    ingress = {
      enabled          = true
      ingressClassName = var.ingress_class
      path             = "/grafana"
      pathType         = "Prefix"
      hosts            = []
      annotations = {
        "alb.ingress.kubernetes.io/scheme"           = "internet-facing"
        "alb.ingress.kubernetes.io/target-type"      = "ip"
        "alb.ingress.kubernetes.io/group.name"       = var.ingress_group
        "alb.ingress.kubernetes.io/group.order"      = "10"
        "alb.ingress.kubernetes.io/healthcheck-path" = "/grafana/api/health"
      }
    }

    datasources = {
      "datasources.yaml" = {
        apiVersion = 1
        datasources = [{
          name      = "CloudWatch"
          type      = "cloudwatch"
          uid       = "cloudwatch"
          isDefault = true
          jsonData  = { authType = "default", defaultRegion = var.region }
        }]
      }
    }

    dashboardProviders = {
      "dashboardproviders.yaml" = {
        apiVersion = 1
        providers = [{
          name            = "default"
          folder          = ""
          type            = "file"
          disableDeletion = true
          options         = { path = "/var/lib/grafana/dashboards/default" }
        }]
      }
    }

    dashboards = {
      default = {
        deploy-overview = {
          json = templatefile("${path.module}/dashboards/deploy-overview.json.tftpl", {
            cluster_name = var.cluster_name
          })
        }
      }
    }
  })]

  depends_on = [aws_eks_pod_identity_association.grafana]
}
