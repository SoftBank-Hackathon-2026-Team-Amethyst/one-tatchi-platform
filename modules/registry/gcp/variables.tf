variable "repositories" {
  description = "만들 이미지 저장소 이름 목록"
  type        = set(string)

  validation {
    condition     = alltrue([for name in var.repositories : can(regex("^[a-z][a-z0-9_-]{0,62}$", name))])
    error_message = "Repository names must start with a lowercase letter, contain only lowercase letters, digits, underscores or hyphens, and be at most 63 characters."
  }
}

variable "keep_images" {
  description = "이미지 경로마다 남겨 둘 최근 버전 수"
  type        = number
  default     = 30

  validation {
    condition     = var.keep_images >= 1 && floor(var.keep_images) == var.keep_images
    error_message = "keep_images must be a positive integer."
  }
}

variable "region" {
  description = "Artifact Registry 리전"
  type        = string
  default     = "asia-northeast3"
}
