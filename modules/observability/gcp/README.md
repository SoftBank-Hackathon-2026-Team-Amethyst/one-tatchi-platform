# observability/gcp

GKE의 Cloud Monitoring CPU·메모리 지표를 표시하는 대시보드와 Logs Explorer 링크를 만든다. 지표·로그 수집은 `cluster/gcp`의 monitoring/logging_config가 담당한다. 기존 AWS Grafana와 T17 중앙 Grafana를 변경하지 않는다.

`project_id`, `cluster_name`을 입력한다. 공통 `dashboard_path`는 Google Cloud Console에 붙이는 경로이며 AWS의 앱 Ingress 주소에 붙이는 경로와 기준 주소가 다르다. 추가 출력 `dashboard_url`은 전체 주소다. 콘솔 로그인과 프로젝트 Monitoring 조회 권한이 필요하며 대시보드를 익명 공개하지 않는다.
