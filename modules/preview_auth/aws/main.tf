# 승인자용 green 미리보기의 OIDC 중계 (ADR 0015).
# 사용자는 IdP(Identity Center)에만 있다. Cognito는 SAML 로그인을 받아 oauth2-proxy에 OIDC로 넘긴다.
# 직접 가입과 Cognito 자체 계정 로그인은 막는다.

data "aws_region" "current" {}

resource "aws_cognito_user_pool" "this" {
  name                = var.name
  deletion_protection = "INACTIVE"

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  # 페더레이션 사용자만 쓰므로 이메일 확인 · 복구 메일을 보내지 않는다.
  account_recovery_setting {
    recovery_mechanism {
      name     = "admin_only"
      priority = 1
    }
  }
}

resource "aws_cognito_user_pool_domain" "this" {
  domain       = var.domain_prefix
  user_pool_id = aws_cognito_user_pool.this.id
}

locals {
  saml_enabled  = var.saml_metadata_url != ""
  provider_name = "IdentityCenter"
}

resource "aws_cognito_identity_provider" "saml" {
  count = local.saml_enabled ? 1 : 0

  user_pool_id  = aws_cognito_user_pool.this.id
  provider_name = local.provider_name
  provider_type = "SAML"

  provider_details = {
    MetadataURL = var.saml_metadata_url
    IDPSignout  = "false"
  }

  attribute_mapping = {
    email = var.saml_email_attribute
  }
}

resource "aws_cognito_user_pool_client" "this" {
  name         = var.name
  user_pool_id = aws_cognito_user_pool.this.id

  generate_secret                      = true
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email"]
  callback_urls                        = [for h in var.callback_hosts : "https://${h}/oauth2/callback"]
  # IdP 하나만 허용하면 Cognito 로그인 화면을 건너뛰고 IdP로 바로 보낸다. COGNITO(자체 계정)는 넣지 않는다.
  supported_identity_providers  = local.saml_enabled ? [aws_cognito_identity_provider.saml[0].provider_name] : []
  explicit_auth_flows           = ["ALLOW_REFRESH_TOKEN_AUTH"]
  prevent_user_existence_errors = "ENABLED"
}

resource "random_password" "cookie" {
  # oauth2-proxy 쿠키 암호화 키는 16 · 24 · 32바이트여야 한다.
  length  = 32
  special = false
}

# oauth2-proxy 환경변수 그대로. App Chart previewAuth.remoteKey가 이 시크릿을 External Secrets로 가져간다.
# 클라이언트 시크릿은 Cognito가 만들어 state에 남으므로, 사람이 값을 넣는 modules/secret과 달리 여기서 값을 쓴다.
resource "aws_secretsmanager_secret" "this" {
  name                    = "${var.name}-oauth2-proxy"
  recovery_window_in_days = 0
}

resource "aws_secretsmanager_secret_version" "this" {
  secret_id = aws_secretsmanager_secret.this.id
  secret_string = jsonencode({
    OAUTH2_PROXY_CLIENT_ID     = aws_cognito_user_pool_client.this.id
    OAUTH2_PROXY_CLIENT_SECRET = aws_cognito_user_pool_client.this.client_secret
    OAUTH2_PROXY_COOKIE_SECRET = random_password.cookie.result
  })
}

# ReadOnlyAccess에는 GetSecretValue가 없어, 이 정책이 없으면 PR plan의 refresh가 실패한다.
data "aws_iam_policy_document" "readers" {
  count = length(var.secret_reader_arns) > 0 ? 1 : 0

  statement {
    principals {
      type        = "AWS"
      identifiers = var.secret_reader_arns
    }
    actions   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
    resources = ["*"] # 시크릿 리소스 정책에서 *는 이 시크릿 하나다.
  }
}

resource "aws_secretsmanager_secret_policy" "readers" {
  count = length(var.secret_reader_arns) > 0 ? 1 : 0

  secret_arn = aws_secretsmanager_secret.this.arn
  policy     = data.aws_iam_policy_document.readers[0].json
}
