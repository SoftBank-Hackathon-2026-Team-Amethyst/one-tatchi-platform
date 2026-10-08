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
  })
  default = {
    aws_load_balancer_controller = "3.5.0"
    argo_rollouts                = "2.43.5"
    external_secrets             = "2.11.0"
  }
}
