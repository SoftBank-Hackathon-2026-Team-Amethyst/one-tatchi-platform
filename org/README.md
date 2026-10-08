# org

**팀 전용 스택. 템플릿의 일부가 아니다.** 해커톤 팀의 AWS 조직 · 계정 · 권한을 관리한다(T23). 템플릿을 가져다 쓰는 사람은 이 디렉터리를 무시하면 된다.

팀원 접속 방법은 [`docs/aws-setup.md`](../docs/aws-setup.md).

## 관리하는 것

| 파일 | 내용 |
|---|---|
| `organization.tf` | 조직, 신뢰 서비스(IAM · SSO), 멤버 계정 루트 중앙관리 |
| `accounts.tf` | 멤버 계정 `one-tatchi` |
| `scp.tf` | 가드레일 SCP: 서울 리전만, 탈퇴 · 해지 금지, EC2 · RDS 타입 제한 |
| `sso.tf` | 권한 세트(`AdministratorAccess`, `ReadOnlyAccess`), 사용자, 그룹, 계정 할당 |
| `budgets.tf` | `one-tatchi` 월 예산 경보 (크레딧 제외 금액 기준) |
| `state.tf` | 이 스택의 state 버킷 |

결정 배경은 [ADR 0001](../docs/adr/0001-aws-account-structure.md).

## 콘솔 설정 (Terraform 밖)

API가 없어 콘솔에서 직접 바꾼 값. 바꾸면 이 표도 고친다.

| 위치 | 설정 | 현재 값 |
|---|---|---|
| 관리 계정 루트 | MFA, 루트 액세스 키 | MFA 설정, 키 없음 |
| Billing → Credits | 크레딧 | 30만원 등록, 조직 공유 |
| IAM Identity Center | 인스턴스 | 조직 인스턴스, 서울(`ap-northeast-2`) |
| Identity Center → Settings → Authentication | MFA | **끔** (ADR 0001) |
| Identity Center → Settings → Authentication | Send email OTP for users created from API | 켬 |
| Billing → Cost Explorer | 활성화 | 켬 |

## 규칙

- **apply는 관리자가 로컬에서만 한다.** 관리 계정에 CI(OIDC)를 열지 않는다. 변경은 PR로 리뷰받는다.
- **`team.auto.tfvars`는 커밋하지 않는다.** 팀원 이메일이 들어 있다. 관리자 로컬에만 둔다.

## 처음 적용

2026-10-08에 적용을 마쳤다. 콘솔에서 먼저 만든 조직 · 멤버 계정 · SCP · 권한 세트 · 사용자를 import했고, state는 S3에 있다. 아래는 처음부터 다시 만들 때의 절차다.

```bash
# 0. 콘솔: IAM Identity Center → Settings → Authentication →
#    "Send email OTP for users created from API" 켜기
#    (API로 만든 사용자는 초대 메일이 안 간다. 이걸 켜야 첫 로그인 때 이메일 OTP로 비밀번호를 정할 수 있다)

export AWS_PROFILE=mgmt            # PowerShell: $env:AWS_PROFILE = "mgmt"
aws sso login

cp team.auto.tfvars.example team.auto.tfvars   # 채운다

# 1. 로컬 state로 import + 생성
terraform init
terraform plan                     # destroy가 있으면 멈춘다
terraform apply

# 2. state를 S3로 이전
#    (backend.tf를 주석 처리하고 시작했다면) 주석을 푼다
terraform init -migrate-state
rm terraform.tfstate terraform.tfstate.backup

# 3. (기존 리소스를 import했다면) import 블록을 지우고 plan이 깨끗한지 확인
terraform plan                     # No changes
```

## 팀원 추가 · 변경

`team.auto.tfvars`의 `users`를 고치고 `terraform apply`. `role`은 `admin` 또는 `readonly`.
username(키)은 바꿀 수 없다. 바꾸면 사용자를 지우고 새로 만든다.

## 정리 (프로젝트 종료 시)

`accounts.tf`의 `prevent_destroy`를 풀고 `terraform destroy`. `one-tatchi` 계정이 닫힌다(90일 뒤 영구 삭제).
