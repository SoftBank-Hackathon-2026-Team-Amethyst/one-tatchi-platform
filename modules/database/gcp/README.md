# database/gcp

Private Service Access를 통해 사설 Cloud SQL Postgres 17을 만든다. 기본은 서울, Enterprise `db-g1-small`, SSD 20GB, 단일 영역, 백업 1개다. 공개 IP 없이 TLS 연결만 허용한다. `private_services_cidr` 기본 10.120.0.0/16은 호출자가 노드·파드·서비스·관리 범위와 중복되지 않게 확인해야 한다. VPC마다 PSA 연결은 하나이므로 기존 연결이 있으면 이 모듈을 중복 사용하지 않는다.

필수 입력은 `project_id`, `name`, `database_name`, `network_id`다. 공통 출력 `host` · `port` · `database_name` · `credentials_secret_id`를 제공한다. 마지막 출력은 `username/password` JSON을 담은 Secret Manager 시크릿의 짧은 이름이다.

비밀번호는 ephemeral random_password → Secret Manager write-only → ephemeral 읽기 → Cloud SQL write-only로 전달한다. state·plan에 값이 남지 않는다. `password_version`을 증가시키면 둘을 함께 교체한다. SQL 사용자를 다시 만들 때도 저장된 동일 비밀번호를 사용한다. CI가 기존 비밀번호를 plan/apply 중 읽어야 하므로 `credential_readers`에 필요한 계정만 지정해 해당 DB 시크릿 읽기를 허용한다.

운영용은 `multi_az`, 백업 보관, 삭제 보호를 별도 설정한다. 현재 데모는 삭제 보호가 꺼져 있으며 PSA peering은 다른 managed service 보호를 위해 삭제 시 ABANDON한다. DB 사용자 삭제는 SQL 객체 소유권 때문에 실패할 수 있으므로 운영 DB 삭제는 별도 검토한다.

근거: [SQL write-only](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/sql_user), [Secret version write-only](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/secret_manager_secret_version).
