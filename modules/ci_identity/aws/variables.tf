variable "name_prefix" {
  description = "역할 이름 접두사"
  type        = string
}

variable "oidc_subject_prefix" {
  description = "신뢰할 GitHub OIDC sub 접두사. immutable subject를 쓰는 레포는 repo:<owner>@<id>/<repo>@<id> 형식이다"
  type        = string
}

variable "deploy_environments" {
  description = "Deploy 권한을 받을 GitHub environment 이름 목록"
  type        = list(string)
  default     = []
}

variable "state_bucket_arn" {
  description = "plan 역할이 state를 읽고 락을 걸 S3 버킷 ARN"
  type        = string
}

variable "allowed_workflow_refs" {
  description = "역할을 받을 수 있는 재사용 워크플로 (OIDC job_workflow_ref, StringLike). 예: <org>/one-tatchi-platform/.github/workflows/*@refs/tags/v*. 비어 있으면 제한하지 않는다"
  type        = list(string)
  default     = []
}
