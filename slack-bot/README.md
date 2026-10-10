# slack-bot

배포 파이프라인 결과를 Slack 채널에서 받고, 같은 자리에서 버튼으로 조작을 요청하는 봇입니다 (T26).

- **알림**: 워크플로가 `.github/actions/slack-notify`로 배포, 승격, 되돌리기, 인프라 반영 결과를 채널에 올립니다.
- **Blue-Green 조작**: 알림의 승격 · 취소 · 되돌리기 버튼이나 `/rollout` 명령을 봇이 받아 대상 레포의 rollout 워크플로를 실행합니다. 그 워크플로는 platform 재사용 워크플로 `rollout.yml`을 호출합니다.
- **PR 리뷰 승인 · 머지**: janto PR 알림의 리뷰 승인 버튼은 누른 사람이 연결한 **자기 GitHub 계정**으로 Approve 리뷰를 남깁니다(CODEOWNERS 리뷰는 봇 신원으로는 인정되지 않아서). 머지 버튼은 봇이 PR을 머지하고 누른 사람을 PR 코멘트로 남깁니다. 필수 검사 등 머지 규칙은 GitHub 브랜치 보호가 그대로 지키고, 거부되면 GitHub의 사유를 그대로 보여 줍니다.

봇은 클러스터 권한이 없습니다. 실제 반영은 배포 파이프라인만 하고, 요청한 Slack 사용자는 감사 로그의 `requested_by`에 남습니다.

```
대상 레포 워크플로 ──알림(승격 · 취소 · 머지 버튼)──▶ Slack 채널
                                                     │ 버튼 클릭 또는 /rollout
                                                     ▼
대상 레포 rollout 워크플로 ◀──workflow_dispatch── slack-bot (Socket Mode)
  └─ platform rollout.yml ──결과 알림(되돌리기 버튼)──▶ Slack 채널
```

Socket Mode를 쓰므로 봇이 Slack으로 연결을 겁니다. 공개 엔드포인트와 Ingress가 필요 없어 클러스터 · 맥북 · 로컬 어디서든 돌릴 수 있습니다.

## 알림 말투

