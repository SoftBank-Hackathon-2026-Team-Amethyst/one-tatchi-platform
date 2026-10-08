# ---------- AWS Load Balancer Controller: Ingress → ALB ----------
module "lb_controller_identity" {
  source  = "terraform-aws-modules/eks-pod-identity/aws"
  version = "~> 2.9"

  name                            = "${var.cluster_name}-lb-controller"
  attach_aws_lb_controller_policy = true

  associations = {
    this = {
      cluster_name    = var.cluster_name
      namespace       = "kube-system"
      service_account = "aws-load-balancer-controller"
    }
  }
}

resource "helm_release" "lb_controller" {
  # 이전 apply에서 실패 상태로 남은 릴리스는 같은 이름으로 덮어쓴다.
  replace = true

  name       = "aws-load-balancer-controller"
  namespace  = "kube-system"
  repository = "https://aws.github.io/eks-charts"
  chart      = "aws-load-balancer-controller"
  version    = var.chart_versions.aws_load_balancer_controller

  values = [yamlencode({
    clusterName    = var.cluster_name
    region         = var.region
    vpcId          = var.network_id
    serviceAccount = { create = true, name = "aws-load-balancer-controller" }
    # Ingress만 쓰고 type=LoadBalancer Service는 쓰지 않는다. 켜 두면 컨트롤러가 준비되기 전
    # 모든 Service 생성(CoreDNS 포함)을 막아 교착이 생긴다.
    enableServiceMutatorWebhook = false
  })]

  depends_on = [module.lb_controller_identity]
}

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

# ---------- External Secrets: 클라우드 시크릿 → k8s Secret ----------
module "external_secrets_identity" {
  source  = "terraform-aws-modules/eks-pod-identity/aws"
  version = "~> 2.9"

  name                                  = "${var.cluster_name}-external-secrets"
  attach_external_secrets_policy        = true
  external_secrets_secrets_manager_arns = var.readable_secret_arns
  external_secrets_create_permission    = false

  associations = {
    this = {
      cluster_name    = var.cluster_name
      namespace       = "external-secrets"
      service_account = "external-secrets"
    }
  }
}

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

  depends_on = [module.external_secrets_identity]
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
      name     = "cloud-secrets"
      provider = { aws = { service = "SecretsManager", region = var.region } }
    }
  })]

  depends_on = [helm_release.external_secrets]
}
