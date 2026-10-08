# 변경 기록

버전은 [시맨틱 버전](https://semver.org/lang/ko/)을 따른다. demo-app은 이 버전으로 모듈(`?ref=`), 재사용 워크플로(`@`), App Chart(`--version`)를 참조한다.

- **MAJOR**: 모듈 입력 · 출력, 워크플로 입력, 차트 값 이름이 바뀌어 demo-app 쪽 수정이 필요한 변경
- **MINOR**: 하위 호환 기능 추가 (새 입력, 새 벤더 구현체)
- **PATCH**: 버그 수정

릴리스 방법: 이 파일에 항목을 추가하고 main에 머지한 뒤 `git tag vX.Y.Z && git push origin vX.Y.Z`. `release.yml`이 차트를 GHCR에 올리고 메이저 태그(`v1`)를 옮긴 뒤, 대상 레포(demo-app)에 알려 버전 업데이트 PR이 열리게 한다. 버전 항목 제목은 `## vX.Y.Z` 형식을 지킨다(PR 본문에 그 구간이 붙는다).

## Unreleased

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
