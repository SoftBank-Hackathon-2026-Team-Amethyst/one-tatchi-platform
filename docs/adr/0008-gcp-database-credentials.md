# 0008: Cloud SQL 비밀번호를 state에 저장하지 않기

상태: 채택 (T4)

## 배경

AWS RDS는 비밀번호를 Secrets Manager에서 관리한다. Cloud SQL의 일반 password/secret_data 속성은 값을 Terraform state에 남기므로 같은 방식으로 사용할 수 없다.

## 결정

- Terraform 1.11 이상과 Google 7.x의 write-only 속성 `password_wo` · `secret_data_wo`를 사용한다.
- 비밀번호를 ephemeral random_password로 만들고 Secret Manager에 먼저 저장한다. 저장된 버전을 다시 ephemeral 리소스로 읽어 SQL 사용자에게 전달한다.
- 최초 실패 후 사용자만 재생성해도 Secret Manager에 남은 비밀번호를 재사용한다. 서로 다른 비밀번호가 DB와 시크릿에 저장되는 상황을 막는다.
- `password_version`을 명시적으로 증가시켜 비밀번호 교체를 요청한다. plan/deploy에는 해당 DB 시크릿 하나만 secretAccessor를 추가한다. 프로젝트 전체 시크릿 읽기를 plan에 부여하지 않는다.
- 공통 service-base의 username/password 계약과 DATABASE_URL·PG_URL 생성은 유지한다. Cloud SQL은 사설 IP와 ENCRYPTED_ONLY를 사용한다.

## 영향

ephemeral 읽기도 IAM 읽기 권한이 필요하다. plan의 DB 시크릿 접근은 C5의 메타데이터 조회 역할에 추가되는 제한적 예외다. state·저장된 plan에 비밀번호가 없음을 실제 생성 후 확인한다. state에는 Secret Manager 식별자와 버전만 남는다. 자동 주기 교체나 자동 앱 재시작은 별도 범위다.
