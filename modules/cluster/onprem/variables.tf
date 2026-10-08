variable "name" {
  type = string
}

variable "kubernetes_version" {
  description = "k3s 이미지 태그 (rancher/k3s)"
  type        = string
  default     = "v1.33.4-k3s1"
}

variable "node_count" {
  description = "에이전트 노드 수. 맥북 한 대에서는 0(서버 노드 하나)으로 충분하다"
  type        = number
  default     = 0
}

variable "api_port" {
  description = "호스트에서 쓰는 Kubernetes API 포트"
  type        = number
  default     = 6550
}
