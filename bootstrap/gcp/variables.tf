variable "project_id" {
  type    = string
  default = "one-tatchi-gejkm"
}
variable "region" {
  type    = string
  default = "asia-northeast3"
}
variable "repository_id" {
  type    = string
  default = "1408704749"
}
variable "repository_owner_id" {
  type    = string
  default = "338407242"
}
variable "oidc_subject_prefix" {
  type    = string
  default = "repo:SoftBank-Hackathon-2026-Team-Amethyst@338407242/demo-app@1408704749"
}

variable "enable_grafana_wif" {
  description = "GCP 관리자가 T17 WIF 관리 권한을 준비할 때만 true"
  type        = bool
  default     = false
}
