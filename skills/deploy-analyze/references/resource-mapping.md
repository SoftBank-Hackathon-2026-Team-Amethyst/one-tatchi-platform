# 자원 목록 매핑 계약 (T16 / C4)

C4는 스킬이 명시한 자원 목록을 가격 도구 입력으로 변환하고 검사한다. HCL 해석, Terraform 실행, state 다운로드와 자원 변경은 수행하지 않는다. 실제 설정을 읽고 자원 목록에 옮기는 책임은 분석 스킬에 있다. 검증기는 전달한 값과 출처·수량·공유 범위의 일관성을 검사하며 Terraform 설정이나 실제 상태와 값이 같은지 자동으로 증명하지 않는다.

## 입력과 출력

```sh
python <skill-dir>/scripts/price.py map \
  --inventory <app-root>/.deploy/analysis/pricing-inventory.json \
  --output <app-root>/.deploy/analysis/pricing-input.json \
  --assessment <app-root>/.deploy/analysis/resource-assessment.json
```

- pricing-inventory.json: 설정에서 확인한 자원, 값의 출처, 과금 항목, 트래픽 추천과 수용량 정보다.
- pricing-input.json: C2·C3 lookup이 읽는 버전 2 입력이다. 전체 월 사용량과 앱 추가 증분을 구분한다.
- resource-assessment.json: 선택한 값과 출처, 공유 자원, 누락·미정 항목, 증설 검토와 온프레미스 운영 비용이다.

map은 네트워크 없이 실행한다. 종료 코드 0은 매핑 확인 항목이 모두 준비됨, 3은 미정 항목이 있는 유효한 부분 결과, 2는 입력 오류, 1은 파일·내부 오류다. 부분 결과에서도 비용 항목을 제거하거나 미정 사용량을 0으로 바꾸지 않는다. 단가 실조회 성공이나 비용 계산 완료를 의미하지 않는다.

출력 두 파일은 입력과 서로 다른 경로여야 한다. 저장 전 경로를 검사하고 파일별로 임시 작성·교체한다. 두 파일을 하나의 트랜잭션으로 교체하지는 않는다. assessment의 input_sha256은 생성된 입력, inventory_sha256은 원래 자원 목록의 정규화 해시다. 두 번째 파일 저장에 실패하면 성공으로 보고하지 않으며, 소비자는 assessment 해시가 현재 입력과 맞는지 검사해야 한다.

## 자원 목록 형식

최상위 schema_version은 "1"이다. input_id, created_at, template_version, monthly_hours, monthly_budget, budget_basis, fx는 [가격 입력 계약](price-format.md)을 따른다. candidates는 배열이다.

후보 키는 candidate_id, target, region, configuration_status, assumptions, values, resources, excluded_resources, traffic, capacity, operating_costs다. unknown 필드는 오류다.

### 값의 출처와 우선순위

values의 각 이름은 root, module_default, assumption 중 하나 이상의 선택지를 가진다. 선택지는 value와 source로 구성된다. source는 path, ref, note이며 실제 파일·참조·선택 근거를 기록한다.

```json
{
  "nodes": {
    "root": {
      "value": {"min": 3, "desired": 3, "max": 3},
      "source": {"path": "infra/envs/aws/main.tf", "ref": "앱의 확인한 커밋", "note": "명시한 노드 수"}
    },
    "module_default": {
      "value": {"min": 2, "desired": 2, "max": 3},
      "source": {"path": "modules/cluster/aws/variables.tf", "ref": "v1.14.0", "note": "참조한 모듈의 기본값"}
    }
  }
}
```

우선순위는 root → module_default → assumption이다. 상위 선택지가 null이면 미정으로 유지하며 하위 값으로 바꾸지 않는다. root 출처에는 확인한 ref가 필요하다. module_default의 ref는 template_version과 같아야 한다. 가정은 ref가 null일 수 있지만 근거가 필요하다.

항목의 값은 직접 쓰거나 {"value_from":"nodes", "member":"desired"}처럼 참조한다. member는 객체 키 또는 음수가 아닌 배열 인덱스다. 없는 값·키·인덱스는 오류이며 수식·코드·HCL 표현식을 평가하지 않는다. 사용한 가정은 생성 입력의 assumptions와 configuration_status에 반영한다. assessment는 사용하지 않은 선언 값도 보존하고 used_values로 실제 사용 여부를 구분한다.

### 물리 자원과 과금 차원

resources의 각 항목은 resource_id, resource_kind, shared, environments, items를 가진다. 같은 물리 자원 또는 같은 규격의 집계 그룹에는 한 resource_id를 사용한다. 공유 자원을 test/prod마다 다른 ID로 다시 선언하지 않는다.

items는 item_id, billing_dimension, attributes, quantity, unit, cost_type, monthly_usage, incremental_usage, source를 가진다. 변환 후 resource_id·resource_kind·shared를 붙이고 가격 입력 계약을 검사한다. quantity는 같은 과금 규격의 개수, monthly_usage는 그 하나의 사용량이다. environment 수를 quantity에 자동으로 곱하지 않는다.

- AWS: EKS, EC2, 노드 EBS, NAT, ALB, RDS, ECR, 로그, 송신을 포함한다.
- GCP: GKE, 노드 CPU·메모리, 디스크, Cloud NAT, 노출, Cloud SQL, Artifact Registry, 로그, 송신을 포함한다.
- NAT·ALB·DB·로그 등은 시간/저장/처리량의 필수 과금 차원을 구분한다. GKE 노드는 CPU·메모리를 모두 기록한다. Cloud SQL은 인스턴스 시간 또는 CPU·메모리 시간과 저장소를 기록한다.
- 해당 자원이 없는 구성은 excluded_resources에 종류와 고정 ref를 가진 source를 기록한다. 포함과 제외를 동시에 선언할 수 없다.
- 추가 비용 종류도 항목으로 남긴다. 현재 조회기가 미지원하거나 정확한 SKU 선택 조건이 없으면 unconfirmed_catalog로 표시한다. 목록에서 지워 완전한 견적으로 보이게 하지 않는다.

