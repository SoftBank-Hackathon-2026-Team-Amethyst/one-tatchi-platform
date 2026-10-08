variable "names" {
  description = "만들 시크릿 이름 목록. 값은 Terraform 밖에서 사람이 넣습니다"
  type        = set(string)
}
