# 맥북(온프레미스) 루트 예시. demo-app의 infra/envs/onprem은 같은 모양으로 source만
# git::https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/one-tatchi-platform.git//modules/<기능>/onprem?ref=v1.x.y 로 바꾼다.
# state는 이 맥북에만 둔다 (로컬 backend).
terraform {
  required_version = ">= 1.6"
}

module "cluster" {
  source = "../../modules/cluster/onprem"
  name   = var.name
}

provider "kubernetes" {
  host                   = module.cluster.endpoint
  cluster_ca_certificate = base64decode(module.cluster.ca_certificate)
  client_certificate     = base64decode(module.cluster.client_certificate)
  client_key             = base64decode(module.cluster.client_key)
}

provider "helm" {
  kubernetes = {
    host                   = module.cluster.endpoint
    cluster_ca_certificate = base64decode(module.cluster.ca_certificate)
    client_certificate     = base64decode(module.cluster.client_certificate)
    client_key             = base64decode(module.cluster.client_key)
  }
}

module "cluster_addons" {
  source       = "../../modules/cluster_addons/onprem"
  cluster_name = module.cluster.cluster_name
  tunnel       = var.tunnel
}

module "registry" {
  source       = "../../modules/registry/onprem"
  owner        = var.github_owner
  repositories = ["${var.service}-be", "${var.service}-fe"]
}

module "database" {
  source        = "../../modules/database/onprem"
  name          = "${var.service}-db"
  database_name = var.database_name
  namespace     = module.cluster_addons.secret_namespace
}
