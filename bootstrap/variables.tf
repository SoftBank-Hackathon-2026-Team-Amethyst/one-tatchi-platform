variable "project" {
  type    = string
  default = "one-tatchi"
}

variable "region" {
  type    = string
  default = "ap-northeast-2"
}

variable "github_oidc_subject_prefix" {
  description = "배포를 실행하는 대상 레포의 OIDC sub 접두사. gh api repos/<owner>/<repo>/actions/oidc/customization/sub 의 sub_claim_prefix 값 (immutable subject 사용 중)"
  type        = string
  default     = "repo:SoftBank-Hackathon-2026-Team-Amethyst@338407242/demo-app@1408704749"
}

variable "deploy_environments" {
  description = "Deploy 역할을 받을 GitHub environment"
  type        = list(string)
  default     = ["test", "prod", "destroy"]
}

variable "audit_log_lock_mode" {
  description = "GOVERNANCE는 특별 권한으로 해제 가능, COMPLIANCE는 누구도 해제 불가"
  type        = string
  default     = "GOVERNANCE"
}

variable "audit_log_retention_days" {
  type    = number
  default = 90
}
