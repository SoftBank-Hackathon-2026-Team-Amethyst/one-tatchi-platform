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
