# 그릇만 만듭니다. 값이 state와 코드에 남지 않도록 사람이 put-secret-value로 넣습니다.
resource "aws_secretsmanager_secret" "this" {
  for_each = var.names

  name = each.value
  # 지운 뒤 같은 이름으로 바로 다시 만들 수 있게 복구 대기 기간을 두지 않습니다.
  recovery_window_in_days = 0
}
