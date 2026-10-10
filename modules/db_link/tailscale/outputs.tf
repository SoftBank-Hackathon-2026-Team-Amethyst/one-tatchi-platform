output "operator_namespace" {
  value = local.namespace
}

output "published" {
  description = "publish한 DB의 tailnet MagicDNS 이름. 상대 클러스터의 consume.fqdn에 넣는다"
  value       = { for k, v in var.publish : k => "${k}.${var.tailnet}" }
}

output "consumed" {
  description = "consume한 DB의 클러스터 안 주소. service-base의 database.host에 넣는다"
  value       = { for k, v in var.consume : k => { host = "${coalesce(v.name, k)}.${v.namespace}.svc.cluster.local", port = v.port } }
}
