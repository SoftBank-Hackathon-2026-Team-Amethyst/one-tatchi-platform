variable "name" {
  description = "DB 이름 (StatefulSet · Service 이름)"
  type        = string
}

variable "database_name" {
  type = string
}

variable "username" {
  type    = string
  default = "app"
}

variable "engine_version" {
  description = "postgres 이미지 태그"
  type        = string
  default     = "17"
}

variable "storage_gb" {
  type    = number
  default = 5
}

variable "namespace" {
  description = "DB와 접속 정보 Secret을 둘 네임스페이스 (cluster_addons 출력값 secret_namespace)"
  type        = string
}
