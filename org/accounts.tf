resource "aws_organizations_account" "one_tatchi" {
  name  = "one-tatchi"
  email = var.member_account_email

  # destroy하면 계정을 닫는다(조직에서 떼어내지 않음). prevent_destroy를 먼저 풀어야 한다.
  close_on_deletion = true

  lifecycle {
    prevent_destroy = true
    # 생성 시에만 쓰이고 import로 읽히지 않는 값. 바뀌면 계정을 다시 만들려 한다.
    ignore_changes = [role_name, iam_user_access_to_billing]
  }
}
