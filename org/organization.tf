resource "aws_organizations_organization" "this" {
  feature_set = "ALL"

  aws_service_access_principals = [
    "iam.amazonaws.com", # 멤버 계정 루트 중앙관리
    "sso.amazonaws.com", # Identity Center (콘솔에서 활성화하며 추가됨)
  ]

  enabled_policy_types = ["SERVICE_CONTROL_POLICY"]

  lifecycle {
    prevent_destroy = true
  }
}

# 멤버 계정의 루트 자격증명(비밀번호 · 액세스 키 · MFA)을 두지 않는다.
resource "aws_iam_organizations_features" "this" {
  enabled_features = [
    "RootCredentialsManagement",
    "RootSessions",
  ]

  depends_on = [aws_organizations_organization.this]
}
