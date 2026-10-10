variable "cluster_name" {
  description = "tailnet에 보이는 operator 기기 이름의 접두 (예: k3d-onetouch, one-tatchi)"
  type        = string
}

variable "tailnet" {
  description = "tailnet DNS 이름 (예: tailb7ed7e.ts.net). publish한 DB의 MagicDNS 이름을 만들 때 쓴다"
  type        = string
}

variable "create_oauth_secret" {
  description = <<-EOT
    true면 oauth_client_id · oauth_client_secret을 write-only Secret `tailscale/operator-oauth`로 만든다 (로컬 apply, 온프레미스).
    false면 그 Secret이 이미 있다고 본다. CI에서 apply하는 클라우드 루트는 값을 Terraform에 주지 않고
    External Secrets(service-base의 `secret` 블록)로 `operator-oauth`를 만든 뒤 이 모듈을 depends_on으로 뒤에 둔다.
  EOT
  type        = bool
  default     = true
}

variable "oauth_client_id" {
  description = "Tailscale OAuth 클라이언트 ID (tag:k8s-operator 소유). create_oauth_secret가 true일 때만. write-only Secret으로만 전달하고 state에 남기지 않는다"
  type        = string
  sensitive   = true
  ephemeral   = true
  default     = null
}

variable "oauth_client_secret" {
  description = "Tailscale OAuth 클라이언트 secret. create_oauth_secret가 true일 때만. write-only Secret으로만 전달하고 state에 남기지 않는다"
  type        = string
  sensitive   = true
  ephemeral   = true
  default     = null
}

variable "manage_namespace" {
  description = "false면 네임스페이스 `tailscale`을 만들지 않는다 (service-base 등 다른 것이 이미 만들 때)"
  type        = bool
  default     = true
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
    target = string
    port   = optional(number, 5432)
    tags   = optional(list(string), ["tag:db-onprem"])
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
    name      = optional(string) # Service 이름. 비우면 키. 여러 네임스페이스에 같은 이름을 쓰려면 키를 다르게 하고 name을 같게
    port      = optional(number, 5432)
    tags      = optional(list(string), ["tag:app-aws"])
    # 비우면 제한 없음. 적으면 egress 프록시 파드에 NetworkPolicy를 걸어 이 목록의 파드만 DB 포트에 닿는다 (T33).
    # 클러스터에 NetworkPolicy 적용기가 있어야 한다 (EKS: VPC CNI enableNetworkPolicy, k3s: 기본).
    allow_from = optional(list(object({
      namespace  = string      # 호출하는 파드의 네임스페이스 (kubernetes.io/metadata.name 라벨)
      pod_labels = map(string) # 호출하는 파드 라벨 (예: app.kubernetes.io/name = demo-app-be)
    })), [])
  }))
  default = {}
}
