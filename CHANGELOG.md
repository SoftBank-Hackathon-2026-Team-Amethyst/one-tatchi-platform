# 변경 기록

버전은 [시맨틱 버전](https://semver.org/lang/ko/)을 따른다. demo-app은 이 버전으로 모듈(`?ref=`), 재사용 워크플로(`@`), App Chart(`--version`)를 참조한다.

- **MAJOR**: 모듈 입력 · 출력, 워크플로 입력, 차트 값 이름이 바뀌어 demo-app 쪽 수정이 필요한 변경
- **MINOR**: 하위 호환 기능 추가 (새 입력, 새 벤더 구현체)
- **PATCH**: 버그 수정

릴리스 방법: 이 파일에 항목을 추가하고 main에 머지한 뒤 `git tag vX.Y.Z && git push origin vX.Y.Z`. `release.yml`이 차트를 GHCR에 올리고 메이저 태그(`v1`)를 옮긴다.

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