후보별 필수 종류 검사는 이 플랫폼의 쿠버네티스 구성에 맞춘 최소 범위다. 모든 클라우드 요금 항목을 자동으로 발견하는 기능은 아니다. 계정 크레딧·할인, 외부 DNS·백업·시크릿·관측 등 추가 비용의 포함 범위는 별도로 확인한다.

### 트래픽과 증설 검토

traffic은 null 또는 scenario(final/default), source, workloads다. workload마다 name, replicas, environments, blue_green_multiplier, cpu_millicores, memory_mib를 적는다. CPU는 정수 millicores, 메모리는 MiB 십진 문자열이다. 같은 서비스·환경을 중복 적지 않는다.

capacity는 null 또는 node_count, per_node, reserved, source다. per_node와 reserved는 cpu_millicores, memory_mib, pod_slots를 가진다. reserved는 시스템·관측·기존 앱 등 클러스터 전체 예약분이다. node_count는 견적의 노드 수와 같아야 한다. 실제 allocatable 값과 예약분을 확인하지 않았다면 null로 두거나 가정임을 출처에 명시한다.

수요는 replicas × 환경 수 × Blue-Green 배수 × 파드 요청량으로 계산한다. 공급은 노드 수 × 노드당 수용량 − 예약분이다. check는 within_supplied_bounds, exceeds_supplied_bounds 또는 unknown이다. node_expansion은 not_indicated 또는 review_required다.

이 검사는 공급받은 합계 한도만 비교한다. 실제 배치, affinity, 파드별 크기, 노드별 분포와 라이브 상태를 보장하지 않는다. replicas를 바꿔도 노드 quantity를 자동으로 변경하지 않는다. 초과하거나 정보가 없으면 증설 검토를 요청하고, 명시적인 새 노드 시나리오를 입력한 뒤 재계산한다. 트래픽이 없거나 default면 기본 시나리오임을 표시한다.

### 전체와 증분, 온프레미스

monthly_usage는 전체 구성의 사용량이고 incremental_usage는 앱 추가분이다. 공용 노드에 여유가 확인되지 않았으면 증분 0을 가정하지 않고 null로 남긴다. 같은 앱에 환경을 추가하는 경우와 새로운 앱을 추가하는 경우의 공유 범위를 가정에 적는다.

onprem의 resources는 비어 있으며 기존 장비의 클라우드 요금만 0으로 비교한다. operating_costs에는 power, hardware, labor를 모두 기록하고 각각 monthly_krw 범위 또는 null과 source를 남긴다. 클라우드 0원을 전체 운영 비용 0원으로 설명하지 않는다. 사용자가 제공한 운영 비용은 assessment에 그대로 보존하며 cloud pricing-input의 항목에 섞지 않는다.

## 확인 예시

[demo-inventory.json](examples/pricing/demo-inventory.json)은 2026-10-09에 확인한 demo-app 커밋 18673c9f3b40baa02e9cb8e79cb74aa3c8b465e7과 참조 모듈 v1.14.0을 기준으로 만든 설정 스냅샷이다. 실제 클라우드 state나 현재 청구 내역이 아니다.

- AWS 명시값: t3.medium 3대, single_nat 1개, db.t4g.micro·단일 AZ·20GB RDS 1개. test/prod 공유 자원은 한 번 기록한다.
- GCP 참조 기본값: 전체 e2-standard-2 노드 3대, 노드 디스크 30GB, db-g1-small·20GB Cloud SQL. 노드 수를 존 수만큼 다시 곱하지 않는다.
- GCP CPU·메모리 사용량과 ingress 개수는 가정이며, 디스크 과금 단위·NAT 과금 수량·정확한 카탈로그 선택 조건과 변동 사용량은 미확인으로 남아 있다.
- 온프레미스 Postgres는 환경별로 별도라는 점을 기록하고 전기·장비·인건비는 미산정으로 남긴다.

따라서 이 예시의 map 종료 코드는 3이다. 미확인 SKU나 사용량을 새로 추측하지 않았다는 의미이며, C7 전까지 완전한 비용 견적으로 사용할 수 없다.

## 실제 카탈로그 선택자를 연결한 예시

[demo-catalog-inventory.json](examples/pricing/demo-catalog-inventory.json)은 demo-app 커밋 7893547913b57705d7f2e366f375b15beadcbba4와 v1.16.0을 기준으로 공개 API의 정확한 과금 항목을 지정한 예시다. 기존 예시는 초기 매핑 계약 검증용으로 유지한다. 새 예시는 AWS usage_type, GCP SKU·서비스·taxonomy·리전을 명시하고 시크릿 접근 요청, S3 요청과 GCP 송신 처리 항목도 구분한다.

카탈로그 연결은 어떤 가격표를 읽을지 확정한 것이다. 선택적 서비스가 실제 사용되는지, 월 사용량이 얼마인지, 계정 무료 구간을 사용할 수 있는지는 별도 확인이 필요하다. 새 예시도 사용량·수용량 미정을 유지하므로 map은 부분 결과를 반환한다. 조회 결과만 보고 항목을 0원으로 바꾸거나 전체 견적 완료로 처리하지 않는다.
