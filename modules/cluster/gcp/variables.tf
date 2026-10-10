variable "project_id" {
  type = string
}

variable "name" {
  description = "GKE cluster name."
  type        = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,38}[a-z0-9]$", var.name))
    error_message = "name must be 2-40 lowercase letters, digits or hyphens, starting with a letter and ending with a letter or digit."
  }
}

variable "region" {
  description = "Region of the Standard regional cluster."
  type        = string
  default     = "asia-northeast3"
}

variable "node_locations" {
  description = "Distinct zones within region; total counts are distributed across these zones."
  type        = list(string)
  default     = ["asia-northeast3-a", "asia-northeast3-b"]
  validation {
    condition     = length(var.node_locations) > 0 && length(distinct(var.node_locations)) == length(var.node_locations) && alltrue([for zone in var.node_locations : startswith(zone, "${var.region}-")])
    error_message = "node_locations must be distinct, nonempty zones in region."
  }
}

variable "kubernetes_version" {
  description = "Minimum GKE control plane version, including the GKE suffix. Null uses the REGULAR channel default."
  type        = string
  default     = "1.36.4-gke.1391000"
}

variable "network_id" {
  description = "VPC ID from network/gcp."
  type        = string
}

variable "subnet_ids" {
  description = "One regional node subnet ID from network/gcp."
  type        = list(string)
  validation {
    condition     = length(var.subnet_ids) == 1
    error_message = "GCP expects exactly one regional subnet ID."
  }
}

variable "pods_range_name" {
  description = "Pod secondary IP range name from network/gcp."
  type        = string
}

variable "services_range_name" {
  description = "Service secondary IP range name from network/gcp."
  type        = string
}

variable "node_instance_types" {
  description = "One GCP machine type; the input name matches AWS."
  type        = list(string)
  default     = ["e2-standard-2"]
  validation {
    condition     = length(var.node_instance_types) == 1
    error_message = "GCP requires exactly one machine type for these node pools."
  }
}

variable "node_count" {
  description = "TOTAL counts across all zones, not counts per zone."
  type = object({
    min     = number
    desired = number
    max     = number
  })
  default = { min = 3, desired = 3, max = 5 }
  validation {
    condition = (
      var.node_count.min >= length(var.node_locations) &&
      var.node_count.min <= var.node_count.desired && var.node_count.desired <= var.node_count.max &&
      alltrue([for count in [var.node_count.min, var.node_count.desired, var.node_count.max] : count == floor(count)])
    )
    error_message = "Counts must be integers with min <= desired <= max and at least one node per zone."
  }
}

variable "master_ipv4_cidr" {
  description = "Nonoverlapping private /28 for the GKE control plane."
  type        = string
  default     = "172.16.0.0/28"
  validation {
    condition     = can(cidrnetmask(var.master_ipv4_cidr)) && endswith(var.master_ipv4_cidr, "/28")
    error_message = "master_ipv4_cidr must be an IPv4 /28."
  }
}

variable "authorized_networks" {
  description = "Optional source CIDRs for the public API. Empty leaves source IP unrestricted; IAM/RBAC still apply (hosted GitHub runners)."
  type        = map(string)
  default     = {}
  validation {
    condition     = alltrue([for cidr in values(var.authorized_networks) : can(cidrnetmask(cidr))])
    error_message = "authorized_networks values must be IPv4 CIDRs."
  }
}
