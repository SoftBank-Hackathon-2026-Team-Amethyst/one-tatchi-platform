variable "cluster_name" {
  type = string
}

variable "secret_namespace" {
  description = "시크릿 원본을 두는 네임스페이스. ClusterSecretStore가 여기서 읽는다"
  type        = string
  default     = "platform"
}

variable "tunnel" {
  description = <<-EOT
    Cloudflare Tunnel 설정.
    token_secret이 비어 있으면 계정 없이 쓰는 Quick Tunnel(*.trycloudflare.com, 재시작하면 주소가 바뀜)로 origin_url 하나만 연다.
    token_secret에 터널 토큰이 든 Secret 이름(키 token)을 주면 고정 도메인 Named Tunnel로 뜨고, 라우팅은 Cloudflare 대시보드에서 정한다.
  EOT
  type = object({
    origin_url   = string
    token_secret = optional(string, "")
    replicas     = optional(number, 1)
  })
  default = null
}

variable "tunnels" {
  description = "환경별 터널 (이름 → tunnel과 같은 모양). Deployment cloudflared-<이름>으로 뜬다. 예: { test = {...}, prod = {...} }"
  type = map(object({
    origin_url   = string
    token_secret = optional(string, "")
    replicas     = optional(number, 1)
  }))
  default = {}
}

variable "chart_versions" {
  type = object({
    argo_rollouts    = string
    external_secrets = string
  })
  default = {
    argo_rollouts    = "2.43.5"
    external_secrets = "2.11.0"
  }
}

variable "cloudflared_image" {
  type    = string
  default = "cloudflare/cloudflared:2026.10.0"
}
