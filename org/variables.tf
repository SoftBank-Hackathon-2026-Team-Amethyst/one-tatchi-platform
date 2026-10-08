variable "member_account_email" {
  description = "one-tatchi 멤버 계정의 루트 이메일"
  type        = string
}

variable "users" {
  description = "Identity Center 사용자. 키는 username(이름.성 소문자)"
  type = map(object({
    given_name  = string
    family_name = string
    email       = string
    role        = string # admin | readonly
  }))

  validation {
    condition     = alltrue([for u in values(var.users) : contains(["admin", "readonly"], u.role)])
    error_message = "role은 admin 또는 readonly만 쓸 수 있다."
  }
}

variable "budget_limit_usd" {
  description = "one-tatchi 계정 월 예산(USD). 크레딧 30만원 ≈ $210"
  type        = number
  default     = 200
}

variable "budget_emails" {
  description = "예산 경보를 받을 이메일"
  type        = list(string)
}