우사기의 짧은 감탄사에서 착안해 알림 첫 줄에 성격을 더합니다. [ABEMA의 캐릭터 소개](https://times.abema.tv/articles/-/10149205)에 나오는 「ヤハ」「ウラ」「ハァ？」「フゥン」을 한국어로 옮겼습니다. 감탄사와 작업 상태의 연결은 이 봇의 표현이며, 원작의 공식 의미나 번역을 뜻하지 않습니다.

| 상황 | 첫 줄 예시 |
|---|---|
| PR 검사 통과 | ✅ 야하! PR 검사 통과! |
| 배포 성공 | ✅ 야하! 배포 완료! 승격 여부는 아래 결과를 확인해 주세요. |
| 승격 성공 | ✅ 우라라! 승격 완료! |
| 운영 승인 대기 | ⏳ 우라! 운영 승인 대기 중. 대상과 버전을 확인해 주세요. |
| 실패 | ❌ 하아…? 작업 실패. 실행 로그를 확인해 주세요. |
| 취소 | ⚠️ 후웅… 작업이 취소됐습니다. |

다음 줄의 작업명·대상·커밋·원본 상태와 본문의 AI 판단·오류·실행 링크는 그대로 표시합니다. 버튼과 확인 창도 명확한 한글을 유지합니다. 배포 성공만으로 트래픽 승격을 선언하지 않습니다.

문구는 [slack-notify 액션](../.github/actions/slack-notify/action.yml)에서 관리합니다. 실제 알림에 적용하려면 변경이 포함된 플랫폼 버전을 릴리스하고 대상 레포의 워크플로 참조와 `template-ref`를 갱신해야 합니다. 이 문구 변경에는 Slack 웹 설정이나 봇 컨테이너 재배포가 필요하지 않습니다.

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
| `GITHUB_APP_CLIENT_SECRET` | 리뷰 승인용 사용자 토큰을 만료 전에 갱신할 때만 필요 (선택). 없으면 만료 뒤 다시 연결 | 빈 값 |
| `LINK_STORE_PATH` | Slack 사용자 → GitHub 계정 연결 저장 파일. 비우면 메모리만. 파드 `/tmp`는 재시작하면 비워진다 | `/tmp/github-links.json` |

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
| 리뷰 승인 | `pr_approve` | 대상 레포의 PR 번호. 누른 사람의 GitHub 계정으로 Approve 리뷰를 남긴다 |
| 머지 | `pr_merge` | 대상 레포의 PR 번호 |
| 운영 승인 · 거절 | `deploy_approve`, `deploy_reject` | `<워크플로 실행 ID>@<GitHub environment>` (예 `123456@prod`). `deploy.yml`의 gate가 regulated 운영 배포마다 올린다 |

명령: `/rollout <promote|abort|undo> <서비스|all>@<대상>.<환경>` (예 `/rollout promote all@aws.test`), `/github-link [reset]`(리뷰 승인용 GitHub 계정 연결)

## PR 준비 알림

janto PR의 검사가 통과하면 재사용 워크플로 `pr-ready.yml`이 PR 제목 · 작성자 · 변경 규모와 **리뷰 승인 · 머지** 버튼을 올립니다. draft, `yolo/**` 브랜치(T8 자동 머지), fork PR은 알리지 않습니다. 대상 레포의 PR 워크플로에서 검사 job 뒤에 붙입니다.

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

## 리뷰 승인 버튼 설정 (한 번만)

`.deploy/config.yaml` · `CODEOWNERS`를 바꾸는 PR은 코드 오너 리뷰(T6)가 있어야 머지됩니다. 봇은 GitHub App이라 봇이 남긴 리뷰는 코드 오너 리뷰가 아닙니다. 그래서 리뷰 승인 버튼은 **누른 사람의 GitHub 계정**으로 리뷰를 제출합니다.

1. GitHub App 설정 → General → **Enable Device Flow**를 켭니다. 공개 콜백 주소가 필요 없는 방식입니다. 권한은 기존 **Pull requests** 쓰기로 충분합니다(사용자 토큰은 앱 권한 ∩ 사용자 권한).
2. (선택) 사용자 토큰 만료가 켜져 있으면(기본 8시간) 봇 Secret에 `GITHUB_APP_CLIENT_SECRET`을 넣어야 봇이 만료 전에 갱신합니다. 없으면 만료 뒤 버튼을 눌렀을 때 다시 연결합니다. 토큰 만료 자체를 끄는 것(Optional features → User-to-server token expiration)도 됩니다.
3. Slack 앱 매니페스트에 `/github-link` 명령을 추가합니다(선택. 버튼을 누르면 연결 안내가 나오므로 없어도 됩니다).

처음 버튼을 누르면 봇이 코드와 주소(`https://github.com/login/device`)를 본인에게만 보여 줍니다. 입력하면 "연결했어요" 알림이 오고, 버튼을 다시 누르면 승인됩니다. 연결은 `LINK_STORE_PATH` 파일에 남지만 파드 `/tmp`라 재시작하면 다시 연결합니다. PR 작성자 본인이 누르면 GitHub이 거부하고(`Can not approve your own pull request`) 그 사유가 그대로 표시됩니다.

## 운영 승인 버튼 설정 (한 번만)

봇은 GitHub App이라 environment의 required reviewers가 될 수 없습니다. 대신 대상 레포 `prod` environment의 **custom deployment protection rule**로 등록하고, 버튼을 누르면 그 규칙을 승인 · 거절합니다. 누른 사람은 승인 코멘트(`slack:<이름>(<ID>)`)로 남습니다.

protection rule을 승인한 사람은 API로 다시 읽을 수 없습니다. 그래서 봇은 승인 · 거절한 뒤 배포하는 커밋에 표지 코멘트(`<!-- one-tatchi-approval run=<실행 ID> environment=<환경> state=<approved|rejected> by=slack:<이름>(<ID>) -->`)를 남기고, `deploy.yml`이 이 표지를 읽어 운영 배포 감사 로그의 `requested_by`에 넣습니다. 그래서 GitHub App에 Repository **Contents** 쓰기 권한도 필요합니다(PR 머지에도 필요한 권한입니다).

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

`deploy/values.yaml`은 App Chart 값입니다. Secret `slack-bot-env`에 `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `GITHUB_APP_CLIENT_ID`, `GITHUB_APP_PRIVATE_KEY`를 넣고, `GITHUB_REPOSITORY`와 `ALLOWED_USER_IDS`(비밀이 아니라서)는 `env`로 줍니다. 어디에 띄울지(EKS · 맥북 k3d · 로컬)는 T26에서 정합니다.
