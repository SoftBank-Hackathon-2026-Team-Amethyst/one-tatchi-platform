# 중앙 Grafana 연결

T17은 AWS의 기존 `/grafana/d/deploy-overview`를 확장한다. `target`, 환경, 서비스, 클러스터와 Actions 실행 ID로 범위를 고른다. AI 근거는 게시 시각에 표시하며 각 행에 실제 관찰 시작·종료가 있다. 과거 실행을 볼 때 시간 범위도 넓힌다. `promote`는 AI 판단이며 실제 승격 여부는 실행 링크에서 확인한다.

## 연결 순서

### HTTPS 진입점과 기존 ALB

`dashboard_host`를 지정하면 Grafana Ingress는 해당 호스트의 HTTPS 443 listener에
`/grafana` 규칙을 만들고 redirect도 `https://<호스트>/grafana/`를 사용한다.
빈 값은 기존 host 없는 HTTP 동작을 유지한다. `ingress_group`은 DNS가 실제로 가리키는
앱 ALB 그룹과 같아야 한다. demo-app은 운영 앱이 `demo-app-prod`를 사용하므로 중앙
관측도 같은 그룹에 넣는다. Grafana 규칙의 순서 10은 앱 `/`의 기본 순서 100보다 앞선다.
기존 다른 ALB를 직접 삭제하지 말고 Ingress·DNS·target health를 확인한 뒤 Terraform 변경을 검토한다.

1. 플랫폼 태그를 릴리스한 후 대상 레포에서 고정 버전으로 참조한다. `observability/aws`에 `central_metrics = { enabled = true, receiver_host = "metrics.example.com", receiver_secret_name = "deploy-metrics-auth" }`를 넘긴다. 호스트는 ALB의 인증서 범위와 Route53 존에 속해야 한다. 기존 Grafana ALB 그룹을 재사용한다.
2. 대상 레포 secret `OBSERVABILITY_REMOTE_WRITE_PASSWORD`를 임의의 긴 값으로 등록한다. 재사용 `infra.yml`의 AWS apply가 bcrypt 수신 Secret을 주입한다. 비밀번호를 Terraform 변수나 tfvars로 전달하지 않는다. 초기 EKS 생성과 관측 활성화는 분리한다(인증 주입은 기존 클러스터가 필요).
3. PR plan을 검토하고 main 파이프라인으로 apply한다. EBS CSI·암호화 gp3·중앙 Prometheus·14일 보존 evidence 로그 그룹이 생성된다. 로그 그룹이 준비되면 대상 레포 변수 `OBSERVABILITY_LOG_GROUP`에 module의 `evidence_log_group` 출력을 설정한다.
4. 온프레미스 `monitoring` namespace에 `username=onprem`, `password=위 secret과 같은 값`을 가진 Kubernetes Secret을 만든다. 파일 입력이나 stdin을 사용하고 셸 기록·로그에 값을 쓰지 않는다. `observability/onprem`에 `cluster_name`, `remote_write_url`(AWS 출력), `remote_write_secret_name`, `dashboard_url`을 전달한다. 호스트 CA를 검증하는 HTTPS만 허용한다.
5. 서비스 값에 `metrics.enabled: true`, BE port 8000 또는 FE port 4040과 `metrics.nginxLogExporter.enabled: true`를 설정한다. 앱 계측 구현이 선행돼야 한다. GCP 재사용 배포는 `metrics.gcpManaged=true`를 자동으로 넘기며 계측이 켜진 서비스만 PodMonitoring을 만든다.

AWS 자원 변경은 앱의 infra 파이프라인으로 수행한다. 기존 팀 온프레미스 state 없이 테스트할 때 기존 클러스터를 같은 이름으로 재생성하지 않는다. 별도 k3d 이름·별도 kubeconfig와 로컬 chart 설치로 검증할 수 있다. 이 검증 설치를 기존 Terraform state로 간주하지 않는다.

## GCP 읽기 전용 인증

기존 GKE의 PR plan에서 Helm이 신규 생성으로 잘못 표시되면 재사용 infra workflow의
`verify-helm-state: true`, `gcp-location: <리전 또는 존>`을 사용한다. 같은 job의 plan/deploy
identity로 state에 있는 release를 실제 조회하고, 권한 거부나 누락이면 plan/apply 전에 실패한다.
Secret 값·Terraform state는 출력하지 않는다. 실패를 없애기 위해 관리자 역할을 주거나
state에서 release를 제거하지 않는다. 이 검사는 신규 클러스터 bootstrap에는 켜지 않는다.

