resource "aws_db_subnet_group" "this" {
  name       = var.name
  subnet_ids = var.subnet_ids
}

resource "aws_security_group" "this" {
  name   = "${var.name}-db"
  vpc_id = var.network_id
}

resource "aws_vpc_security_group_ingress_rule" "postgres" {
  # 보안 그룹 ID는 apply 전에 알 수 없어서 for_each 대신 count(개수는 알 수 있음)를 쓴다.
  count = length(var.allowed_security_group_ids)

  security_group_id            = aws_security_group.this.id
  referenced_security_group_id = var.allowed_security_group_ids[count.index]
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_db_instance" "this" {
  identifier     = var.name
  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  db_name  = var.database_name
  username = var.username
  # 비밀번호는 RDS가 Secrets Manager에 만들고 교체한다. state에 평문이 남지 않는다.
  manage_master_user_password = true

  allocated_storage = var.storage_gb
  storage_type      = "gp3"
  storage_encrypted = true

  multi_az               = var.multi_az
  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.this.id]
  publicly_accessible    = false

  backup_retention_period   = var.backup_retention_days
  skip_final_snapshot       = var.skip_final_snapshot
  final_snapshot_identifier = var.skip_final_snapshot ? null : "${var.name}-final"
  deletion_protection       = false
  apply_immediately         = true
}
