# slack-bot

배포 파이프라인 결과를 Slack 채널에서 받고, 같은 자리에서 버튼으로 조작을 요청하는 봇입니다 (T26).

- **알림**: 워크플로가 `.github/actions/slack-notify`로 배포, 승격, 되돌리기, 인프라 반영 결과를 채널에 올립니다.
- **Blue-Green 조작**: 알림의 승격 · 취소 · 되돌리기 버튼이나 `/rollout` 명령을 봇이 받아 대상 레포의 rollout 워크플로를 실행합니다. 그 워크플로는 platform 재사용 워크플로 `rollout.yml`을 호출합니다.
- **PR 머지**: janto PR 알림의 머지 버튼을 누르면 봇이 PR을 머지하고, 누른 사람을 PR 코멘트로 남깁니다. 필수 검사 등 머지 규칙은 GitHub 브랜치 보호가 그대로 지킵니다.

봇은 클러스터 권한이 없습니다. 실제 반영은 배포 파이프라인만 하고, 요청한 Slack 사용자는 감사 로그의 `requested_by`에 남습니다.

```
대상 레포 워크플로 ──알림(승격 · 취소 · 머지 버튼)──▶ Slack 채널
                                                     │ 버튼 클릭 또는 /rollout
                                                     ▼
대상 레포 rollout 워크플로 ◀──workflow_dispatch── slack-bot (Socket Mode)
  └─ platform rollout.yml ──결과 알림(되돌리기 버튼)──▶ Slack 채널
```

Socket Mode를 쓰므로 봇이 Slack으로 연결을 겁니다. 공개 엔드포인트와 Ingress가 필요 없어 클러스터 · 맥북 · 로컬 어디서든 돌릴 수 있습니다.

## 처음 세팅 (한 번만)

1. **Slack 앱 생성**: https://api.slack.com/apps 에서 "From a manifest"를 고르고 [`manifest.yaml`](manifest.yaml)을 붙여 넣은 뒤 워크스페이스에 설치합니다.
   - Bot User OAuth Token(`xoxb-`)을 복사합니다.
   - Basic Information → App-Level Tokens에서 `connections:write` 스코프로 토큰(`xapp-`)을 만듭니다.
2. **GitHub 인증**: 팀 GitHub App `one-tatchi-bot`을 씁니다(개인 토큰을 쓰지 않습니다). 필요한 권한은 **Actions**(워크플로 실행), **Pull requests** · **Contents**(머지 · 코멘트) 쓰기입니다.
3. **대상 레포 설정**: Settings → Secrets and variables → Actions. 둘 중 하나라도 없으면 알림 단계는 건너뜁니다.
   - Secret `SLACK_BOT_TOKEN`: 1번의 `xoxb-` 토큰
   - Variable `SLACK_CHANNEL_ID`: 알림을 받을 채널 ID
