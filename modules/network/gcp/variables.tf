variable "name" {
  description = "Network name; suffixes identify subnet, router and NAT."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,48}[a-z0-9]$", var.name))
    error_message = "name must be 2-50 lowercase letters, digits or hyphens, starting with a letter and ending with a letter or digit."
  }
}

variable "region" {
  description = "Region for the subnet, router and NAT."
  type        = string
  default     = "asia-northeast3"
}

variable "cidr" {
  description = "IPv4 address pool; its first sixteenth is the node subnet."
  type        = string
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.cidr)) && try(tonumber(split("/", var.cidr)[1]) >= 8 && tonumber(split("/", var.cidr)[1]) <= 24, false)
    error_message = "cidr must be an IPv4 CIDR with a prefix from /8 to /24; four subnet bits are added for nodes."
  }
}

variable "pods_cidr" {
  description = "Secondary IPv4 range for GKE pods."
  type        = string
  default     = "10.100.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.pods_cidr))
    error_message = "pods_cidr must be an IPv4 CIDR."
  }
}

variable "services_cidr" {
  description = "Secondary IPv4 range for GKE services."
  type        = string
  default     = "10.110.0.0/20"

  validation {
    condition     = can(cidrnetmask(var.services_cidr))
    error_message = "services_cidr must be an IPv4 CIDR."
  }
}
