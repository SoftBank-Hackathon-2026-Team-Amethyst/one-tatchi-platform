# GCP cluster — GKE Standard

AWS의 EKS 관리형 노드 그룹에 대응하는 GKE Standard Regional 클러스터다. C2 네트워크를 사용하고, 서울 2개 영역에 총 3대의 노드를 구성한다. 아래 내용은 코드 기준이며 실제 생성 · Ready 확인은 apply 후 수행한다.

```hcl
module "cluster" {
  project_id          = "one-tatchi-gejkm"
  source              = "<platform 고정 태그의 modules/cluster/gcp>"
  name                = "one-tatchi"
  network_id          = module.network.network_id
  subnet_ids          = module.network.private_subnet_ids
  pods_range_name     = module.network.pods_range_name
  services_range_name = module.network.services_range_name
  node_instance_types = ["e2-standard-2"]
  node_count          = { min = 3, desired = 3, max = 5 }
}
```

## 입력

| 이름 | 기본값 | 의미 |
|---|---|---|
| `name` | 필수 | 클러스터 이름 |
| `network_id`, `subnet_ids` | 필수 | C2 VPC와 리전 서브넷 1개 |
| `pods_range_name`, `services_range_name` | 필수 | C2 보조 IP 범위 이름 |
| `region` | `asia-northeast3` | 관리 기능이 여러 영역에 분산되는 클러스터 리전 |
| `node_locations` | 서울 `a`, `b` | 노드를 둘 영역 목록 |
| `node_instance_types` | `["e2-standard-2"]` | 단일 머신 타입. 이름은 AWS 입력과 동일 |
| `node_count` | `{ min = 3, desired = 3, max = 5 }` | 모든 영역을 합친 노드 수. GKE Cluster Autoscaler가 min~max 범위에서 조절 |
| `kubernetes_version` | `1.36.4-gke.1391000` | 최소 관리 버전. 서울 REGULAR 지원 목록 확인. `null`이면 채널 기본값 |
| `master_ipv4_cidr` | `172.16.0.0/28` | 관리 기능의 사설 주소 범위. 기존 네트워크와 비중복 확인 필요 |
| `authorized_networks` | `{}` | 관리 API에 접근할 이름 → IPv4 CIDR 목록. 기본은 IP 제한 없음 |

`node_count`는 AWS처럼 총개수다. 영역별 노드 풀을 만들고 정렬된 영역 순서로 나머지를 배분하므로 기본값은 a 영역 2대 · b 영역 1대다. min/desired/max도 각각 같은 방식으로 배분한다. 영역 간에 자동으로 노드 용량을 재배분하지 않는다. desired는 최초 생성 수이며 이후 크기는 각 풀의 autoscaler가 관리한다.

기본 3대는 정상 운영 시 기준이다. 클러스터 생성 중 제거할 기본 풀이 잠시 생기고, 업그레이드 중에는 풀마다 여분 노드 1대가 생길 수 있다. 총 CPU · IP · 비용 한도는 apply 전에 확인한다.

## 인증 · 통신

- 노드는 외부 IP 없이 C2 NAT를 사용한다. 관리 API는 GitHub 호스티드 러너가 접근할 수 있게 공개한다.
- 별도 노드 서비스 계정에 `roles/container.defaultNodeServiceAccount`와 `roles/artifactregistry.reader`만 부여한다. 기존 프로젝트 IAM 바인딩은 덮어쓰지 않는다.
- 클러스터 · 노드에 Workload Identity를 켠다. 파드별 권한은 애드온 단계에서 연결하며 노드 계정과 분리한다.
- legacy metadata · 클라이언트 인증서 발급을 끄고 Shielded Nodes, Secure Boot, Dataplane V2, 로그 · 지표 · Managed Prometheus를 설정한다.
- IP 제한 없는 공개 API는 기존 AWS의 러너 접근 정책을 따른다. IAM/RBAC 인증이 필요하며 CI·사람의 접근 권한은 별도로 연결한다. 이 사유로 `GCP-0061` 검사 예외를 해당 클러스터 코드에만 기록했다. 고정 러너 IP가 있으면 `authorized_networks`를 지정한다.
- `deletion_protection = false`로 해커톤 리소스 삭제를 허용한다. REGULAR 채널 · 노드 자동 복구 · 자동 업그레이드를 사용한다.

## 출력 · 검증

공통 출력은 `cluster_name`, HTTPS `endpoint`, base64 `ca_certificate`다. `cluster_name`은 노드 풀 준비를 기다린다. GCP 추가 출력은 노드 서비스 계정 이메일 `node_service_account`다.

```bash
terraform init -backend=false
terraform validate
terraform test
```

mock plan 테스트는 총 3대 구성, C2 범위 · Workload Identity 연결, 잘못된 노드 수와 다른 리전 영역 거부를 확인한다. 실제 클러스터 생성과 인증 · 노드 Ready는 이 검사로 확인되지 않는다.

- [GKE node pool provider 문서](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/container_node_pool)
- [노드 서비스 계정 설정](https://docs.cloud.google.com/kubernetes-engine/security/configure-node-service-accounts)

`project_id`를 명시적으로 전달한다. 프로젝트 식별을 위해 인증 토큰이 포함된 client_config 데이터 소스를 state에 저장하지 않는다.
