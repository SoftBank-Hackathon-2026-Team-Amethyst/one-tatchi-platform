variable "project_id" {
  type = string
}
variable "cluster_name" {
  type = string
}
variable "region" {
  type    = string
  default = "asia-northeast3"
}
variable "readable_secret_ids" {
  description = "External Secrets가 읽을 Secret Manager 시크릿 ID 목록"
  type        = list(string)
}
variable "chart_versions" {
  type = object({
    argo_rollouts    = string
    external_secrets = string
  })
  default = {
    argo_rollouts    = "2.43.5"
    external_secrets = "2.11.0"
  }
}
