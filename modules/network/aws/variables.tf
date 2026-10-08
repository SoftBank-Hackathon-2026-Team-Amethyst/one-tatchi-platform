variable "name" {
  type = string
}

variable "cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "az_count" {
  type    = number
  default = 2
}

variable "single_nat" {
  description = "NAT를 하나만 둘지(비용 절감) AZ마다 둘지(가용성)"
  type        = bool
  default     = true
}
