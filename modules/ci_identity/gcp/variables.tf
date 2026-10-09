variable "project_id" {
  type = string
}
variable "name_prefix" {
  type    = string
  default = "one-tatchi"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,17}$", var.name_prefix))
    error_message = "name_prefix must be 5–18 lowercase letters, digits or hyphens."
  }
}
variable "repository_id" {
  description = "GitHub caller repository numeric ID; protects against repository-name reuse"
  type        = string
}
variable "repository_owner_id" {
  type = string
}
variable "oidc_subject_prefix" {
  type = string
}
variable "workflow_repository" {
  type    = string
  default = "SoftBank-Hackathon-2026-Team-Amethyst/one-tatchi-platform"
}
variable "allowed_workflows" {
  type    = set(string)
  default = ["infra.yml", "deploy.yml", "rollout.yml", "destroy.yml"]
}
variable "deploy_environments" {
  type    = list(string)
  default = ["test", "prod", "prod-auto", "destroy"]
}
variable "state_bucket" {
  type = string
}
