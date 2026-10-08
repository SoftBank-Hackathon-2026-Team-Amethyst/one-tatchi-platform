# Terraform 모듈 계약

환경 루트는 `modules/<기능>/<대상>`을 고정 태그 `vX.Y.Z`로 참조한다. 공통 출력 이름과 AWS에서의 의미는 다음과 같다.

| 기능 | 공통 출력 | AWS에서 연결하는 대상 |
|---|---|---|
| network | `network_id`, `network_cidr`, `private_subnet_ids`, `public_subnet_ids` | VPC와 서브넷 |
| cluster | `cluster_name`, `endpoint`, `ca_certificate` | EKS와 Helm/Kubernetes provider. CA는 base64 인코딩 |
| cluster_addons | `secret_store_name`, `ingress_class` | ClusterSecretStore와 IngressClass |
| registry | `repository_urls` | 저장소 이름 → 이미지 push 주소 |
| database | `host`, `port`, `database_name`, `credentials_secret_id` | RDS와 username/password JSON 시크릿 식별자 |
| observability | `dashboard_path` | Ingress 주소에 붙일 Grafana 경로 |
| ci_identity | `plan_identity`, `deploy_identity` | plan/apply가 사용할 IAM 역할 ARN |

AWS의 `node_security_group_id`, onprem의 `kube_context` 등은 벤더별 연결에 쓰는 추가 출력이다. `ci_identity/aws`의 기존 `plan_role_arn`, `deploy_role_arn`은 bootstrap 호환성을 위해 유지한다. GCP는 구현 중이며 입력까지 모두 통일된 상태는 아니다.

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
