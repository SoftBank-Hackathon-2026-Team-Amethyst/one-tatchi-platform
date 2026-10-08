# SCP는 관리 계정에는 적용되지 않는다. one-tatchi 계정에만 연결한다.
# 서비스 연결 역할(예: EKS 노드 그룹의 Auto Scaling)에는 SCP가 적용되지 않으니
# 인스턴스 타입 제한은 사람이 직접 띄우는 경우만 막는다.
data "aws_iam_policy_document" "guardrails" {
  statement {
    sid    = "DenyOutsideSeoul"
    effect = "Deny"
    # 글로벌 서비스(us-east-1로 호출되는 것)는 예외
    not_actions = [
      "account:*",
      "acm:*",
      "billing:*",
      "budgets:*",
      "ce:*",
      "cloudfront:*",
      "cur:*",
      "health:*",
      "iam:*",
      "identitystore:*",
      "organizations:*",
      "pricing:*", # T16 가격 조회
      "route53:*",
      "route53domains:*",
      "s3:GetBucketLocation",
      "s3:ListAllMyBuckets",
      "sso:*",
      "sts:*",
      "support:*",
      "waf:*",
      "wafv2:*",
    ]
    resources = ["*"]

    condition {
      test     = "StringNotEquals"
      variable = "aws:RequestedRegion"
      values   = [local.region]
    }
  }

  statement {
    sid       = "DenyLeaveAndCloseAccount"
    effect    = "Deny"
    actions   = ["organizations:LeaveOrganization", "account:CloseAccount"]
    resources = ["*"]
  }

  statement {
    sid       = "LimitEc2InstanceTypes"
    effect    = "Deny"
    actions   = ["ec2:RunInstances"]
    resources = ["arn:aws:ec2:*:*:instance/*"]

    condition {
      test     = "StringNotLike"
      variable = "ec2:InstanceType"
      values   = ["t3.*", "t3a.*", "t4g.*", "m6i.large", "m7i.large", "c6i.large"]
    }
  }

  statement {
    sid       = "LimitRdsInstanceClasses"
    effect    = "Deny"
    actions   = ["rds:CreateDBInstance", "rds:ModifyDBInstance"]
    resources = ["*"]

    condition {
      test     = "StringNotLike"
      variable = "rds:DatabaseClass"
      values   = ["db.t3.*", "db.t4g.*"]
    }
  }
}

resource "aws_organizations_policy" "guardrails" {
  name        = "one-tatchi-guardrails"
  description = "서울 리전만, 조직 탈퇴 · 계정 해지 금지, EC2 · RDS 타입 제한"
  type        = "SERVICE_CONTROL_POLICY"
  content     = data.aws_iam_policy_document.guardrails.json
}

resource "aws_organizations_policy_attachment" "guardrails_one_tatchi" {
  policy_id = aws_organizations_policy.guardrails.id
  target_id = aws_organizations_account.one_tatchi.id
}
