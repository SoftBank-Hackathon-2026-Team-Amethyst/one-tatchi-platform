variable "name" {
  description = "DB 인스턴스 식별자"
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
  type    = string
  default = "17"
}

variable "instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "storage_gb" {
  type    = number
  default = 20
}

variable "multi_az" {
  description = "운영 환경에서는 true"
  type        = bool
  default     = false
}

variable "backup_retention_days" {
  type    = number
  default = 1
}

variable "skip_final_snapshot" {
  description = "삭제할 때 최종 스냅샷을 건너뛸지. 데모는 true, 운영은 false"
  type        = bool
  default     = true
}

variable "network_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "allowed_security_group_ids" {
  description = "DB 포트 접근을 허용할 보안 그룹 (클러스터 노드)"
  type        = list(string)
}
