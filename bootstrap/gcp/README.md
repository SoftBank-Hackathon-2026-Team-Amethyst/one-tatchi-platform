# GCP bootstrap

프로젝트 `one-tatchi-gejkm`의 state와 CI WIF를 관리한다. AWS bootstrap · 감사 로그를 변경하지 않는다.

1. `gcloud --configuration onetatchi auth print-access-token` 결과를 출력하지 않고 `GOOGLE_OAUTH_ACCESS_TOKEN` 환경변수에 넣는다. ADC를 변경하지 않는다.
2. 최초 실행은 이 디렉터리를 임시 디렉터리에 복사하고 backend 블록만 제거한 뒤 local state로 apply한다. 모듈 source는 원본의 절대 경로로 지정한다.
3. 원본에서 `terraform init -backend-config=bucket=one-tatchi-gejkm-tfstate`를 실행한다. 임시 local state를 `terraform state push`로 GCS의 `bootstrap/gcp` prefix로 이전하고 `terraform plan`으로 차이가 없는지 확인한다. bootstrap state를 Git에 넣지 않는다.
4. `terraform output -json github_variables`의 각 항목을 demo-app의 GitHub Actions Variables에 등록한다. 기존 AWS · DEPLOY_TARGET 변수는 유지한다.

state 버킷은 공개 접근 차단 · 버전 관리를 켜고 삭제를 보호한다. local state의 안전한 이전을 확인한 뒤 임시 사본을 삭제한다. 이후 변경은 이 원본 루트의 GCS state로 반영한다.

## T17 중앙 Grafana 최초 연결 권한

프로젝트 관리자(Owner)가 이 저장소 main에서 수행한다. 기존 GCS backend와 같은 state를 사용하며 새 local state를 만들지 않는다. 개인 Editor 계정을 Owner로 바꿀 필요는 없다.

```bash
# 관리자 본인 계정으로 로그인한 onetatchi gcloud configuration 사용
export GOOGLE_OAUTH_ACCESS_TOKEN="$(gcloud --configuration onetatchi auth print-access-token)"
terraform -chdir=bootstrap/gcp init -backend-config=bucket=one-tatchi-gejkm-tfstate
terraform -chdir=bootstrap/gcp plan -var=enable_grafana_wif=true -out=/tmp/t17-gcp-bootstrap.tfplan
# 새 IAM binding 1개만 추가되고 기존 리소스 삭제/교체가 없는지 확인한 뒤
terraform -chdir=bootstrap/gcp apply /tmp/t17-gcp-bootstrap.tfplan
unset GOOGLE_OAUTH_ACCESS_TOKEN
```

추가되는 것은 `one-tatchi-gha-deploy` 서비스 계정의 `roles/iam.workloadIdentityPoolAdmin`이다. CI가 Grafana 전용 OIDC pool/provider를 생성·유지하기 위한 권한이며, plan 계정의 권한이나 GitHub 신뢰 조건은 바꾸지 않는다. `enable_grafana_wif=true`를 관리자 로컬 tfvars에도 유지해야 다음 bootstrap apply에서 되돌아가지 않는다. 토큰·plan·state는 공유하거나 커밋하지 않는다.

이후 GCP 앱 루트의 `observability` 입력에 중앙 EKS OIDC issuer를 설정해 PR 파이프라인으로 적용한다. Grafana 서비스 계정 자체는 Monitoring Viewer만 받는다. 전체 연결 순서는 [관측 안내](../../docs/observability.md)를 따른다.
