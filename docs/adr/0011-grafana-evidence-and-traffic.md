# 0011: 중앙 Grafana의 실행 근거와 실제 트래픽

상태: 채택 (T17)

## 배경

현재 AI 판단은 green에 smoke 요청을 보낸 뒤 `metrics.sh`가 계산한 `metrics.json`과 파드 상태를 사용한다. 중앙 저장소의 rate 쿼리로 이를 대체하면 관찰 창과 p95 계산이 달라진다. 실제 사용자 트래픽은 앱에 별도 계측이 필요하다.

## 결정

- AI 계산과 거부 규칙을 유지한다. `publish-metrics`는 원본 수치·임계값·관찰 시작/종료·판단·저장소/실행/attempt/SHA/대상/환경/서비스를 CloudWatch Logs에 게시한다. 응답 본문과 원본 로그는 보내지 않는다. 게시 실패는 경고로 남기고 원래 Actions artifact를 보존한다.
- 대시보드에서 실제 HTTP 지표와 실행별 smoke 근거를 분리한다. HTTP 에러율은 5xx/전체, histogram p95는 추정값이다. smoke 에러율은 기대 상태 불일치(연결 실패 포함), p95는 기존 nearest-rank다. 요청이 없거나 수집이 끊긴 구간을 성공률 100%로 채우지 않는다.
- AWS 중앙 Prometheus가 AWS 앱을 수집하고, 온프레미스 Prometheus가 outbound HTTPS remote-write로 전송한다. Quick Tunnel 주소와 IP 변경에 의존하지 않는다. 수신기는 인증된 POST `/api/v1/write`만 허용하며 Prometheus 조회 API는 외부로 노출하지 않는다.
- 수신 비밀번호는 CI secret → Kubernetes Secret 경로로만 전달한다. Terraform에는 호스트와 Secret 이름만 저장한다. 중앙 7일·온프레미스 2일, 각각 5Gi 볼륨/4GB TSDB 한도로 데모 보관량을 제한한다. 중앙 스토리지에는 EBS CSI와 암호화 gp3를 사용한다.
- GCP 앱은 Managed Prometheus `PodMonitoring`을 사용한다. AWS Grafana는 EKS 서비스 계정 토큰 → GCP Workload Identity Federation → Monitoring Viewer 권한으로 조회한다. 서비스 계정 private key를 생성하지 않는다.
- AWS/온프레미스 리소스는 kubelet `/metrics/cadvisor`와 pod 전용 kube-state-metrics에서 읽는다. kubelet TLS 검증을 유지하고 `nodes/metrics` GET만 허용한다. `nodes/proxy` 권한을 주지 않는다.
- 기존 호출은 CloudWatch 전용 상태를 유지한다. 새 수집과 인증은 모듈 입력으로 켠다. AI의 `promote` 판단은 실제 승격 완료와 구별하고 Actions 실행 링크를 제공한다.

## 영향

FE는 제한된 syslog 필드(메서드·상태·바이트·소요 시간)로 exporter에 전달하고 BE는 완료 요청을 계측한다. URL·IP·사용자 식별자는 메트릭 라벨에 넣지 않는다. `one-tatchi-smoke`와 kube-probe는 실제 트래픽 집계에서 제외한다. FE와 BE가 같은 사용자 요청을 각각 기록할 수 있으므로 서비스 간 요청 수를 합산하지 않는다. syslog UDP 전송은 과부하에서 유실될 수 있으므로 과금이나 정확한 거래 건수의 근거로 사용하지 않는다.

공식 nginxlog exporter v1.11.0 이미지는 Go 1.18.10을 포함한다. 원본 릴리스를 Go 1.27.2로 재빌드해 플랫폼 릴리스와 함께 배포하고 이미지 취약점 검사를 수행한다. 외부 수신 인증과 GCP WIF 초기 권한 설정은 [운영 안내](../observability.md)를 따른다.
