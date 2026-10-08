variable "repositories" {
  description = "이미지 저장소 이름 목록"
  type        = set(string)
}

variable "owner" {
  description = "GHCR 소유자 (GitHub 조직 이름, 소문자)"
  type        = string
}
