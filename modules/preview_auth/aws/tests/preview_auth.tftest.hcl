mock_provider "aws" {
  mock_data "aws_region" {
    defaults = { region = "ap-northeast-2" }
  }
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{}" }
  }
}
mock_provider "random" {}

variables {
  name           = "demo-app-preview"
  domain_prefix  = "demo-app-preview"
  callback_hosts = ["green.onetachi.example", "green-yolo.onetachi.example"]
}

run "pool_only_before_idp" {
  command = plan
  assert {
    condition     = length(aws_cognito_identity_provider.saml) == 0 && length(aws_cognito_user_pool_client.this.supported_identity_providers) == 0
    error_message = "Without IdP metadata no login provider may be enabled, including Cognito's own accounts."
  }
  assert {
    condition     = length(aws_secretsmanager_secret_policy.readers) == 0
    error_message = "No secret reader is granted unless requested."
  }
  assert {
    condition     = aws_cognito_user_pool.this.admin_create_user_config[0].allow_admin_create_user_only
    error_message = "Self sign-up must stay disabled."
  }
  assert {
    condition     = aws_cognito_user_pool_client.this.callback_urls == toset(["https://green.onetachi.example/oauth2/callback", "https://green-yolo.onetachi.example/oauth2/callback"])
    error_message = "Callbacks must be the oauth2-proxy callback of each green host."
  }
}

run "saml_only_login" {
  command = plan
  variables {
    saml_metadata_url = "https://portal.sso.ap-northeast-2.amazonaws.com/saml/metadata/example"
  }
  assert {
    condition     = aws_cognito_user_pool_client.this.supported_identity_providers == toset(["IdentityCenter"])
    error_message = "Only the SAML IdP may sign users in; COGNITO must not be allowed."
  }
  assert {
    condition     = aws_cognito_user_pool_client.this.allowed_oauth_flows == toset(["code"]) && aws_cognito_user_pool_client.this.generate_secret
    error_message = "oauth2-proxy uses the confidential authorization code flow."
  }
}

run "plan_role_can_refresh" {
  command = plan
  variables {
    secret_reader_arns = ["arn:aws:iam::123456789012:role/plan"]
  }
  assert {
    condition     = length(aws_secretsmanager_secret_policy.readers) == 1
    error_message = "Requested readers must get a secret resource policy so PR plans can refresh the version."
  }
}
