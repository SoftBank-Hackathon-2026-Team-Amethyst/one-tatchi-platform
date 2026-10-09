resource "aws_cloudwatch_log_group" "evidence" {
  count             = var.central_metrics.enabled ? 1 : 0
  name              = var.evidence_log_group
  retention_in_days = 14
}

resource "aws_iam_role" "ebs" {
  count              = var.central_metrics.enabled ? 1 : 0
  name               = "${var.cluster_name}-observability-ebs"
  assume_role_policy = data.aws_iam_policy_document.grafana_trust.json
}
resource "aws_iam_role_policy_attachment" "ebs" {
  count      = var.central_metrics.enabled ? 1 : 0
  role       = aws_iam_role.ebs[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
}
resource "aws_eks_addon" "ebs" {
  count        = var.central_metrics.enabled ? 1 : 0
  cluster_name = var.cluster_name
  addon_name   = "aws-ebs-csi-driver"
  pod_identity_association {
    role_arn        = aws_iam_role.ebs[0].arn
    service_account = "ebs-csi-controller-sa"
  }
  depends_on = [aws_iam_role_policy_attachment.ebs]
}
resource "helm_release" "metrics" {
  count            = var.central_metrics.enabled ? 1 : 0
  name             = "deploy-metrics"
  namespace        = "monitoring"
  create_namespace = true
  chart            = "${path.module}/../../../charts/observability"
  values = [yamlencode({
    target    = "aws"
    cluster   = var.cluster_name
    retention = "7d"
    storage   = { persistent = true, className = "deploy-metrics-gp3", size = "5Gi", createEbsClass = true }
    receiver = {
      enabled      = true
      host         = var.central_metrics.receiver_host
      secretName   = var.central_metrics.receiver_secret_name
      ingressClass = var.ingress_class
      ingressGroup = var.ingress_group
    }
  })]
  depends_on = [aws_eks_addon.ebs]
}
