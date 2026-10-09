# 배포 산출물 규칙

에이전트가 대상 레포에 만들거나 고치는 파일(설계 문서 6.3). 템플릿 본문(App Chart 보안 설정, 재사용 워크플로의 검사 단계, Terraform 모듈)은 산출물이 아니다.

## 자리표시자

`templates/*.tmpl`의 `@@이름@@`을 `scripts/render.sh`가 바꾼다. 남은 자리표시자는 `check-artifacts.sh`가 잡는다.

| 자리표시자 | 값 | 예 |
|---|---|---|
| `TEMPLATE_VERSION` | `.deploy/config.yaml`의 `template_version` | `v1.9.0` |
| `CHART_VERSION` | 같은 버전, `v` 없이 | `1.9.0` |
| `APP` | 앱 이름 = 레포 이름. 서비스 이름 · 이미지 저장소 · Ingress 그룹 접두사 | `demo-app` |
| `ORG`, `ORG_LOWER` | 대상 레포의 GitHub 조직 또는 사용자. GHCR 경로는 소문자 | `SoftBank-Hackathon-2026-Team-Amethyst`, `softbank-hackathon-2026-team-amethyst` |
| `CLUSTER_NAME` | onprem k3d 클러스터 이름 (context는 `k3d-<이름>`) | `onetouch` |
| `REPOSITORIES_HCL` | 이미지 저장소 이름 목록, HCL 리스트 문자열 | `["demo-app-be", "demo-app-fe"]` |
| `PUBLIC_SERVICE`, `PUBLIC_SERVICE_PORT` | onprem Quick Tunnel이 연결할 서비스와 포트 (`public: true`인 서비스) | `demo-app-fe`, `3000` |
| `DEFAULT_TARGET` | `config.yaml`의 `target`. 레포 변수 `DEPLOY_TARGET`이 없을 때의 기본값 | `onprem` |
| `CLUSTER_AWS` | EKS 클러스터 이름 (`infra/envs/aws` 변수 `name`) | `one-tatchi` |
| `CLUSTER_ONPREM` | self-hosted runner의 kube context (`k3d-<이름>`) | `k3d-onetouch` |
| `HOST_TEST`, `HOST_PROD` | aws만. 서비스 도메인. 없으면 빈 값(ALB 주소로 HTTP) | `yolo.onetatchi.soulee.dev` / `onetatchi.soulee.dev` |
| `SERVICES_JSON` | `deploy.yml` 입력 `services`. `config.yaml`의 `services` 순서대로 `{"name","path","values","migration"?}` | 아래 |
| `NODE_DIRS`, `PYTHON_DIRS`, `IMAGE_DIRS` | `checks.yml` 입력. 런타임별 서비스 경로 JSON 배열 | `["be","fe"]`, `[]`, `["be","fe"]` |
| `DB_INIT` | 테스트 전에 Postgres에 넣을 SQL. 없으면 빈 값 | `db/init.sql` |
| `OWNERS` | CODEOWNERS에 넣을 사람(GitHub 로그인). AI 계정은 넣지 않는다 | `@silano08 @soulee-dev` |
| `SERVICE`, `PORT`, `HEALTH` | 서비스별 값 파일용 | `demo-app-be`, `8000`, `/health` |
| `ACCOUNT_ID`, `REGION`, `DOMAIN` | aws tfvars | `993371732872`, `ap-northeast-2`, `onetatchi.soulee.dev` |
| `DB_NAME` | DB 이름 | `demo` |

`SERVICES_JSON` 예:

```json
[{"name":"demo-app-be","path":"be","values":"deploy/values-be.yaml","migration":"db/init.sql"},
 {"name":"demo-app-fe","path":"fe","values":"deploy/values-fe.yaml"}]
```

## 버전 표기

세 참조가 모두 `template_version`과 같아야 한다. `template-update` 워크플로가 이 형식만 갱신한다(platform README "버전 표기 규칙").

