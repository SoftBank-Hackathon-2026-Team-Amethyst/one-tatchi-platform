---
name: deploy-provision
description: 분석 결과(.deploy/plan.yaml, .deploy/report.md)로 대상 레포에 배포 산출물을 만든다. Dockerfile, App Chart 값 파일, 대상별 Terraform Terraform 루트(원격 모듈 태그 참조), .deploy/smoke.json, 재사용 워크플로 호출부, CODEOWNERS. 아무것도 apply하지 않는다. janto-deploy / yolo-deploy의 산출물 단계이거나, 설정이 바뀐 뒤 산출물을 다시 맞출 때 쓴다.
---

# deploy-provision

`.deploy/plan.yaml`의 `target` · `services`로 배포 산출물을 만들어 작업 트리에 둔다. **apply · push · PR은 하지 않는다**(호출한 스킬이 한다). 템플릿 본문은 platform 레포에 있고, 여기서는 변수 값과 호출부만 만든다.

## 입력

- `.deploy/plan.yaml`(`target`, `services`), `.deploy/config.yaml`(`template_version`, `compliance`), `.deploy/report.md`. `plan.yaml` · `report.md`가 없으면 `deploy-analyze`를 먼저 하라고 알리고 멈춘다.
- `.deploy/analysis/codebase.md`(필요한 코드 수정, 검사 입력), `.deploy/analysis/service.md`(smoke 요청 후보).
- 이 스킬의 `templates/`(산출물 원형)과 [references/artifacts.md](references/artifacts.md)(파일별 규칙과 자리표시자 표).
- 모드(janto · yolo)는 로컬 검증 실패 때 사람에게 물을지(janto) 바로 고칠지(yolo)만 가른다.

## 순서

`<skill-dir>`은 이 `SKILL.md`가 있는 실제 경로다.

1. **템플릿 버전.** `template_version`이 없으면 platform의 최신 태그로 정한다. 이미 있으면 그대로 둔다(올리는 건 `template-update` PR의 몫). `@@TEMPLATE_VERSION@@`은 `vX.Y.Z`, `@@CHART_VERSION@@`은 `X.Y.Z`.
   ```sh
   git ls-remote --tags https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/one-tatchi-platform.git 'v*.*.*' | sed 's#.*refs/tags/##' | sort -V | tail -1
   ```
2. **필요한 코드 수정.** 보고서의 "필요한 코드 수정"을 앱에 적용한다. 범위는 앱 코드 · Dockerfile · 설정 파일. 수정 뒤 앱의 lint · test · build를 돌린다.
   - 서비스마다 `Dockerfile`과 `.dockerignore`. 규칙은 artifacts.md "Dockerfile".
   - 로컬 DB(SQLite 등)는 환경변수로 접속하는 운영 DB로. 헬스체크 경로가 없으면 추가. `pnpm lint` · `pnpm build`(Node) 또는 `ruff` · `pytest`(Python) 명령이 없으면 추가.
3. **템플릿 렌더.** 자리표시자 값을 정하고(artifacts.md 표) 아래로 렌더한다. 기존 파일이 있으면 덮어쓰기 전에 diff를 보고, 사람이 손으로 바꾼 흔적(주석 · 추가 입력)이 있으면 그 부분을 유지한다.
   ```sh
   "<skill-dir>/scripts/render.sh" "<skill-dir>/templates/<경로>.tmpl" "<대상 경로>" KEY=값 KEY=값 …
   ```
   | 산출물 | 템플릿 | 만들 때 |
   |---|---|---|
   | `.github/workflows/deploy.yml` | `templates/.github/workflows/deploy.yml.tmpl` | 항상 |
   | `.github/workflows/template-update.yml` | `templates/.github/workflows/template-update.yml.tmpl` | 항상 |
   | `.github/workflows/infra.yml` | `templates/.github/workflows/infra.yml.tmpl` | `target: aws` |
   | `.github/CODEOWNERS` | `templates/.github/CODEOWNERS.tmpl` | 없을 때만. 있으면 건드리지 않는다 |
   | `deploy/values-<서비스>.yaml` | `templates/deploy/values-service.yaml.tmpl` | 서비스마다 |
   | `deploy/<대상>/values.yaml` | `templates/deploy/<대상>/values.yaml.tmpl` | 대상마다 |
   | `infra/envs/aws/*` | `templates/infra/envs/aws/*.tmpl` | `target: aws` |
   | `infra/envs/onprem/*` | `templates/infra/envs/onprem/*.tmpl` | `target: onprem` |
   | `.deploy/smoke.json` | `templates/.deploy/smoke.json.tmpl` | 항상. 서비스 분석의 smoke 후보로 채운다. `database: true`인 서비스는 헬스 경로에 `expect_body`로 DB 연결 조건(예: `{"database": "connected"}`)을 넣는다 |
   | `.deploy/config.yaml` | 직접 편집 | 없을 때 `template_version` · 주석을 추가. 있으면 건드리지 않는다(CODEOWNERS 리뷰 대상). `compliance`는 `write_brief.py`만 쓴다 |
   | `.deploy/plan.yaml` | 읽기만 | `deploy-analyze`가 쓴 인계값 |
