variable "cluster_name" {
  description = "tailnet에 보이는 operator 기기 이름의 접두 (예: k3d-onetouch, one-tatchi)"
  type        = string
}

variable "tailnet" {
  description = "tailnet DNS 이름 (예: tailb7ed7e.ts.net). publish한 DB의 MagicDNS 이름을 만들 때 쓴다"
  type        = string
}

variable "oauth_client_id" {
  description = "Tailscale OAuth 클라이언트 ID (tag:k8s-operator 소유). write-only Secret으로만 전달하고 state에 남기지 않는다"
  type        = string
  sensitive   = true
  ephemeral   = true
}

variable "oauth_client_secret" {
  description = "Tailscale OAuth 클라이언트 secret. write-only Secret으로만 전달하고 state에 남기지 않는다"
  type        = string
  sensitive   = true
  ephemeral   = true
}

variable "oauth_revision" {
  description = "OAuth 값을 바꿨을 때 올린다 (write-only 값은 revision이 바뀔 때만 다시 쓴다)"
  type        = number
  default     = 1
}

variable "operator_chart_version" {
  description = "tailscale-operator Helm 차트 버전"
  type        = string
}

variable "publish" {
  description = <<-EOT
    tailnet에 내보낼 클러스터 안 DB. 키는 tailnet 기기 이름(MagicDNS 호스트명)이 된다.
    target은 클러스터 안 DNS 이름(예: demo-app-db-test.platform.svc.cluster.local). 같은 클러스터의 다른 네임스페이스여도 된다.
  EOT
  type = map(object({
    namespace = string
    target    = string
    port      = optional(number, 5432)
    tags      = optional(list(string), ["tag:db-onprem"])
  }))
  default = {}
}

variable "consume" {
  description = <<-EOT
    tailnet의 DB를 클러스터 안 Service로 끌어온다. 키는 Service 이름이고, 앱은 <키>.<namespace>.svc.cluster.local:<port>로 붙는다.
    fqdn은 상대 쪽이 publish한 MagicDNS 전체 이름(예: demo-app-db-test.tailb7ed7e.ts.net).
  EOT
  type = map(object({
    namespace = string
    fqdn      = string
    port      = optional(number, 5432)
    tags      = optional(list(string), ["tag:app-aws"])
  }))
  default = {}
}
