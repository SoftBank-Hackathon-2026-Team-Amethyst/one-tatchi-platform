# AWS 접속 설정

팀원이 자기 계정으로 AWS 콘솔과 CLI를 쓰는 방법. 액세스 키는 발급하지 않고, IAM Identity Center(SSO)로 단기 자격증명만 쓴다.

## 계정 구조

```
관리 계정 (management)      ← 조직 · 결제 · Identity Center 관리. 팀원은 접근하지 않음
 └─ one-tatchi (멤버 계정)  ← 프로젝트 전용. 팀이 쓰는 곳
```

| 항목 | 값 |
|---|---|
| 접속 포털 (SSO start URL) | `https://d-9b675c5372.awsapps.com/start` |
| SSO 리전 | `ap-northeast-2` (서울) |
| 작업 리전 | `ap-northeast-2`만 허용 (다른 리전은 SCP로 막혀 있음) |

## 권한 세트

| 이름 | username | 권한 세트 (세션 8시간) |
|---|---|---|
| 이소울 | `soul.lee` | `AdministratorAccess` (관리 계정 포함) |
| 배준범 | `junbeom.bae` | `AdministratorAccess` |
| 김형래 | `hyeongrae.kim` | `AdministratorAccess` |
| 원가연 | `gayeon.won` | `AdministratorAccess` |
| 배규태 | `gyutae.bae` | `ReadOnlyAccess` |

계정 · 권한은 [`org/`](../org) Terraform으로 관리한다. 바꿀 일이 있으면 이소울에게 요청한다.

## 1. 처음 로그인

1. 접속 포털에 들어가서 내 username(위 표)을 입력한다.
2. 등록한 이메일로 일회용 코드가 온다. 코드를 입력하고 비밀번호를 정한다.
3. 포털에서 `one-tatchi` 계정과 내 권한 세트가 보이면 된다. 콘솔은 권한 세트 옆 **Management console**로 들어간다.

## 2. AWS CLI 설치

SSO는 **AWS CLI v2**에서만 된다.

```bash
aws --version   # aws-cli/2.x.x 이면 통과
```

없으면 설치한다.

- Windows: `winget install Amazon.AWSCLI`
- macOS: `brew install awscli`
- Linux / WSL: [설치 안내](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)

## 3. CLI 프로필 만들기

```bash
aws configure sso
```

질문에 아래처럼 답한다.

```
SSO session name (Recommended): onetatchi
SSO start URL [None]: https://d-9b675c5372.awsapps.com/start
SSO region [None]: ap-northeast-2
SSO registration scopes [sso:account:access]: (엔터)
```

브라우저가 열리면 로그인하고 **Allow**를 누른다. 터미널로 돌아와서 이어서 답한다.

```
(계정 선택)  one-tatchi
(역할 선택)  AdministratorAccess 또는 ReadOnlyAccess
Default client Region [None]: ap-northeast-2
CLI default output format [None]: json
Profile name [...]: onetatchi
```

결과로 `~/.aws/config`에 아래 내용이 생긴다. 직접 붙여 넣어도 된다(`<계정ID>`는 포털에서 확인).

```ini
[profile onetatchi]
sso_session = onetatchi
sso_account_id = <계정ID>
sso_role_name = AdministratorAccess
region = ap-northeast-2
output = json

[sso-session onetatchi]
sso_start_url = https://d-9b675c5372.awsapps.com/start
sso_region = ap-northeast-2
sso_registration_scopes = sso:account:access
```

## 4. 확인

```bash
aws sts get-caller-identity --profile onetatchi
```

`Arn`이 `arn:aws:sts::<계정ID>:assumed-role/AWSReservedSSO_AdministratorAccess_.../<내 username>` 형식이면 끝이다.

## 매일 쓰기

```bash
aws sso login --profile onetatchi       # 세션 만료(8시간) 후 다시 로그인

# 매번 --profile을 붙이기 싫으면
export AWS_PROFILE=onetatchi            # bash / zsh
$env:AWS_PROFILE = "onetatchi"          # PowerShell
```

Terraform, kubectl(`aws eks update-kubeconfig`), Helm은 같은 프로필을 그대로 쓴다.

## 규칙

- **액세스 키를 만들지 않는다.** IAM 사용자, 액세스 키 발급 금지. 모든 접근은 SSO로 한다.
- **자격증명을 공유하지 않는다.** 각자 자기 계정으로 로그인한다. 화면 공유나 채팅에 토큰 · `~/.aws/sso/cache` 내용을 올리지 않는다.
- **서울 리전만 쓴다.** 다른 리전 요청은 거부된다.
- **비용을 확인한다.** 월 예산 경보가 팀 전원에게 간다. 안 쓰는 EKS 노드 · RDS는 꺼 둔다.

## 문제 해결

| 증상 | 해결 |
|---|---|
| `Error loading SSO Token` / `Token has expired` | `aws sso login --profile onetatchi` |
| `aws configure sso`가 없는 명령이라고 나옴 | CLI v1이다. v2로 다시 설치 |
| 계정 목록에 `one-tatchi`가 없음 | 권한 할당 전이다. 이소울에게 요청 |
| `... with an explicit deny in a service control policy` | 서울 외 리전이거나 허용되지 않은 인스턴스 타입이다. 리전 · 타입 확인 |
| 브라우저가 안 열림 (WSL · 원격) | 터미널에 나온 URL과 코드를 브라우저에 직접 입력 |
