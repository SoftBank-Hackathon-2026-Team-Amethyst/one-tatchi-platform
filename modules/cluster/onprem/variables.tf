variable "name" {
  type = string
}

variable "kubernetes_version" {
  description = "k3s 이미지 태그 (rancher/k3s)"
  type        = string
  default     = "v1.33.4-k3s1"
}

variable "node_count" {
  description = "사전 생성할 k3d agent 노드 수. k3d는 이 모듈에서 node autoscaler로 확장하지 않는다"
  type        = number
  default     = 0
}

variable "api_port" {
  description = "호스트에서 쓰는 Kubernetes API 포트"
  type        = number
  default     = 6550
}
