variable "project_id" {
  type = string
}
variable "name" {
  type = string
}
variable "database_name" {
  type = string
}
variable "username" {
  type    = string
  default = "app"
}
variable "engine_version" {
  type    = string
  default = "17"
}
variable "instance_class" {
  type    = string
  default = "db-g1-small"
}
variable "storage_gb" {
  type    = number
  default = 20
}
variable "multi_az" {
  type    = bool
  default = false
}
variable "backup_retention_days" {
  type    = number
  default = 1
}
variable "network_id" {
  type = string
}
variable "region" {
  type    = string
  default = "asia-northeast3"
}
variable "private_services_cidr" {
  type    = string
  default = "10.120.0.0/16"
  validation {
    condition     = can(cidrnetmask(var.private_services_cidr)) && tonumber(split("/", var.private_services_cidr)[1]) <= 24
    error_message = "private_services_cidr must be IPv4 with at least a /24 range, disjoint from node/pod/service/master ranges."
  }
}
variable "password_version" {
  description = "Increment to rotate both stored credentials and SQL password together"
  type        = number
  default     = 1
  validation {
    condition     = var.password_version >= 1 && var.password_version == floor(var.password_version)
    error_message = "password_version must be a positive integer."
  }
}
variable "deletion_protection" {
  type    = bool
  default = false
}
variable "credential_readers" {
  description = "CI identities that need ephemeral credential reads during plan/apply, scoped to this secret"
  type        = set(string)
  default     = []
}
