# 0009: GCP 기본 관측 사용

상태: 채택 (T4)

## 배경

T17 중앙 Grafana는 다른 담당의 작업이다. GCP 데모 검증에 필요한 지표와 로그를 제공하면서 기존 AWS 관측을 변경하지 않아야 한다.

## 결정

- GKE system/workload 로그, 기본 Kubernetes CPU·메모리 지표, Managed Prometheus를 활성화한다.
- observability/gcp는 해당 클러스터를 필터링한 Cloud Monitoring 대시보드를 만든다. 기존 Grafana 설치나 데이터 소스는 수정하지 않는다.
- 공통 출력 이름 dashboard_path를 유지하며 GCP에서 기준 주소는 Google Cloud Console이다. 전체 주소 dashboard_url도 제공한다.

## 영향

대시보드는 GCP 로그인과 조회 권한이 필요하다. 익명 접근을 제공하지 않는다. 공통 출력 소비자는 AWS 앱 주소에 GCP 경로를 붙이지 말고 벤더별 기준 주소 또는 전체 URL을 사용한다. GKE 지표 수집과 실제 시계열 조회를 완료 검증에 포함한다.
