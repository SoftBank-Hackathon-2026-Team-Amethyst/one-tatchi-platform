# Terraform 모듈 계약

환경 루트는 `modules/<기능>/<대상>`을 고정 태그 `vX.Y.Z`로 참조한다. 공통 출력 이름과 대상별 의미는 다음과 같다. GCP는 T4 구현체를 제공한다.

| 기능 | 공통 출력 | AWS에서 연결하는 대상 | GCP에서 연결하는 대상  |
|---|---|---|---|
| network | `network_id`, `network_cidr`, `private_subnet_ids`, `public_subnet_ids` | VPC와 서브넷 | VPC와 노드 서브넷. `public_subnet_ids`는 `[]` |
| cluster | `cluster_name`, `endpoint`, `ca_certificate` | EKS와 Helm/Kubernetes provider. CA는 base64 인코딩 | GKE와 Helm/Kubernetes provider. endpoint는 HTTPS URL, CA는 base64 인코딩 |
| cluster_addons | `secret_store_name`, `ingress_class` | ClusterSecretStore와 IngressClass | ClusterSecretStore와 Ingress 설정. GKE 기본 `gce` 어노테이션 사용 |
| registry | `repository_urls` | 저장소 이름 → 이미지 push 주소 | 저장소 이름 → Artifact Registry 이미지 push 주소 |
| database | `host`, `port`, `database_name`, `credentials_secret_id` | RDS와 username/password JSON 시크릿 식별자 | Cloud SQL과 username/password JSON을 담은 Secret Manager 시크릿 식별자 |
| observability | `dashboard_path` | Ingress 주소에 붙일 Grafana 경로 | Google Cloud Console 기준 대시보드 경로 (`dashboard_url`도 제공) |
| ci_identity | `plan_identity`, `deploy_identity` | plan/apply가 사용할 IAM 역할 ARN | plan/apply가 사용할 서비스 계정 이메일 |

AWS의 `node_security_group_id`, onprem의 `kube_context` 등은 벤더별 연결에 쓰는 추가 출력이다. `ci_identity/aws`의 기존 `plan_role_arn`, `deploy_role_arn`은 bootstrap 호환성을 위해 유지한다. GCP 고유 입력은 각 모듈 README에 기록한다.

## GCP 입력 · 출력 규칙 (T4)

- 공통 출력 이름과 역할은 유지한다. 값의 형식이 대상에 따라 다른 식별자는 해당 대상의 provider · 인증 액션에 연결한다.
- GCP에는 AWS 전용 `node_security_group_id`, `plan_role_arn`, `deploy_role_arn`을 만들지 않는다.
- GCP 전용 출력으로 `node_service_account`, `pods_range_name`, `services_range_name`, `workload_identity_provider`를 추가한다.
- 입력은 의미가 같으면 기존 이름을 유지한다. AWS 전용 개념은 GCP에 필요한 이름으로 별도 대응한다. 구체적인 입력 목록은 각 모듈 구현 시 문서화한다.
- 기존 AWS · onprem 계약과 호출부는 유지한다. 공통 계약 자체를 바꿔야 하는 예외는 담당자와 공유 · 합의한다.

## AWS 루트의 연결 순서

1. `network`의 private subnet을 `cluster`와 `database`에 전달한다. DB 접근은 `cluster.node_security_group_id`만 허용한다.
2. `cluster.cluster_name`을 애드온에 전달한다. 이 출력은 노드 그룹과 CoreDNS를 포함한 EKS 모듈 완료를 기다린다. VPC CNI와 Pod Identity Agent는 노드보다 먼저 설치한다.
3. Helm provider는 `cluster.endpoint`, `base64decode(cluster.ca_certificate)`와 `aws eks get-token` exec 인증을 쓴다. 긴 apply 중에도 토큰을 갱신할 수 있다.
4. `database.credentials_secret_id`만 External Secrets의 읽기 허용 목록에 넣는다. External Secrets CRD 설치 후 별도 Helm 릴리스로 ClusterSecretStore를 만든다.
5. `cluster_addons.ingress_class`를 observability에 전달해 LB Controller 준비 후 Grafana Ingress가 만들어지도록 한다.

`ci_identity`는 bootstrap이 소유한다. demo-app 루트에서는 기존 plan/deploy 역할을 조회하고 EKS access entry에 연결한다. GitHub OIDC provider나 역할을 다시 만들지 않는다. 생성자 자동 관리자 권한은 꺼져 있으므로 팀 관리자 SSO 역할도 명시적으로 등록해야 한다.

## 사전 검증에서 반영한 조건

- LB Controller의 `enableServiceMutatorWebhook = false`: Ingress용 ALB만 사용하며 Service 생성이 webhook 준비를 기다리는 교착을 피한다.
- Helm 릴리스의 `replace = true`: 삭제된 릴리스 이름 재사용을 허용한다. 모든 실패를 자동 복구하는 옵션은 아니므로 실패 원인과 Helm 상태도 확인한다.
- DB 보안 그룹 규칙은 `count = length(allowed_security_group_ids)`: 최초 plan에서 ID를 몰라도 규칙 개수를 결정할 수 있다.
- GitHub 신뢰 조건은 immutable subject 접두사와 허용된 재사용 워크플로를 사용한다. 배포 역할은 main 및 지정 environment로 제한한다.