4. **대상 레포에 rollout 워크플로 추가**: 아래 [대상 레포 호출 예시](#대상-레포-호출-예시).

## 환경 변수

| 이름 | 설명 | 기본값 |
|---|---|---|
| `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN` | Slack 토큰 | 필수 |
| `GITHUB_REPOSITORY` | 조작할 대상 레포 (`owner/demo-app`) | 필수 |
| `GITHUB_APP_CLIENT_ID`, `GITHUB_APP_PRIVATE_KEY` | GitHub App 인증 (권장) | 둘 중 하나 필수 |
| `GITHUB_TOKEN` | 토큰 인증 (로컬 시험용) | 〃 |
| `ROLLOUT_WORKFLOW` | 대상 레포의 rollout 워크플로 파일 | `rollout.yml` |
| `GITHUB_REF` | rollout 워크플로를 실행할 브랜치 | `main` |
| `MERGE_METHOD` | 머지 방식 (`squash` · `merge` · `rebase`) | `squash` |
| `ALLOWED_USER_IDS` | 조작할 수 있는 Slack 사용자 ID. 예 `'["U0123", "U0456"]'` | `[]` (채널의 누구나) |

## 로컬 실행

```bash
cd slack-bot
cp .env.example .env   # 토큰을 채웁니다
uv sync
uv run python -m app.main
```

검사 명령: `uv run ruff check`, `uv run ruff format --check`, `uv run pytest` (CI `slack-bot` 잡과 같음)

## 버튼 약속

버튼은 `slack-notify` 액션이 만들고 봇이 해석합니다. 한쪽을 바꾸면 다른 쪽도 같이 바꿉니다.

| 버튼 | `action_id` | `value` |
|---|---|---|
| 승격 · 취소 · 되돌리기 | `rollout_promote`, `rollout_abort`, `rollout_undo` | `<서비스|all>@<대상>.<환경>` (예 `demo-app-be@aws.test`). 알림의 `target`과 같다 |
| 머지 | `pr_merge` | 대상 레포의 PR 번호 |
| 운영 승인 · 거절 | `deploy_approve`, `deploy_reject` | `<워크플로 실행 ID>@<GitHub environment>` (예 `123456@prod`). `deploy.yml`의 gate가 regulated 운영 배포마다 올린다 |

명령: `/rollout <promote|abort|undo> <서비스|all>@<대상>.<환경>` (예 `/rollout promote all@aws.test`)

## PR 준비 알림

janto PR의 검사가 통과하면 재사용 워크플로 `pr-ready.yml`이 PR 제목 · 작성자 · 변경 규모와 머지 버튼을 올립니다. draft, `yolo/**` 브랜치(T8 자동 머지), fork PR은 알리지 않습니다. 대상 레포의 PR 워크플로에서 검사 job 뒤에 붙입니다.

```yaml
  pr-ready:
    needs: checks
    if: github.event_name == 'pull_request'
    uses: SoftBank-Hackathon-2026-Team-Amethyst/one-tatchi-platform/.github/workflows/pr-ready.yml@vX.Y.Z
    with:
      template-ref: vX.Y.Z
    secrets:
      SLACK_BOT_TOKEN: ${{ secrets.SLACK_BOT_TOKEN }}
```

## 운영 승인 버튼 설정 (한 번만)

봇은 GitHub App이라 environment의 required reviewers가 될 수 없습니다. 대신 대상 레포 `prod` environment의 **custom deployment protection rule**로 등록하고, 버튼을 누르면 그 규칙을 승인 · 거절합니다. 누른 사람은 승인 코멘트(`slack:<이름>(<ID>)`)로 남습니다.

1. GitHub App 권한: Repository **Deployments** 읽기 · 쓰기, 이벤트 **Deployment protection rule** 구독(웹후크를 켜야 고를 수 있다. 봇은 웹후크를 받지 않으니 주소는 아무 곳이어도 된다)
2. 대상 레포 Settings → Environments → `prod` → Deployment protection rules에서 앱을 켠다. Slack만으로 승인하려면 required reviewers는 끈다(둘 다 켜면 둘 다 필요). 관리자는 긴급할 때 화면에서 우회할 수 있다

## 대상 레포 호출 예시

봇은 아래 입력으로 대상 레포의 `rollout.yml`을 실행합니다. 대상 레포는 대상 · 환경을 클러스터 · 네임스페이스로 바꿔 platform 재사용 워크플로에 넘깁니다.

```yaml
# demo-app/.github/workflows/rollout.yml
name: rollout
on:
  workflow_dispatch:
    inputs:
      action: { type: choice, options: [promote, abort, undo], required: true }
      release: { description: "서비스 이름 또는 all", type: string, default: all }
      target: { type: choice, options: [aws, onprem], default: aws }
      environment: { type: choice, options: [test, prod], default: test }
      requested_by: { type: string, required: false }

permissions:
  contents: read
  id-token: write

jobs:
  rollout:
    uses: SoftBank-Hackathon-2026-Team-Amethyst/one-tatchi-platform/.github/workflows/rollout.yml@v1.2.0
    with:
      action: ${{ inputs.action }}
      release: ${{ inputs.release }}
      services: demo-app-be demo-app-fe
      target: ${{ inputs.target }}
      environment: ${{ inputs.environment }}
      # 클러스터 이름은 대상별로 정한 값 (aws: T24의 EKS, onprem: T3의 k3d context)
      cluster: ${{ inputs.target == 'aws' && '<eks-cluster>' || 'k3d-onetouch' }}
      namespace: ${{ inputs.environment }}
      requested-by: ${{ inputs.requested_by }}
      template-ref: v1.2.0
    secrets:
      SLACK_BOT_TOKEN: ${{ secrets.SLACK_BOT_TOKEN }}
```

## 배포

`deploy/values.yaml`은 App Chart 값입니다. Secret `slack-bot-env`에 `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `GITHUB_APP_CLIENT_ID`, `GITHUB_APP_PRIVATE_KEY`를 넣고, `GITHUB_REPOSITORY`는 `env`로 줍니다. 어디에 띄울지(EKS · 맥북 k3d · 로컬)는 T26에서 정합니다.
