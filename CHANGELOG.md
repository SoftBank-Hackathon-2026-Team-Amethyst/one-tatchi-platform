# 변경 기록

버전은 [시맨틱 버전](https://semver.org/lang/ko/)을 따른다. demo-app은 이 버전으로 모듈(`?ref=`), 재사용 워크플로(`@`), App Chart(`--version`)를 참조한다.

- **MAJOR**: 모듈 입력 · 출력, 워크플로 입력, 차트 값 이름이 바뀌어 demo-app 쪽 수정이 필요한 변경
- **MINOR**: 하위 호환 기능 추가 (새 입력, 새 벤더 구현체)
- **PATCH**: 버그 수정

릴리스 방법: 이 파일에 항목을 추가하고 main에 머지한 뒤 `git tag vX.Y.Z && git push origin vX.Y.Z`. `release.yml`이 차트를 GHCR에 올리고 메이저 태그(`v1`)를 옮긴다.

## Unreleased

- `modules/dns`: 서비스 도메인의 존과 와일드카드 인증서(aws 구현). `bootstrap`에서 호출한다 (T2)
- `cluster_addons/aws`: external-dns 애드온. 입력 `dns_zone_id`를 주면 설치한다(비우면 지금과 같음). `chart_versions.external_dns`는 선택
- App Chart: `ingress.host`를 주면 HTTPS(443) + 80→443 리다이렉트, 미리보기 포트도 HTTPS. 비우면 지금과 같은 HTTP

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
