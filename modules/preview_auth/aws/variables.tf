variable "name" {
  description = "User Pool · 클라이언트 · 시크릿 이름 접두사 (예: demo-app-preview)"
  type        = string
}

variable "domain_prefix" {
  description = "Cognito 로그인 도메인 접두사. <prefix>.auth.<region>.amazoncognito.com. 리전 안에서 전역으로 유일해야 한다"
  type        = string
}

variable "callback_hosts" {
  description = "green 미리보기 호스트 목록 (예: green.onetachi.soulee.dev). 각 호스트의 /oauth2/callback을 허용한다"
  type        = list(string)
}

variable "saml_metadata_url" {
  description = "IdP SAML 메타데이터 URL (Identity Center 앱의 'SAML metadata file' URL). 비우면 IdP 없이 User Pool만 만든다: 첫 apply 후 출력 saml_acs_url · saml_audience로 IdP 앱을 만들고 다시 apply한다"
  type        = string
  default     = ""
}

variable "saml_email_attribute" {
  description = "IdP가 이메일을 보내는 SAML 속성 이름"
  type        = string
  default     = "email"
}

variable "secret_reader_arns" {
  description = "oauth2-proxy 시크릿 값을 읽을 IAM 역할 ARN (예: PR plan 역할). plan의 refresh가 시크릿 버전을 읽으려고 GetSecretValue를 호출한다. 이 역할이 state를 읽을 수 있다면 같은 값을 이미 볼 수 있다"
  type        = list(string)
  default     = []
}
