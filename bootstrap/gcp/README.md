# GCP bootstrap

프로젝트 `one-tatchi-gejkm`의 state와 CI WIF를 관리한다. AWS bootstrap · 감사 로그를 변경하지 않는다.

1. `gcloud --configuration onetatchi auth print-access-token` 결과를 출력하지 않고 `GOOGLE_OAUTH_ACCESS_TOKEN` 환경변수에 넣는다. ADC를 변경하지 않는다.
2. 최초 실행은 이 디렉터리를 임시 디렉터리에 복사하고 backend 블록만 제거한 뒤 local state로 apply한다. 모듈 source는 원본의 절대 경로로 지정한다.
3. 원본에서 `terraform init -backend-config=bucket=one-tatchi-gejkm-tfstate`를 실행한다. 임시 local state를 `terraform state push`로 GCS의 `bootstrap/gcp` prefix로 이전하고 `terraform plan`으로 차이가 없는지 확인한다. bootstrap state를 Git에 넣지 않는다.
4. `terraform output -json github_variables`의 각 항목을 demo-app의 GitHub Actions Variables에 등록한다. 기존 AWS · DEPLOY_TARGET 변수는 유지한다.

state 버킷은 공개 접근 차단 · 버전 관리를 켜고 삭제를 보호한다. local state의 안전한 이전을 확인한 뒤 임시 사본을 삭제한다. 이후 변경은 이 원본 루트의 GCS state로 반영한다.
