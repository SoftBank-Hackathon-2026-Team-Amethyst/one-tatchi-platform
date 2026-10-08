locals {
  management_account_id = "813360232874"
  region                = "ap-northeast-2"

  sso_instance_arn  = tolist(data.aws_ssoadmin_instances.this.arns)[0]
  identity_store_id = tolist(data.aws_ssoadmin_instances.this.identity_store_ids)[0]
}

data "aws_ssoadmin_instances" "this" {}
