variable "name" {
  description = "클러스터 이름"
  type        = string
  default     = "onetouch"
}

variable "service" {
  type    = string
  default = "demo-app"
}

variable "database_name" {
  type    = string
  default = "demo"
}

variable "github_owner" {
  type    = string
  default = "SoftBank-Hackathon-2026-Team-Amethyst"
}

variable "tunnel" {
  description = "cluster_addons의 tunnel 입력. 기본은 Quick Tunnel로 test 네임스페이스의 FE를 연다"
  type = object({
    origin_url   = string
    token_secret = optional(string, "")
    replicas     = optional(number, 1)
  })
  default = {
    origin_url = "http://demo-app-fe.test.svc.cluster.local:80"
  }
}
