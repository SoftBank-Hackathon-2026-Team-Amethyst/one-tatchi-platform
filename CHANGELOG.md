# 변경 기록

버전은 [시맨틱 버전](https://semver.org/lang/ko/)을 따른다. demo-app은 이 버전으로 모듈(`?ref=`), 재사용 워크플로(`@`), App Chart(`--version`)를 참조한다.

- **MAJOR**: 모듈 입력 · 출력, 워크플로 입력, 차트 값 이름이 바뀌어 demo-app 쪽 수정이 필요한 변경
- **MINOR**: 하위 호환 기능 추가 (새 입력, 새 벤더 구현체)
- **PATCH**: 버그 수정

릴리스 방법: 이 파일에 항목을 추가하고 main에 머지한 뒤 `git tag vX.Y.Z && git push origin vX.Y.Z`. `release.yml`이 차트를 GHCR에 올리고 메이저 태그(`v1`)를 옮긴 뒤, 대상 레포(demo-app)에 알려 버전 업데이트 PR이 열리게 한다. 버전 항목 제목은 `## vX.Y.Z` 형식을 지킨다(PR 본문에 그 구간이 붙는다).

## Unreleased

## v2.0.1

- macOS runner의 설치/작업 경로에 공백이 있으면 설치 전에 중단한다. 실제 Actions Bash 단계에서 경로가 잘려 실행에 실패한 사례를 반영하고 공백 없는 고정 경로를 안내한다 (T27).

## v2.0.0

- **호환되지 않는 변경 (T27):** onprem은 Terraform 1.11+와 관리 도구의 ephemeral 인증/DB 비밀번호 입력을 요구한다. cluster의 인증서/개인키 출력과 DB random_password state를 제거한다. 기존 state는 암호화 백업을 검증한 뒤 이전한다.
- macOS launchd의 AC 잠자기 방지·Docker/k3d 복구·공식 runner 서비스와 기기별 배포/승격 대상 검증을 추가한다. [설치·이전 절차](scripts/onprem/README.md).
- checks의 단일 amd64/arm64 OCI 빌드와 각각의 Trivy 검사를 통과한 동일 run artifact만 발행한다. deploy의 재빌드를 제거하고 digest로 고정한다. prod는 test의 동일 digest 승격을 확인한다.
- 현재 터널의 환경·서비스·실행 로그를 검증하며 URL 누락이나 조회 오류는 실패한다. 기존 PostgreSQL StatefulSet/PVC는 유지한다 (ADR 0012).
- 선택형 `.deploy/config.yaml`의 `infra_versions`로 기존 클라우드 루트 버전을 유지할 수 있다. v2는 자동 전체 루트 갱신 알림을 보내지 않는다. 기존 v1 호출과 태그는 유지된다.

## v1.16.0

- `slack-bot` · `deploy.yml` (T26): 운영 승인 · 거절 버튼을 누른 사람을 배포 커밋에 표지 코멘트로 남기고, 운영 배포 감사 로그의 `requested_by`에 기록한다. 표지가 없으면 지금처럼 actor로 남는다. 봇 `deploy/values.yaml`에 `ALLOWED_USER_IDS`(팀원 5명)를 넣는다.
- `yolo-deploy`: push SHA에 맞는 Actions 실행 추적, 보호 경로 검사, 최대 3회 수정 커밋·push 및 중단 후 상태 복원 도구 추가. 기록만을 위한 추가 배포 제거 (T14)

## v1.15.0

- 선택형 중앙 Prometheus와 온프레미스 TLS remote-write, 서비스 HTTP·리소스 대시보드를 추가한다. 수신 비밀번호는 Kubernetes Secret에만 주입한다 (T17).
- GCP Cloud Monitoring은 EKS 서비스 계정의 단기 OIDC 토큰을 이용한다. 서비스 계정 키 파일은 만들지 않는다. 기존 CloudWatch 전용 모듈 호출은 그대로 동작한다.
- AI 판단의 `metrics.json`과 관찰 창을 CloudWatch Logs에 게시한다. 게시 실패는 원래 판단·배포 결과를 바꾸지 않으며 Actions artifact를 보존한다.
- App Chart에 선택형 지표 수집·GCP PodMonitoring·FE nginxlog exporter를 추가한다. exporter는 원본 v1.11.0을 Go 1.27.2로 재빌드해 플랫폼 버전으로 배포한다.

## v1.14.0

- `deploy.yml` (T8): `yolo-auto-merge: true`로 test의 모든 서비스가 해당 커밋으로 승격됐음을 확인한 뒤 GitHub App으로 main PR을 만든다. PR 검사 완료를 기다리고 `--match-head-commit`으로 검증한 head에 rebase 자동 머지를 요청한다. 일반 리뷰와 CODEOWNERS 규칙은 유지한다.
- `promote-mode: branch`: yolo push 및 yolo PR이 머지된 main push는 auto, janto와 수동 재실행은 manual. GitHub rebase는 SHA를 바꾸므로 main에서 test를 다시 검증한 뒤 같은 이미지를 prod에 쓴다.
- 스킬 호출부는 참조 버전에 맞춰 새 입력을 렌더한다. yolo 실행 기록은 push 전에 쓰고, 완료 기록을 위한 재push 대신 Actions artifact와 PR에 결과를 남긴다.
- `target·services`는 `.deploy/plan.yaml`, 보호 값 `compliance·template_version`은 `.deploy/config.yaml`로 분리한다 (T13).

## v1.13.1

- GCP Monitoring 대시보드의 열 수를 API가 반환하는 JSON 문자열로 지정해, 적용 후에도 같은 변경이 반복되는 문제를 해결한다(T4).

## v1.13.0

- GCP 구현체(T4): GKE · Artifact Registry · Cloud SQL · Secret Manager · Cloud Monitoring과 WIF/GCS bootstrap을 추가한다. 기존 AWS · onprem 기본 설정은 유지한다.
- `infra` · `kube-access` · `image-push` · `deploy` · `rollout`에 GCP 인증, state, 이미지 주소, 클러스터 접속 분기를 추가한다.
- App Chart에 선택적인 Service/Ingress annotations를 추가해 GKE 기본 Ingress와 NEG를 지원한다. ALB 기본 렌더링은 유지한다.

## v1.12.0

- `deploy.yml`: prod 배포 전에 같은 커밋이 test에서 승격(stable)됐는지 확인하고 기다린다. 입력 `require-test-promotion`(기본 true), `test-namespace`(기본 test), `promotion-wait-seconds`(기본 600). Paused(승격 대기)인 test를 두고 운영으로 넘어가던 흐름을 막는다 (T5, 리뷰 지점 3)
- `deploy.yml`(onprem): 터널 외부 주소를 찾지 못하면 실패로 끝낸다 (전에는 주소 `/`로 성공 처리) (T27)
- `image-push`: 빌드한 이미지를 push 전에 Trivy(HIGH 이상, 수정 버전 있는 것, `.trivyignore`)로 검사한다. checks의 `image-scan`은 다른 runner에서 따로 빌드한 이미지라 배포 이미지와 같지 않았다. `deploy.yml`에 `setup-trivy` 단계 추가 (T5 · T27)

## v1.11.0

- 재사용 워크플로 `pr-ready.yml` (T26): janto PR의 검사가 통과하면 Slack에 "PR 준비" 알림과 머지 버튼. draft · `yolo/**` · fork PR은 제외

- `skills/`: 에이전트 스킬 추가 (T13). `/janto-deploy`(기능 브랜치 + main PR), `/yolo-deploy`(`yolo/<기능>` push, 검사 실패 수정 루프 규칙), `deploy-analyze`(T15 브리프 + 분석기 5개 + 보고서 · `config.yaml`의 `target` · `services`), `deploy-provision`(산출물 템플릿 · `render.sh` · `check-artifacts.sh`), `deploy-release` · `deploy-rollback`(`rollout.yml` 요청). 스킬은 apply하지 않고 템플릿을 태그로만 참조한다. 설치는 `scripts/install-skills.sh`

## v1.10.0

- Slack 운영 승인 · 거절 버튼 (T26): `deploy.yml` gate가 regulated 운영 배포마다 승인 대기 알림과 버튼을 올리고, 봇이 prod environment의 custom deployment protection rule을 승인 · 거절한다. `slack-notify` 버튼 `approve` · `reject`와 입력 `approval`, 결과 `waiting` 아이콘 추가

## v1.9.0

- `release.yml`: Slack 봇 이미지 `ghcr.io/<org>/slack-bot:<버전>`(amd64 · arm64)을 함께 올린다. 대상 레포 인프라가 같은 버전으로 띄운다 (T26)
- `slack-bot/manifest.yaml`: 앱 이름 `배포하는 우사기`(봇 `deploy-usagi`), `/rollout` 설명을 따옴표로 감싸 매니페스트 파싱 오류 수정 (T26)
- `deploy.yml`: Paused인 서비스들을 묶어 AI 승격 판단(`promote-judge`)을 거친다. 입력 `promote-mode`(기본 `manual` → 실행은 지금처럼 버튼으로 사람이), `promote-window-seconds`(기본 30, 서비스 동시 관찰), 시크릿 `ANTHROPIC_API_KEY`(선택). Slack 알림에 AI 판단 · 근거, auto 실행은 감사 로그(`requested-by: ai-judge`), 판단 근거는 artifact `promote-judgment-<환경>`. auto로 promote한 뒤에는 버튼이 `undo`만 남는다 (T7)
- `promote-judge`: 입력 `release` → `releases`(공백 구분). 서비스마다 판단하고 하나라도 abort면 전체 abort (ADR 0005). `executed`는 명령이 성공했을 때만 남긴다 (T7)

## v1.8.0

- `deploy.yml`: 입력 `host` 추가 (aws). 서비스 도메인으로 HTTPS(ACM) + 80→443 리다이렉트, 주소도 `https://<host>/`로 알린다. 비우면 지금처럼 ALB 주소로 HTTP (T2)

## v1.7.0

- `deploy.yml`: 서비스마다 job을 나누던 matrix를 없애고 환경당 job 하나에서 배열 순서대로 배포한다. environment 승인이 job마다 걸려 prod 승인을 서비스 수만큼 받아야 했다(BE 승인 후 FE가 다시 승인 대기). 감사 로그 · Slack 대상은 `all@<대상>.<환경>`, concurrency는 대상 · 환경 단위 (T5)
- `image-push`: 빌드 · push 로직을 `push.sh`로 분리 (deploy.yml 반복문과 액션이 같이 쓴다)
- `promote-judge` 액션: Paused green에 smoke 요청 → 지표 · 규칙 판정 → Claude 판단 → promote · abort(auto) 또는 기록(manual). 아직 deploy.yml에서 호출하지 않음 (T7)

## v1.6.1

- `deploy.yml`: aws 대상에서 Ingress가 없는 서비스(FE가 프록시하는 BE 등)의 "주소" 단계가 실패하던 문제. 새 ALB는 주소가 붙을 때까지 최대 150초 기다린다

## v1.6.0

- 운영 관문 (T6): `deploy.yml`이 운영 배포(`environment: prod`) 때 `.deploy/config.yaml`의 `compliance`를 읽어 environment를 고른다. `regulated`(또는 값 없음) → `prod`(사람 승인), `none` → `prod-auto`(자동 반영). 대상 레포에 `prod-auto` environment(main 브랜치만)가 있어야 하고, bootstrap `deploy_environments`에 `prod-auto`를 추가했다
- `checks.yml`: `config-guard` 잡 추가. `.deploy/config.yaml` 형식(`compliance: regulated | none`, `template_version: vX.Y.Z`)을 검사하고, yolo 경로나 AI가 만든 커밋이 `compliance` · `.github/CODEOWNERS`를 바꾸면 실패한다

## v1.5.1

- `cluster/aws`: 지정된 관리자 목록을 KMS 키에도 적용해 plan/apply 실행 역할에 따라 키 정책이 바뀌는 문제 수정 (T24)

## v1.5.0

- `ci_identity/aws`: 벤더 중립 출력 `plan_identity`, `deploy_identity` 추가. 기존 `plan_role_arn`, `deploy_role_arn`은 유지 (T24)
- `modules/README.md`: AWS 모듈의 공통 출력, 연결 순서와 사전 검증 조건 문서화 (T24)

## v1.4.0

Slack 봇과 롤아웃 워크플로, 템플릿 버전 업데이트 흐름, 서비스 도메인(HTTPS)을 추가했다.

- `slack-bot/`: 사전 검증 봇 이식. GitHub App(`one-tatchi-bot`) 인증, 대상 레포 · 워크플로를 설정값으로, PR 머지 버튼(`pr_merge`) 추가 (T26)
- 재사용 워크플로 `rollout.yml`: Blue-Green 승격 · 취소 · 되돌리기, 감사 로그 `requested-by`
- `slack-notify`: 조작 버튼 value가 알림 `target`(`<서비스|all>@<대상>.<환경>`)이 됨. 입력 `service` 기본값이 `all`에서 빈 값(=target)으로 바뀜. `merge` 버튼과 입력 `pr` 추가
- 재사용 워크플로 `template-update.yml`: 새 태그가 나오면 대상 레포의 버전 표기(`template_version`, `uses@`, `template-ref`, `chart-version`, 모듈 `?ref=`)를 올리는 PR을 연다 (T22)
- `release.yml`: 태그 릴리스 후 대상 레포에 `repository_dispatch`(`template-released`)
- `scripts/bump-template-version.sh`, `scripts/changelog-between.sh`와 테스트(`scripts/tests/run.sh`, CI `scripts` 잡)
- `modules/dns`: 서비스 도메인의 존과 와일드카드 인증서(aws 구현). `bootstrap`에서 호출한다 (T2)
- `cluster_addons/aws`: external-dns 애드온. 입력 `dns_zone_id`를 주면 설치한다(비우면 지금과 같음). `chart_versions.external_dns`는 선택
- App Chart: `ingress.host`를 주면 HTTPS(443) + 80→443 리다이렉트, 미리보기 포트도 HTTPS. 비우면 지금과 같은 HTTP

## v1.3.2

- `kube-access`: Docker · Helm 레지스트리 설정을 job 전용 파일로 둔다. macOS self-hosted runner에서 Helm이 OCI 차트를 받을 때 키체인 도우미를 불러 실패하던 문제

## v1.3.1

- `image-push`(onprem): GHCR 인증을 `docker login` 대신 job 전용 설정 파일에 적는다. macOS self-hosted runner(launchd)에서 키체인 저장 실패로 push가 안 되던 문제

## v1.3.0

온프레미스에서 환경별(test · prod) 외부 주소를 따로 연다. 기존 입력은 그대로 동작한다.

- `cluster_addons/onprem`: 선택 입력 `tunnels`(이름 → 터널). Deployment `cloudflared-<이름>`으로 뜬다. `tunnel`은 선택 입력으로 바뀜(기본 null), 출력 `public_url_commands` 추가
- `deploy.yml`: onprem 주소를 `cloudflared-<네임스페이스>` 터널에서 찾는다(없으면 `cloudflared`)

## v1.2.0

배포 워크플로를 배포 대상(target)으로 나눴다. 기존 호출부는 그대로 동작한다(`target` 기본값 `aws`).

- `deploy.yml`: 입력 `target`(aws | onprem). onprem은 맥북 self-hosted runner(`[self-hosted, onprem]`)에서 돌고 이미지는 GHCR에 올린다. `ingress-group`은 aws만 쓰는 선택 입력으로 바뀜
- `deploy.yml`: `deploy/<target>/values.yaml`이 있으면 모든 서비스에 덧붙인다
- `deploy.yml`: 같은 대상 · 환경 · 서비스 배포는 동시에 돌지 않는다(concurrency). green 대기가 10분을 넘으면 실패로 끝낸다(이전에는 통과)
- `deploy.yml`: `helm upgrade --server-side=false` (Helm 4 server-side apply와 Argo Rollouts의 Service selector 충돌)
- 공통 액션: `kube-access`에 `target` 입력과 Helm `v4.3.0` 고정, 이미지 빌드 · push는 새 액션 `image-push`로 분리

## v1.1.0

온프레미스(맥북 k3d) 구현체와 OIDC 제한을 추가했다. demo-app 쪽 수정 없이 올릴 수 있다.

- Terraform 모듈 onprem 구현: `cluster`(k3d), `cluster_addons`(Argo Rollouts · External Secrets · Cloudflare Tunnel), `database`(클러스터 안 Postgres), `registry`(GHCR 주소)
- `ci_identity/aws`: 선택 입력 `allowed_workflow_refs`(OIDC `job_workflow_ref` 제한). 기본값은 제한 없음
- `checks.yml`: 이미지 Trivy, gitleaks, 라이선스 검사 (T11)

## v1.0.0

첫 릴리스. AWS로 사전 검증한 템플릿을 옮겼다.

- Terraform 모듈: network · cluster · cluster_addons · registry · database · ci_identity · observability · secret (aws 구현, gcp · onprem은 자리만)
- Helm 차트: `app`(Blue-Green / rolling, Argo Rollouts), `service-base`, `platform-config`
- 재사용 워크플로: `checks.yml`, `infra.yml`, `deploy.yml`
- 공통 액션: `kube-access`, `audit-log`, `slack-notify`
- `bootstrap/`: state 버킷 · 감사 로그 버킷 · GitHub OIDC 역할