| 위치 | 형식 |
|---|---|
| `.deploy/config.yaml` | `template_version: v1.9.0` |
| 워크플로 `uses:` | `one-tatchi-platform/.github/workflows/<이름>.yml@v1.9.0` |
| 워크플로 입력 | `template-ref: v1.9.0`, `chart-version: 1.9.0` |
| Terraform 모듈 | `one-tatchi-platform.git//modules/<기능>/<벤더>?ref=v1.9.0` |

예외: `template-update.yml` 자신은 `@v1`(움직이는 메이저 태그)로 호출한다.

## 파일별 규칙

### `<서비스>/Dockerfile`, `.dockerignore`

App Chart가 강제하는 조건에서 돌아야 한다.

- **non-root 숫자 UID**: `USER 1000`처럼 숫자. 이름(`USER node`)은 `runAsNonRoot` 검증을 통과하지 못한다. nginx는 `nginxinc/nginx-unprivileged`(UID 101).
- **읽기 전용 루트 파일시스템**: 실행 중 쓰는 경로는 값 파일 `writablePaths`에 선언한다(기본 `/tmp`).
- **다단계 빌드**: 빌드 도구는 빌드 스테이지에만. 런타임 스테이지에서 패키지 매니저(npm · corepack · yarn · pip)를 지워 `image-scan`(Trivy HIGH 이상 차단) 대상을 줄인다.
- **런타임 환경변수를 굽지 않는다**: DB 접속 · 다른 서비스 주소는 실행 시 환경변수. 포트는 `ENV PORT`로 두고 `containerPort`와 맞춘다.
- **lockfile 고정**: `pnpm install --frozen-lockfile`, `uv sync --frozen`. lockfile이 없으면 만들어 커밋한다(`|| pnpm install` 같은 우회 금지).
- **베이스 이미지 보안 패치**: `apk upgrade --no-cache` 등. 취약점 검사가 막은 패키지는 패치 버전이 있으면 올리고, 없으면 `.trivyignore`에 CVE와 근거를 적는다.
- `.dockerignore`: `node_modules`, `.git`, `dist`, `.env*`, 테스트 · 문서. 빈 파일로 두지 않는다.
- 참고 구현: demo-app `be/Dockerfile`(Node 런타임만 남긴 3단계), `fe/Dockerfile`(비특권 nginx).

### `deploy/values-<서비스>.yaml`

App Chart(`charts/app/values.yaml`)가 받는 키만. 모든 배포 대상 공통.

- `image.repository`: `ghcr.io/<org 소문자>/<서비스>`. 파이프라인이 대상에 맞게 덮어쓴다(aws는 ECR). `image.tag`는 비운다(커밋 SHA).
- `containerPort`, `service.port`(다른 서비스가 `http://<서비스>:<port>`로 부른다), `probe.path`.
- `env`: 고정값만. `envFromSecrets`: DB를 쓰면 `[<앱>-db]`(Terraform이 만든 Secret, 키 `DATABASE_URL` · `PG_URL`).
- `migration.enabled: true` + `secretName: <앱>-db`면 파이프라인이 `--set-file migration.sql=<SQL>`로 배포마다 적용한다. SQL은 여러 번 실행해도 안전해야 한다(`IF NOT EXISTS`).
- `ingress.enabled: true`는 외부에 열 서비스(보통 FE)만. BE는 FE가 프록시한다. `ingress.group` · `host`는 파이프라인이 넣는다.
- `deployStrategy`는 기본 `blueGreen`을 유지한다.

### `deploy/<대상>/values.yaml`

대상별 덮어쓰기. 파이프라인이 모든 서비스에 덧붙인다.

- `aws`: `replicas: 1`(노드 파드 한도 17개, Blue-Green과 test · prod 동시 운영).
- `onprem`: `ingress.enabled: false`(Cloudflare Quick Tunnel이 FE Service로 바로 간다), `replicas: 1`.

