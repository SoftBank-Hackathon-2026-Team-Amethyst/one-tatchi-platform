variable "repositories" {
  description = "만들 이미지 저장소 이름 목록"
  type        = set(string)
}

variable "keep_images" {
  description = "저장소마다 남겨 둘 최근 이미지 수"
  type        = number
  default     = 30
}
