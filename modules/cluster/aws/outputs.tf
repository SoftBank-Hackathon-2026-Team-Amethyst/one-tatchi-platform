output "cluster_name" {
  value = module.eks.cluster_name
  # 이 값을 쓰는 Helm 애드온이 노드 그룹과 CoreDNS 등 클러스터 애드온이 준비된 뒤에 설치되도록 한다.
  depends_on = [module.eks]
}

output "endpoint" {
  value = module.eks.cluster_endpoint
}

output "ca_certificate" {
  description = "base64로 인코딩된 클러스터 CA"
  value       = module.eks.cluster_certificate_authority_data
}

output "node_security_group_id" {
  value = module.eks.node_security_group_id
}
