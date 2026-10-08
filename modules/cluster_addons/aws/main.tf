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

# ---------- external-dns: Ingress host → Route53 레코드 (T2) ----------
# dns_zone_id가 비어 있으면 설치하지 않는다. 이 존의 레코드만 만들고 고친다(지우지 않음).
module "external_dns_identity" {
  source  = "terraform-aws-modules/eks-pod-identity/aws"
  version = "~> 2.9"
  count   = var.dns_zone_id == "" ? 0 : 1

  name                          = "${var.cluster_name}-external-dns"
  attach_external_dns_policy    = true
  external_dns_hosted_zone_arns = ["arn:aws:route53:::hostedzone/${var.dns_zone_id}"]

  associations = {
    this = {
      cluster_name    = var.cluster_name
      namespace       = "kube-system"
      service_account = "external-dns"
    }
  }
}

resource "helm_release" "external_dns" {
  count = var.dns_zone_id == "" ? 0 : 1

  # 이전 apply에서 실패 상태로 남은 릴리스는 같은 이름으로 덮어쓴다.
  replace = true

  name       = "external-dns"
  namespace  = "kube-system"
  repository = "https://kubernetes-sigs.github.io/external-dns"
  chart      = "external-dns"
  version    = var.chart_versions.external_dns

  values = [yamlencode({
    provider       = { name = "aws" }
    serviceAccount = { create = true, name = "external-dns" }
    env            = [{ name = "AWS_DEFAULT_REGION", value = var.region }]
    sources        = ["ingress"]
    # upsert-only: 만들고 고치기만 한다. 사람이 만든 레코드나 다른 클러스터 레코드를 지우지 않는다.
    policy     = "upsert-only"
    registry   = "txt"
    txtOwnerId = var.cluster_name
    extraArgs  = ["--zone-id-filter=${var.dns_zone_id}", "--aws-zone-type=public"]
  })]

  depends_on = [module.external_dns_identity, helm_release.lb_controller]
}
