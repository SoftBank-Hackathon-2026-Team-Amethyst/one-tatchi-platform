output "kube_context" {
  value = module.cluster.kube_context
}

# service-base 차트 값(database)에 그대로 넣는다.
output "database" {
  value = {
    host      = module.database.host
    port      = module.database.port
    name      = module.database.database_name
    remoteKey = module.database.credentials_secret_id
  }
}

output "repository_urls" {
  value = module.registry.repository_urls
}

output "public_url_command" {
  value = module.cluster_addons.public_url_command
}
