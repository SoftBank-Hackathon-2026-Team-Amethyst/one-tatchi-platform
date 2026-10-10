variable "cluster_name" {
  type = string
}

variable "region" {
  type = string
}

variable "ingress_class" {
  description = "Grafana를 노출할 IngressClass (cluster_addons 출력값)"
  type        = string
}

variable "ingress_group" {
  description = "앱과 ALB 하나를 공유하기 위한 Ingress 그룹 이름"
  type        = string
}

variable "grafana_chart_version" {
  type    = string
  default = "13.2.7"
}

variable "dashboard_host" {
  description = "중앙 Grafana의 HTTPS 호스트. 비우면 기존 host 없는 HTTP Ingress를 유지한다"
  type        = string
  default     = ""
  validation {
    condition     = var.dashboard_host == "" || (length(var.dashboard_host) <= 253 && can(regex("^([a-z0-9]([a-z0-9-]*[a-z0-9])?\\.)+[a-z0-9]([a-z0-9-]*[a-z0-9])?$", var.dashboard_host)))
    error_message = "dashboard_host에는 스킴·포트·경로 없이 DNS 호스트 이름만 입력하세요."
  }
}

variable "central_metrics" {
  description = "중앙 Prometheus. 인증 Secret(htpasswd)은 별도로 주입하며 Terraform이 비밀번호를 관리하지 않는다."
  type = object({
    enabled              = optional(bool, false)
    receiver_host        = optional(string, "")
    receiver_secret_name = optional(string, "")
  })
  default = {}
  validation {
    condition     = !var.central_metrics.enabled || (var.central_metrics.receiver_host != "" && var.central_metrics.receiver_secret_name != "")
    error_message = "central_metrics requires a TLS hostname and an existing receiver Secret name."
  }
}
variable "evidence_log_group" {
  type    = string
  default = "/one-tatchi/deploy-evidence"
}
variable "gcp_monitoring" {
  description = "GCP WIF를 통한 읽기 전용 Cloud Monitoring 인증 (키 파일 아님)"
  type = object({
    project_id            = string
    workload_provider     = string
    service_account_email = string
  })
  default = null
}