4. **값 파일 다듬기.** 렌더한 `deploy/values-<서비스>.yaml`에 서비스별 값(`env`, `envFromSecrets`, `migration`, `ingress.paths`, `writablePaths`, `resources`)을 `plan.yaml`의 `services`와 코드베이스 분석대로 채운다. App Chart가 받는 키만 쓴다(`charts/app/values.yaml`이 기준). 비밀값은 쓰지 않는다.
5. **로컬 검증.** 모두 통과해야 다음으로 간다.
   ```sh
   "<skill-dir>/scripts/check-artifacts.sh" .          # 자리표시자 잔존 · 버전 표기 일치 · 필수 파일 · smoke.json 형식
   docker build -t check:<서비스> <서비스 경로>          # 서비스마다 (이미지가 빌드되는지만. push하지 않는다)
   terraform -chdir=infra/envs/<대상> fmt -check && terraform -chdir=infra/envs/<대상> init -backend=false && terraform -chdir=infra/envs/<대상> validate
   ```
   `terraform init -backend=false` · `validate`는 origin/main 대비 `infra/` 변경이 있거나 `infra/envs/<대상>`을 이번에 렌더했을 때만 돌린다(모듈 다운로드가 30초 이상). 변경이 없으면 `fmt -check`만 하고 기록에 "init · validate 생략(infra 변경 없음)"을 적는다. 이미지 빌드 · lint · test · 검증 명령은 서로 독립이라 병렬로 돌린다.
   실패하면 산출물이나 앱 코드를 고친다. janto는 원인과 고칠 방법을 사용자에게 보여 주고 승인받아 고친다. yolo는 바로 고치고 기록에 적는다.
6. **기록.** `.deploy/log/<YYYYMMDD-HHMMSS>-provision.md`: 만든 · 고친 파일 목록, 템플릿 버전, 검증 명령과 결과, 소요 시간.

## 끝난 상태

- 서비스마다 Dockerfile · `.dockerignore` · `deploy/values-<서비스>.yaml`
- `deploy/<대상>/values.yaml`, `infra/envs/<대상>/`, `.deploy/smoke.json`, 워크플로 호출부, CODEOWNERS
- `.deploy/config.yaml`의 `template_version`과 워크플로 `@vX.Y.Z` · `template-ref` · `chart-version` · 모듈 `?ref=`가 모두 같은 버전
- `check-artifacts.sh`, 이미지 빌드, `terraform validate` 통과. **아무것도 반영되지 않았다**(반영은 머지 뒤 파이프라인)

## 사람이 할 일 (스킬이 못 하는 것)

호출한 스킬이 PR 본문이나 마무리 보고에 적는다.

- yolo 자동 PR: `BOT_CLIENT_ID` 변수와 `BOT_PRIVATE_KEY` 시크릿. GitHub App은 대상 레포에 설치하고 Contents · Pull requests 쓰기, Actions 읽기 권한을 준다. 저장소 auto-merge와 rebase merge가 활성화돼 있어야 한다. 리뷰 정책은 우회하지 않는다.
- GitHub Variables: `DEPLOY_TARGET`, AWS면 `AWS_REGION` · `AWS_PLAN_ROLE_ARN` · `AWS_DEPLOY_ROLE_ARN` · `TF_STATE_BUCKET` · `AUDIT_LOG_BUCKET`(bootstrap 출력), Slack 알림이면 `SLACK_CHANNEL_ID`와 시크릿 `SLACK_BOT_TOKEN`, AI 승격 판단이면 시크릿 `ANTHROPIC_API_KEY`
- Environments: `test`, `prod`(승인자 지정), `prod-auto`(main만)
- 온프레미스: 기본 self-hosted runner 라벨은 기존 `onprem`을 유지한다. 추가 기기는 `onprem-<profile>`로 구분한다. v2는 `scripts/onprem/README.md`에 따라 `onpremctl.py terraform`으로 인증정보를 메모리에서 공급하며, 기존 state는 apply 전에 암호화 백업·이전을 수행한다. v1 참조는 기존 계약을 유지한다. 기기마다 cluster·state를 분리하고 기존 state 없이 클러스터를 재생성하지 않는다.
- 첫 AWS 인프라: `infra.yml`이 PR에서 plan, 머지에서 apply. 머지 전에 plan 코멘트의 비용을 확인
