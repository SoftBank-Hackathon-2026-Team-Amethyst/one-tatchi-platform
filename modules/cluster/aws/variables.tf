variable "name" {
  type = string
}

variable "kubernetes_version" {
  type    = string
  default = "1.36"
}

variable "network_id" {
  type = string
}

variable "subnet_ids" {
  description = "노드와 컨트롤 플레인을 둘 프라이빗 서브넷"
  type        = list(string)
}

variable "node_instance_types" {
  type    = list(string)
  default = ["t3.medium"]
}

variable "node_count" {
  type = object({
    min     = number
    desired = number
    max     = number
  })
  default = { min = 2, desired = 2, max = 3 }
}

variable "admin_principal_arns" {
  description = "클러스터와 암호화 키 관리자 권한을 줄 IAM 주체 (GHA Deploy 역할 포함)"
  type        = list(string)
  default     = []
}

variable "viewer_principal_arns" {
  description = "읽기 전용(시크릿 포함) 권한을 줄 IAM 주체. terraform plan 역할용"
  type        = list(string)
  default     = []
}
