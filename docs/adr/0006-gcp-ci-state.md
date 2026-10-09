# 0006: GCP CI 인증과 state 분리

상태: 채택 (T4)

## 배경

AWS 인증과 S3 state를 고정한 기존 경로로는 GCP 인프라를 반영할 수 없다. 장기 서비스 계정 키를 GitHub에 저장하지 않고 plan과 deploy 권한을 분리해야 한다.

## 결정

- GCP bootstrap은 GCS state 버킷과 GitHub WIF를 만든다. AWS bootstrap과 감사 로그 S3는 유지한다.
- 숫자 조직 ID · 레포 ID와 허용한 platform 재사용 워크플로의 main · 버전 태그만 신뢰한다. 이름만 같은 외부 레포는 허용하지 않는다.
- plan과 deploy는 같은 pool의 별도 provider와 서비스 계정을 사용한다. provider가 설정한 access 속성으로 계정 간 교차 위임을 막는다.
- deploy는 main 또는 test/prod/prod-auto/destroy environment로 제한한다. 기존 운영 승인 관문은 유지한다.
- plan은 viewer와 해당 state 버킷의 읽기, `.tflock` 객체 쓰기만 가진다. Secret Manager 값 읽기 권한은 부여하지 않는다.
- deploy에는 compute/container/cloudsql/secretmanager/artifactregistry/monitoring/servicenetworking과 서비스 계정 · 프로젝트 IAM 관리 역할을 부여한다. 프로젝트 전체 Owner/Editor는 부여하지 않는다.

## 영향

프로젝트 IAM 관리와 서비스 계정 사용 권한은 높은 권한이다. 인프라가 노드 · External Secrets IAM 연결을 관리하기 때문에 필요하며, bootstrap을 별도로 보호한다. CI 코드를 승인 없이 변경하는 주체가 deploy 토큰을 얻지 않도록 main · environment와 재사용 워크플로 신뢰를 함께 제한한다. GCP 변수는 `GCP_*`로 분리하여 기존 AWS 변수를 덮어쓰지 않는다.
