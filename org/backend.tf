# 이 스택의 state는 관리 계정의 S3 버킷(state.tf)에 둔다.
# 처음부터 다시 만들 때는 이 블록을 주석 처리하고 로컬 state로 버킷을 먼저 만든 뒤 `terraform init -migrate-state`.

terraform {
  backend "s3" {
    bucket       = "onetatchi-org-tfstate-813360232874"
    key          = "org/terraform.tfstate"
    region       = "ap-northeast-2"
    encrypt      = true
    use_lockfile = true
  }
}
