variable "cluster_name" {
  type = string
}

variable "region" {
  type = string
}

variable "network_id" {
  type = string
}

variable "readable_secret_arns" {
  description = "External Secrets가 읽을 수 있는 시크릿 ARN 목록"
  type        = list(string)
}

variable "chart_versions" {
  type = object({
    aws_load_balancer_controller = string
    argo_rollouts                = string
    external_secrets             = string
    external_dns                 = optional(string, "1.23.0")
    metrics_server               = optional(string, "3.13.0")
    cluster_autoscaler           = optional(string, "9.59.0")
    cluster_autoscaler_image     = optional(string, "v1.36.1")
  })
  default = {
    aws_load_balancer_controller = "3.5.0"
    argo_rollouts                = "2.43.5"
    external_secrets             = "2.11.0"
    external_dns                 = "1.23.0"
    metrics_server               = "3.13.0"
    cluster_autoscaler           = "9.59.0"
    cluster_autoscaler_image     = "v1.36.1"
  }
}

variable "dns_zone_id" {
  description = "external-dns가 레코드를 쓸 Route53 존 ID (dns 모듈 출력 zone_id). 비우면 external-dns를 설치하지 않는다"
  type        = string
  default     = ""
}
