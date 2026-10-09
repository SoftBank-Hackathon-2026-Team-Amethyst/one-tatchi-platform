# GCP network

GKE용 VPC · 노드 서브넷 · pods/services 보조 IP 범위 · Cloud Router/NAT를 만든다. 루트의 Google provider에서 프로젝트를 지정한다. API 활성화는 프로젝트 준비 단계에서 한다.

```hcl
module "network" {
  source = "<platform 고정 태그의 modules/network/gcp>"
  name   = "one-tatchi"
  region = "asia-northeast3"
}
```

## 입력

| 이름 | 기본값 | 의미 |
|---|---|---|
| `name` | 필수 | 리소스 이름 접두사 |
| `region` | `asia-northeast3` | 서브넷 · Router · NAT 리전 |
| `cidr` | `10.0.0.0/16` | 노드용 주소 풀. 첫 1/16(`10.0.0.0/20`)을 서브넷으로 사용 |
| `pods_cidr` | `10.100.0.0/16` | GKE 파드용 보조 범위 |
| `services_cidr` | `10.110.0.0/20` | GKE 서비스용 보조 범위 |

기본값은 팀 프로젝트의 기존 서브넷과 겹치지 않음을 확인했다. 다른 환경에서는 기존 네트워크 · 피어링 · VPN 범위와의 충돌을 별도로 확인한다. 모듈은 노드 · 파드 · 서비스 세 범위의 중복을 거부한다.

## 출력

- 공통: `network_id`, `network_cidr`, `private_subnet_ids`, `public_subnet_ids`
- `network_cidr`는 입력 주소 풀을 반환한다. GCP VPC 자체에는 단일 CIDR이 없다.
- `private_subnet_ids`는 노드 서브넷 1개의 ID 목록이며 NAT 준비를 기다린다. `public_subnet_ids`는 `[]`다.
- GCP 전용: `pods_range_name`, `services_range_name`. GKE 모듈의 보조 범위 선택에 사용한다.

## 통신 · 검증

Private Google Access를 켜고, 노드 서브넷과 보조 범위만 NAT 대상으로 지정한다. VPC Flow Logs와 NAT 오류 로그를 활성화한다. 방화벽은 별도로 열지 않으며 GKE용 규칙은 클러스터 단계에서 검토한다.

```bash
terraform init -backend=false
terraform validate
terraform test
```

테스트는 mock provider의 plan만 실행한다. 실제 리소스는 apply 때 생성되며 NAT · 로그 비용이 발생할 수 있다.
