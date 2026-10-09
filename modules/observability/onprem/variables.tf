variable "cluster_name" { type = string }
variable "remote_write_url" {
  type    = string
  default = ""
}
variable "remote_write_secret_name" {
  description = "monitoring namespace의 기존 Secret 이름 (username/password 키)"
  type        = string
  default     = ""
}
variable "storage_class" {
  type    = string
  default = "local-path"
}
variable "dashboard_url" {
  description = "중앙 Grafana 전체 주소"
  type        = string
  default     = ""
}
