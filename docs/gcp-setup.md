# GCP 배포

대상 프로젝트는 `one-tatchi-gejkm`, 리전은 서울 `asia-northeast3`이다. 구현체는 v1.13.0부터 제공한다. AWS 계정·state·도메인과 onprem 설정은 유지한다.

## 인증과 state

로컬에서는 팀 계정의 `onetatchi` gcloud configuration을 사용한다. ADC를 바꾸지 않고 명령 실행 시 단기 토큰을 환경변수로 전달한다.

```bash
export GOOGLE_OAUTH_ACCESS_TOKEN="$(gcloud --configuration onetatchi auth print-access-token)"
export CLOUDSDK_ACTIVE_CONFIG_NAME=onetatchi
```

bootstrap/gcp는 GCS state 버킷과 WIF를 만든다. 자세한 최초 이전 절차는 [bootstrap 안내](../bootstrap/gcp/README.md)를 따른다. demo-app 루트는 GCS prefix `demo-app/gcp`를 사용하고 bootstrap은 `bootstrap/gcp`를 사용한다. Terraform state·plan은 Git에 넣지 않는다.

GitHub Variables: `GCP_PROJECT`, `GCP_REGION`, `GCP_CLUSTER`, `GCP_WIF_PROVIDER`, `GCP_PLAN_WIF_PROVIDER`, `GCP_PLAN_IDENTITY`, `GCP_DEPLOY_IDENTITY`, `GCP_TF_STATE_BUCKET`. AWS 변수와 기본 `DEPLOY_TARGET`은 그대로 둔다.

## 최초 생성

demo-app의 `infra/envs/gcp`에서 실행한다. GKE 인증 플러그인과 Helm이 필요하다.

```bash
terraform init -backend-config=bucket=one-tatchi-gejkm-tfstate
terraform validate
# 클러스터 생성 전 Helm provider가 연결할 대상이 없으므로 최초에만 분리한다.
terraform apply -target=module.network -target=module.cluster -target=module.registry -target=module.database -target=module.observability
terraform apply
terraform plan
```

최종 plan에 의도하지 않은 변경이 없어야 한다. GKE private 노드 3대, Cloud SQL private IP, Argo Rollouts, External Secrets, test/prod namespace와 DB Secret을 확인한다.

```bash
gcloud --configuration onetatchi container clusters get-credentials one-tatchi-gcp --region asia-northeast3
kubectl get nodes
kubectl get clustersecretstore cloud-secrets
kubectl get externalsecret -A
```

DB는 Postgres 17, 기본 `db-g1-small`·단일 영역·SSD 20GB·백업 1개다. 공개 IP 없이 TLS를 요구한다. demo-app의 GCP 값은 Postgres.js에 `PGSSL=require`를 전달하고 기존 service-base의 psql 연결도 sslmode=require를 사용한다. 이 설정은 암호화를 요구하지만 서버 인증서의 이름·CA 검증을 제공하지 않는다. 실제 개인정보를 처리하는 운영은 Cloud SQL Connector 또는 검증할 CA를 별도 연결한다.

## 앱 배포와 확인

같은 `deploy/values-be.yaml` · `deploy/values-fe.yaml`과 App Chart를 사용한다. `deploy/gcp/values.yaml`에는 GKE NEG, gce Ingress, TLS 연결용 환경값만 덧붙인다. FE만 외부에 공개하고 기존 FE → BE 프록시를 유지한다.

demo-app `deploy` workflow_dispatch에서 target=gcp, environment=test를 선택하면 test만 검증한다. 기존 기본값은 test 검증 후 prod이며 규제 대상 prod 승인 관문은 유지한다. prod에는 test에서 stable로 승격한 같은 이미지 태그만 배포한다.

```bash
kubectl -n test get rollout,svc,ingress
kubectl -n test get ingress demo-app-fe -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
curl http://<active-IP>/health
curl http://<active-IP>/api/info
```

`/health`의 database가 connected이고 `/api/info`의 dbConnected가 true여야 DB 연결 검증이다. 메모리 모드의 HTTP 200만으로 완료 처리하지 않는다. 두 번째 버전이 Paused인 상태에서 preview와 active를 확인하고 rollout workflow_dispatch target=gcp로 promote한 뒤 stable 태그를 확인한다. GCP preview는 별도 IP이며 AWS의 `:8080` 주소 규칙을 사용하지 않는다.

`terraform output dashboard_url`의 Cloud Monitoring 대시보드와 Logs Explorer에서 해당 GKE 지표·로그를 확인한다. 기존 중앙 Grafana는 변경하지 않는다.

## 비용과 정리

GKE 노드·Regional 관리 기능·NAT·Cloud SQL·Ingress LB와 로그·지표에 비용이 발생한다. active/preview와 test/prod마다 LB가 따로 생길 수 있다. 데모를 유지할 시간은 운영 담당자가 정한다. 삭제 시 앱 Helm 릴리스를 먼저 제거해 Ingress LB와 NEG 정리를 기다린 뒤 GCP 환경 루트를 destroy한다. bootstrap은 별도이며 state 버킷을 삭제하지 않는다. PSA peering은 다른 managed service 보호를 위해 자동으로 삭제하지 않는다.

## 공유 결정

- [ADR 0006: CI와 state](adr/0006-gcp-ci-state.md)
- [ADR 0007: 공통 차트와 GKE Ingress](adr/0007-gcp-ingress.md)
- [ADR 0008: DB 비밀번호](adr/0008-gcp-database-credentials.md)
- [ADR 0009: 관측](adr/0009-gcp-observability.md)