`observability/gcp.grafana_eks_oidc_issuer`에 중앙 EKS의 OIDC issuer를 넣는다. 최초 pool/provider 생성에는 적용 주체의 Workload Identity Pool 관리 권한이 필요하다. 현재 T4 CI 기본 권한에는 이 권한이 없으므로 GCP 관리자가 [bootstrap의 `enable_grafana_wif=true` 절차](../bootstrap/gcp/README.md#t17-중앙-grafana-최초-연결-권한)로 먼저 준비해야 한다. 기본값은 false이며 앱 파이프라인이 임의로 자신의 IAM 권한을 높이지 않는다.

GCP 모듈의 `grafana_workload_provider`, `grafana_service_account` 출력을 AWS 모듈의 `gcp_monitoring`에 `project_id`와 함께 전달한다. 이 값들은 비밀값이 아니다. AWS Grafana에는 external-account 설정 ConfigMap과 만료 1시간의 projected token만 연결된다. 신뢰 대상은 지정한 EKS issuer의 `system:serviceaccount:monitoring:grafana`로 한정된다. 서비스 계정에는 `roles/monitoring.viewer`만 부여한다.

기본 GKE 시스템 지표와 앱의 Managed Prometheus 시계열을 모두 확인한다. GCP 인증을 설정하지 않은 기존 설치에서는 해당 쿼리를 숨긴다. 단순 datasource 생성만으로 실제 조회 검증을 대신하지 않는다.

## 검증·장애 확인

### 관리되는 맥북의 remote-write 설정

v2 재사용 `onprem-observability.yml`은 `workflow_dispatch`의 main에서만 실행된다.
`profile`은 기존 설치 프로필이며 기본 기기는 `default`, 추가 기기는 `secondary`다.
호출부는 `mode`(기본 `plan`), AWS 출력의 `remote-write-url`, `dashboard-url`, 고정
`template-ref`를 전달하고 기존 `OBSERVABILITY_REMOTE_WRITE_PASSWORD`를 명시적으로 넘긴다.

먼저 `plan`을 실행한다. 기존 state와 cluster 소유권, 실제 입력, 전체 Terraform 변경을 검사하며
`module.observability.helm_release.metrics`의 update/no-op만 허용한다. 생성·삭제·교체·다른
자원 변경이 있으면 중단한다. plan 종료 시 기존 공개 tfvars를 복원하며 Secret을 만들지 않는다.

검토 후 같은 입력으로 `apply`를 실행하면 `monitoring/deploy-metrics-remote-write` Secret을
stdin으로 전달하고 기존 설치의 `onpremctl`로 전체 apply한다. 공개 설정은 해당 device root의
`t17-metrics.auto.tfvars.json`에 유지한다. 자격증명은 파일·state·로그에 쓰지 않는다.
v2 wrapper는 저장 plan 적용을 허용하지 않으므로 적용 직전에 state lineage/serial을 확인하고
다시 plan하는 apply를 사용한다. 그동안 다른 로컬 Terraform 작업이나 root 편집을 하지 않는다.
적용 후 collector rollout과 중앙의 실제 시계열을 확인한다. 중앙 연결을 해제해야 하면 공개
remote-write 설정만 원래 값으로 되돌려 wrapper로 plan/apply하고 DB·PVC·클러스터는 보존한다.

로컬 실행도 같은 스크립트를 쓸 수 있다. `METRICS_PASSWORD`는 apply에만 필요하며 터미널 명령에
직접 입력하지 않는다. 예: `python3 scripts/onprem/observability.py --config <기존-config.json>
--remote-write-url https://metrics.example.com/api/v1/write
--dashboard-url https://example.com/grafana/d/deploy-overview --mode plan`.

- `/api/v1/targets`에서 application·kube-state-metrics·cadvisor를 확인한다. kubelet 인증서 문제가 있으면 CA/serving certificate를 수정한다. `insecure_skip_verify`나 `nodes/proxy` 권한으로 우회하지 않는다.
- 정상 요청과 5xx를 보낸 뒤 서비스별 요청 수·오류 비율·histogram을 확인한다. smoke와 kube-probe 요청은 runtime counter에 더해지면 안 된다. `app_parse_errors_total` 증가도 점검한다.
- 중앙에서 `up{target="onprem"}`과 온프레미스 서비스 시계열을 조회한다. 수집 중단 뒤 데이터가 끊기는지, 재연결 뒤 다시 나타나는지 확인한다. remote-write의 `prometheus_remote_storage_*`로 backlog와 오류를 확인한다. 로컬 TSDB 보관 기간이 원격 전송의 무손실 보장을 뜻하지는 않는다.
- 인증 없는 수신 POST는 401, 조회 API는 404여야 한다. 올바른 인증으로 전송한 실제 시계열이 중앙에 나타나야 한다.
- `promote-judgment-<환경>` artifact와 대시보드 행의 SHA·실행/attempt·관찰 창·requests/failed/error_rate/p95_ms·파드 상태·임계값을 대조한다. 게시 실패는 Actions 경고와 원본 artifact를 확인한다. 같은 event_id의 전송 재시도는 대시보드에서 중복 제거한다.
- 비밀번호 교체 시 CI secret과 각 온프레미스 Secret을 함께 바꾼다. 수신 Secret 반영 후 receiver를 재시작해 새 bcrypt 파일을 읽게 한다. GCP OIDC issuer가 바뀌면 Terraform 신뢰 설정도 갱신한다.

로컬 자동 검증: `scripts/tests/run.sh`, AWS/GCP observability의 `terraform test`, `helm lint`, 렌더링한 관측 YAML의 Trivy 검사. 실제 HTTP 계측은 demo-app의 BE 통합 테스트와 격리 클러스터에서 확인한다. 라이브 검증 근거는 PR에 기록하며 확인 전 T17 체크 항목을 완료로 바꾸지 않는다.