### `infra/envs/<대상>/`

platform 모듈을 `?ref=@@TEMPLATE_VERSION@@`로 참조하는 Terraform 루트. 모듈 본문을 복사하지 않는다.

- `aws`: S3 backend(bucket은 워크플로가 `-backend-config`로 넣는다, key `<앱>/aws.tfstate`), network · cluster · registry · database(RDS) · cluster_addons · observability, 환경마다 `service-base` 차트. 값은 `terraform.tfvars`(계정 · 리전 · 도메인 · 서비스 이름). `region`은 서울로 고정(팀 SCP).
- `onprem`: 로컬 backend(state는 그 기기에만, `.gitignore`), k3d cluster · cluster_addons(환경마다 Quick Tunnel) · registry(GHCR 주소) · 환경마다 database(StatefulSet) · `service-base`.
- `README.md`: 사람이 실행할 명령(aws는 SSO 로그인 → plan만, apply는 CI; onprem은 기기에서 apply).
- `.terraform.lock.hcl`은 `terraform init -backend=false` 뒤 커밋한다.

### `.deploy/config.yaml`

`template_version`(처음 한 번), `compliance`(`write_brief.py`만), `target` · `services`(`deploy-analyze`). 형식은 `deploy-analyze/references/report-format.md`. `config-guard`가 `compliance`와 `template_version` 형식을 검사한다.

### `.deploy/smoke.json`

승격 판단(T7, `promote-judge`)이 green 미리보기에 보낼 요청. 서비스(release) 이름별 목록.

```json
{
  "demo-app-be": [
    {"method": "GET", "path": "/health", "expect": 200},
    {"method": "GET", "path": "/api/info", "expect": 200},
    {"method": "POST", "path": "/api/guestbook", "expect": 201, "body": {"name": "smoke", "message": "smoke test"}}
  ],
  "demo-app-fe": [
    {"method": "GET", "path": "/", "expect": 200}
  ]
}
```

- `method` 기본 `GET`, `expect` 기본 `200`. 쓰기 요청은 관찰 창에서 한 번만 보내진다. 데이터가 남으므로 테스트용임이 드러나는 값으로.
- FE green의 `/api`는 blue BE로 프록시되므로 FE 목록에는 FE 자체 경로만.
- 파일이 없으면 `GET /health → 200`만 확인한다. 서비스 분석의 smoke 후보에서 읽기 요청 위주로 3~5개.

### `.github/workflows/`

platform 재사용 워크플로를 **호출만** 한다. 검사 단계를 끄는 입력은 없다.

- `deploy.yml`: `pull_request` → checks, `push yolo/**` → checks → test, `push main` → checks → test → prod, `workflow_dispatch` → 대상 골라 재배포. yolo 브랜치에서는 `promote-mode: auto`(AI 판단대로 실행), 그 외 `manual`(사람이 Slack 버튼). **호출부 입력은 참조하는 템플릿 버전에 있는 것만 넘긴다.** 없는 입력을 넘기면 워크플로가 `startup_failure`로 시작하지 못한다(`promote-mode`는 v1.9.0부터). 각 입력이 생긴 버전은 platform `CHANGELOG.md`.
- `infra.yml`(aws): `infra/**` PR → plan 코멘트, main → apply.
- `template-update.yml`: 새 태그 알림 → 버전 올리는 PR.
- 호출부의 `with:` 값만 바꾼다. 새 job을 끼워 검사를 건너뛰게 만들지 않는다.

### `.github/CODEOWNERS`

`.deploy/config.yaml`과 `CODEOWNERS` 자신을 사람 리뷰 대상으로 묶는다(T6). 이미 있으면 그대로 둔다. AI 계정을 오너로 넣지 않는다.

### `.deploy/log/`

스킬 실행마다 `<YYYYMMDD-HHMMSS>-<스킬>.md`. 지우지 않는다.
