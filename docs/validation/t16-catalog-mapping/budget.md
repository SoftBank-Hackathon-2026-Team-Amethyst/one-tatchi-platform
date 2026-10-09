# 예산 분석

## 예산 범위

0원 ~ 100,000원

기본 단가는 공개 종량제 USD 기준이며 세금·크레딧·약정·계정별 할인은 제외합니다.

## 후보별 예상 월 비용

| 대상 · 후보 | 구성 | 고정비 (USD 소계) | 변동비 (USD 소계) | 전체 (USD) | 앱 추가 (USD) | 전체 원화 | 예산 판정 | 조회/시도 시각 (UTC) |
|---|---|---|---|---|---|---|---|---|
| AWS · demo-aws | 가정 포함 | USD 306.023 | 미산정 | 확인된 소계 USD 306.023; 추가 비용 미정 | 미산정 | 미산정 | 예산 초과 (전체) | 2026-10-09T14:06:30Z |
| GCP · demo-gcp | 가정 포함 | USD 294.4799268 | 미산정 | 확인된 소계 USD 294.4799268; 추가 비용 미정 | 미산정 | 미산정 | 예산 초과 (전체) | 2026-10-09T14:06:30Z |
| 온프레미스 · demo-onprem | 명시 | USD 0 | USD 0 | USD 0 | USD 0 | 0원 | 판정 미정 (전체) | 2026-10-09T14:06:30Z |

부분 결과의 소계는 전체 합계가 아닙니다. 상한과 미산정 항목을 함께 확인하세요.

## 환율 근거

- USD 1 = 1,343.456106원; 기준일 2026-10-08; 출처 ECB EXR daily reference rates: KRW/EUR divided by USD/EUR; input rounded to 6 decimals

## 예산 경고와 절감안

- demo-aws: 예산 초과: 알려진 비용 하한만으로도 예산 상한을 넘습니다.
  - 절감액 미산정: 별도 대안 견적이 없습니다. 노드·DB·NAT 등 큰 비용 항목의 대안을 검토하고, 가용성·규제 조건을 확인한 뒤 별도로 계산해야 합니다.
- demo-gcp: 예산 초과: 알려진 비용 하한만으로도 예산 상한을 넘습니다.
  - 절감액 미산정: 별도 대안 견적이 없습니다. 노드·DB·NAT 등 큰 비용 항목의 대안을 검토하고, 가용성·규제 조건을 확인한 뒤 별도로 계산해야 합니다.
- demo-onprem: 판정 미정: 예산·환율·미산정 비용·구성 조건을 확인해야 합니다.
  - 절감액 미산정: 별도 대안 견적이 없습니다. 노드·DB·NAT 등 큰 비용 항목의 대안을 검토하고, 가용성·규제 조건을 확인한 뒤 별도로 계산해야 합니다.

## 미산정 항목과 실패 사유

- demo-aws / aws-cluster-cluster\_hours: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-aws / aws-nodes-instance\_hours: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-aws / aws-node-disks-storage: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-aws / aws-nat-gateway\_hours: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-aws / aws-nat-processed\_data: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-aws / aws-nat-processed\_data: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-aws / aws-alb-load\_balancer\_hours: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-aws / aws-alb-lcu\_hours: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-aws / aws-alb-lcu\_hours: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-aws / aws-db-instance\_hours: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-aws / aws-db-storage: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-aws / aws-registry-storage: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-aws / aws-registry-storage: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-aws / aws-observability-ingestion: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-aws / aws-observability-ingestion: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-aws / aws-observability-storage: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-aws / aws-observability-storage: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-aws / aws-egress-transfer: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-aws / aws-egress-transfer: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-aws / aws-addresses-address\_hours: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-aws / aws-addresses-address\_hours: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-aws / aws-metrics-metrics: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-aws / aws-metrics-metrics: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-aws / aws-secrets-storage: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-aws / aws-secrets-storage: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-aws / aws-secrets-access: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-aws / aws-secrets-access: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-aws / aws-audit-storage: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-aws / aws-audit-storage: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-aws / aws-audit-write\_requests: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-aws / aws-audit-write\_requests: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-aws / aws-audit-read\_requests: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-aws / aws-audit-read\_requests: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-aws / aws-metrics-disk-storage: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-aws / 구성: 수용량·증설 검토 필요; Traffic or supplied cluster capacity is unknown; node quantity is not changed automatically
- demo-aws / aws-cluster-cluster\_hours: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-aws / aws-nodes-instance\_hours: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-aws / aws-node-disks-storage: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-aws / aws-nat-gateway\_hours: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-aws / aws-nat-processed\_data: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-aws / aws-nat-processed\_data: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-aws / aws-alb-load\_balancer\_hours: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-aws / aws-alb-lcu\_hours: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-aws / aws-alb-lcu\_hours: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-aws / aws-db-instance\_hours: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-aws / aws-db-storage: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-aws / aws-registry-storage: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-aws / aws-registry-storage: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-aws / aws-observability-ingestion: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-aws / aws-observability-ingestion: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-aws / aws-observability-storage: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-aws / aws-observability-storage: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-aws / aws-egress-transfer: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-aws / aws-egress-transfer: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-aws / aws-addresses-address\_hours: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-aws / aws-addresses-address\_hours: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-aws / aws-metrics-metrics: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-aws / aws-metrics-metrics: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-aws / aws-secrets-storage: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-aws / aws-secrets-storage: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-aws / aws-secrets-access: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-aws / aws-secrets-access: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-aws / aws-audit-storage: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-aws / aws-audit-storage: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-aws / aws-audit-write\_requests: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-aws / aws-audit-write\_requests: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-aws / aws-audit-read\_requests: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-aws / aws-audit-read\_requests: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-aws / aws-metrics-disk-storage: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-gcp / gcp-cluster-cluster\_hours: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-gcp / gcp-nodes-cpu\_hours: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-gcp / gcp-nodes-memory\_hours: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-gcp / gcp-node-disks-storage: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-node-disks-storage: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-gcp / gcp-nat-gateway\_hours: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-nat-gateway\_hours: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-gcp / gcp-nat-processed\_data: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-nat-processed\_data: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-gcp / gcp-ingress-test-load\_balancer\_hours: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-ingress-test-load\_balancer\_hours: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-gcp / gcp-ingress-test-processed\_data: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-ingress-test-processed\_data: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-gcp / gcp-ingress-test-outbound-data: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-ingress-test-outbound-data: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-gcp / gcp-ingress-prod-load\_balancer\_hours: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-ingress-prod-load\_balancer\_hours: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-gcp / gcp-ingress-prod-processed\_data: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-ingress-prod-processed\_data: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-gcp / gcp-ingress-prod-outbound-data: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-ingress-prod-outbound-data: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-gcp / gcp-db-instance\_hours: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-gcp / gcp-db-storage: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-db-storage: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-gcp / gcp-registry-storage: 무료 구간의 적용 조건·기존 사용량 미확인; Catalog free tiers need explicit verified eligibility and account/project baseline
- demo-gcp / gcp-observability-ingestion: 무료 구간의 적용 조건·기존 사용량 미확인; Catalog free tiers need explicit verified eligibility and account/project baseline
- demo-gcp / gcp-observability-storage: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-observability-storage: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-gcp / gcp-egress-transfer: 계정·프로젝트의 기존 사용량 미정; Account/project tier baseline must be supplied explicitly
- demo-gcp / gcp-addresses-address\_hours: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-addresses-address\_hours: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-gcp / gcp-metrics-metrics: 계정·프로젝트의 기존 사용량 미정; Account/project tier baseline must be supplied explicitly
- demo-gcp / gcp-secrets-storage: 무료 구간의 적용 조건·기존 사용량 미확인; Catalog free tiers need explicit verified eligibility and account/project baseline
- demo-gcp / gcp-secrets-access: 무료 구간의 적용 조건·기존 사용량 미확인; Catalog free tiers need explicit verified eligibility and account/project baseline
- demo-gcp / gcp-audit-storage: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-audit-storage: 앱 추가 사용량 또는 상관관계 미정; Incremental usage or correlation with total usage is unresolved
- demo-gcp / 구성: 수용량·증설 검토 필요; Traffic or supplied cluster capacity is unknown; node quantity is not changed automatically
- demo-gcp / gcp-cluster-cluster\_hours: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-gcp / gcp-nodes-cpu\_hours: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-gcp / gcp-nodes-memory\_hours: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-gcp / gcp-node-disks-storage: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-node-disks-storage: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-gcp / gcp-nat-gateway\_hours: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-nat-gateway\_hours: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-gcp / gcp-nat-processed\_data: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-nat-processed\_data: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-gcp / gcp-ingress-test-load\_balancer\_hours: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-ingress-test-load\_balancer\_hours: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-gcp / gcp-ingress-test-processed\_data: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-ingress-test-processed\_data: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-gcp / gcp-ingress-test-outbound-data: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-ingress-test-outbound-data: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-gcp / gcp-ingress-prod-load\_balancer\_hours: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-ingress-prod-load\_balancer\_hours: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-gcp / gcp-ingress-prod-processed\_data: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-ingress-prod-processed\_data: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-gcp / gcp-ingress-prod-outbound-data: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-ingress-prod-outbound-data: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-gcp / gcp-db-instance\_hours: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-gcp / gcp-db-storage: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-db-storage: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-gcp / gcp-registry-storage: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-registry-storage: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-gcp / gcp-observability-ingestion: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-observability-ingestion: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-gcp / gcp-observability-storage: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-observability-storage: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-gcp / gcp-egress-transfer: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-egress-transfer: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-gcp / gcp-addresses-address\_hours: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-addresses-address\_hours: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-gcp / gcp-metrics-metrics: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-metrics-metrics: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-gcp / gcp-secrets-storage: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-secrets-storage: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-gcp / gcp-secrets-access: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-secrets-access: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-gcp / gcp-audit-storage: 월 사용량 또는 상한 미정; Monthly usage is unknown or unbounded
- demo-gcp / gcp-audit-storage: 앱 추가 사용량 또는 상관관계 미정; App addition usage is unknown or unbounded
- demo-onprem / 구성: 수용량·증설 검토 필요; Traffic or supplied cluster capacity is unknown; node quantity is not changed automatically
- demo-onprem / 구성: 온프레미스 운영 비용 미산정; Onprem power operating cost is not estimated
- demo-onprem / 구성: 온프레미스 운영 비용 미산정; Onprem hardware operating cost is not estimated
- demo-onprem / 구성: 온프레미스 운영 비용 미산정; Onprem labor operating cost is not estimated

## 가격 근거

| 후보 | 비용 항목 | SKU | 출처 | 단위 | 가격 적용 시점 |
|---|---|---|---|---|---|
| demo-aws | aws-cluster-cluster\_hours | 8HAE52ZNS3QC3Q8Q | https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API\_pricing\_GetProducts.html | hour | 2026-09-01T00:00:00Z |
| demo-aws | aws-nodes-instance\_hours | G5CAZXC4M5ENHEZN | https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API\_pricing\_GetProducts.html | hour | 2026-10-01T00:00:00Z |
| demo-aws | aws-node-disks-storage | MTK7D9SGKGYR3JD6 | https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API\_pricing\_GetProducts.html | gb\_month | 2026-10-01T00:00:00Z |
| demo-aws | aws-nat-gateway\_hours | P63FHTYZXQBC6HX5 | https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API\_pricing\_GetProducts.html | hour | 2026-10-01T00:00:00Z |
| demo-aws | aws-nat-processed\_data | HC3MBQKUG7PB4BYX | https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API\_pricing\_GetProducts.html | gb | 2026-10-01T00:00:00Z |
| demo-aws | aws-alb-load\_balancer\_hours | VUV9M7PZ543S2SC9 | https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API\_pricing\_GetProducts.html | hour | 2026-08-01T00:00:00Z |
| demo-aws | aws-alb-lcu\_hours | CX4ZBV2SE6F5HJV3 | https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API\_pricing\_GetProducts.html | lcu\_hour | 2026-08-01T00:00:00Z |
| demo-aws | aws-db-instance\_hours | ZBMXF2F4CYQ2FT96 | https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API\_pricing\_GetProducts.html | hour | 2026-10-01T00:00:00Z |
| demo-aws | aws-db-storage | 8TFTRRBWJSP95DQP | https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API\_pricing\_GetProducts.html | gb\_month | 2026-10-01T00:00:00Z |
| demo-aws | aws-registry-storage | FP58BXCX2RHZR3B2 | https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API\_pricing\_GetProducts.html | gb\_month | 2025-11-01T00:00:00Z |
| demo-aws | aws-observability-ingestion | 5P9Q77R2ADUJCNJ2 | https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API\_pricing\_GetProducts.html | gb | 2026-10-01T00:00:00Z |
| demo-aws | aws-observability-storage | E7V5NF3GN7MQKCB6 | https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API\_pricing\_GetProducts.html | gb\_month | 2026-10-01T00:00:00Z |
| demo-aws | aws-egress-transfer | 9AS8NERTGECRPGT7 | https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API\_pricing\_GetProducts.html | gb | 2026-06-01T00:00:00Z |
| demo-aws | aws-addresses-address\_hours | ZKBHEVDXYBRCKFQ8 | https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API\_pricing\_GetProducts.html | hour | 2026-09-01T00:00:00Z |
| demo-aws | aws-metrics-metrics | 92QAN7T7PQUAG6NQ | https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API\_pricing\_GetProducts.html | metric\_month | 2026-10-01T00:00:00Z |
| demo-aws | aws-secrets-storage | 8TY6BPQ52JVYCRQD | https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API\_pricing\_GetProducts.html | secret\_month | 2025-07-01T00:00:00Z |
| demo-aws | aws-secrets-access | 9779GVGYGTKZ2UJA | https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API\_pricing\_GetProducts.html | request | 2025-07-01T00:00:00Z |
| demo-aws | aws-audit-storage | 3JSN7K7UDDNCYCDM | https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API\_pricing\_GetProducts.html | gb\_month | 2026-09-01T00:00:00Z |
| demo-aws | aws-audit-write\_requests | D3S5DN86CFPGUM5G | https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API\_pricing\_GetProducts.html | request | 2026-09-01T00:00:00Z |
| demo-aws | aws-audit-read\_requests | 84G6KSFBGCU9CEC9 | https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API\_pricing\_GetProducts.html | request | 2026-09-01T00:00:00Z |
| demo-aws | aws-metrics-disk-storage | MTK7D9SGKGYR3JD6 | https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API\_pricing\_GetProducts.html | gb\_month | 2026-10-01T00:00:00Z |
| demo-gcp | gcp-cluster-cluster\_hours | B561-BFBD-1264 | https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest/v2beta/skus.price/get | hour | 공급 API 미제공 (최신 단가 조회) |
| demo-gcp | gcp-nodes-cpu\_hours | 9304-94C4-2117 | https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest/v2beta/skus.price/get | vcpu\_hour | 공급 API 미제공 (최신 단가 조회) |
| demo-gcp | gcp-nodes-memory\_hours | D715-4E57-BAFB | https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest/v2beta/skus.price/get | gib\_hour | 공급 API 미제공 (최신 단가 조회) |
| demo-gcp | gcp-node-disks-storage | 0306-B164-A7B7 | https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest/v2beta/skus.price/get | gib\_month | 공급 API 미제공 (최신 단가 조회) |
| demo-gcp | gcp-nat-gateway\_hours | 32E2-4EFC-EF9F | https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest/v2beta/skus.price/get | hour | 공급 API 미제공 (최신 단가 조회) |
| demo-gcp | gcp-nat-processed\_data | 015F-5732-FFF0 | https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest/v2beta/skus.price/get | gib | 공급 API 미제공 (최신 단가 조회) |
| demo-gcp | gcp-ingress-test-load\_balancer\_hours | DEE3-C42E-3E4D | https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest/v2beta/skus.price/get | hour | 공급 API 미제공 (최신 단가 조회) |
| demo-gcp | gcp-ingress-test-processed\_data | 147E-ED36-67D1 | https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest/v2beta/skus.price/get | gib | 공급 API 미제공 (최신 단가 조회) |
| demo-gcp | gcp-ingress-test-outbound-data | 3C98-FAA0-7935 | https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest/v2beta/skus.price/get | gib | 공급 API 미제공 (최신 단가 조회) |
| demo-gcp | gcp-ingress-prod-load\_balancer\_hours | DEE3-C42E-3E4D | https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest/v2beta/skus.price/get | hour | 공급 API 미제공 (최신 단가 조회) |
| demo-gcp | gcp-ingress-prod-processed\_data | 147E-ED36-67D1 | https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest/v2beta/skus.price/get | gib | 공급 API 미제공 (최신 단가 조회) |
| demo-gcp | gcp-ingress-prod-outbound-data | 3C98-FAA0-7935 | https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest/v2beta/skus.price/get | gib | 공급 API 미제공 (최신 단가 조회) |
| demo-gcp | gcp-db-instance\_hours | 28C7-7317-B255 | https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest/v2beta/skus.price/get | hour | 공급 API 미제공 (최신 단가 조회) |
| demo-gcp | gcp-db-storage | B160-DAEA-03EE | https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest/v2beta/skus.price/get | gib\_month | 공급 API 미제공 (최신 단가 조회) |
| demo-gcp | gcp-registry-storage | 8502-299A-ABAF | https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest/v2beta/skus.price/get | gib\_month | 공급 API 미제공 (최신 단가 조회) |
| demo-gcp | gcp-observability-ingestion | 143F-A1B0-E0BE | https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest/v2beta/skus.price/get | gib | 공급 API 미제공 (최신 단가 조회) |
| demo-gcp | gcp-observability-storage | F4AE-5A52-ACE3 | https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest/v2beta/skus.price/get | gib\_month | 공급 API 미제공 (최신 단가 조회) |
| demo-gcp | gcp-egress-transfer | 70A1-9E75-5BB1 | https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest/v2beta/skus.price/get | gib | 공급 API 미제공 (최신 단가 조회) |
| demo-gcp | gcp-addresses-address\_hours | 8515-9425-D2CE | https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest/v2beta/skus.price/get | hour | 공급 API 미제공 (최신 단가 조회) |
| demo-gcp | gcp-metrics-metrics | A4E4-DF03-CDB6 | https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest/v2beta/skus.price/get | sample | 공급 API 미제공 (최신 단가 조회) |
| demo-gcp | gcp-secrets-storage | 7756-ADEF-84F4 | https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest/v2beta/skus.price/get | secret\_month | 공급 API 미제공 (최신 단가 조회) |
| demo-gcp | gcp-secrets-access | EBA7-264F-2D2C | https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest/v2beta/skus.price/get | request | 공급 API 미제공 (최신 단가 조회) |
| demo-gcp | gcp-audit-storage | F4AE-5A52-ACE3 | https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest/v2beta/skus.price/get | gib\_month | 공급 API 미제공 (최신 단가 조회) |

## 근거 파일의 해시

- 입력: `86a903f95a882a3794c4874b2fd11a40d7b4d1411526dc7b61514499aa6ce4eb`
- 단가: `ece27a06a182d236c5d110d6fb09ffa807d36acbf10f4960cdf66d56f75b9a86`
- 계산: `0f6d0c74aefa7e2b64d47f9a0ce84870126be62e02b711aab6160ac292436030`
- 자원 평가: `68a29a14eddcb9942530dfff1c6ef0a2007c95693d1b24b9f9c89211b46529cb`

## 온프레미스 별도 운영 비용

클라우드 비용에 합산하지 않은 별도 값입니다. 전체 운영 예산은 별도로 확인해야 합니다.

- 전기: 미산정; No monthly power cost supplied.
- 장비: 미산정; No monthly hardware cost supplied.
- 인건비: 미산정; No monthly labor cost supplied.

## 가정

- demo-aws: Configuration snapshot only; live state and runtime overrides have not been queried. Catalog selectors and unmeasured usage remain unconfirmed.
- demo-aws: Live validation uses current configured resources. Unmeasured monthly usage and unsupported additional charges remain unknown; no zero-cost replacement is applied.
- demo-aws: Additional selectors identify potential billable dimensions, not proof of measured monthly usage.
- demo-aws: Assumed input node\_disk\_usage: Three node root disks observed at 20GB gp3; future monthly storage modeled at current size.
- demo-aws: Resource assessment SHA-256: 68a29a14eddcb9942530dfff1c6ef0a2007c95693d1b24b9f9c89211b46529cb
- demo-aws: Monthly-hours scenario: 730; resource usage is explicit. Public pre-tax prices exclude credits and negotiated discounts.
- demo-aws: SKU usage is pooled once; item costs use input-order marginal attribution. Item range extrema need not sum to aggregate range extrema.
- demo-aws: KRW conversion: 1343.456106 KRW/USD as of 2026-10-08; ECB EXR daily reference rates: KRW/EUR divided by USD/EUR; input rounded to 6 decimals
- demo-gcp: Configuration snapshot only; live state and runtime overrides have not been queried. Catalog selectors and unmeasured usage remain unconfirmed.
- demo-gcp: Referenced node disk is 30 GB; SQL tier db-g1-small and initial storage 20 GB are confirmed configuration defaults, not live usage.
- demo-gcp: Live validation uses current configured resources. Unmeasured monthly usage and unsupported additional charges remain unknown; no zero-cost replacement is applied.
- demo-gcp: Explicit E2 SKUs use Google public v2beta latest prices; price effective time is not supplied by that API and remains null.
- demo-gcp: Catalog mapping snapshot only. Optional AWS custom metrics and GCP custom audit retention are conditional, not proven active; unknown usage is retained.
- demo-gcp: GCP internet data transfer selector models Seoul-to-South-Korea Premium traffic only; other destinations require separate items.
- demo-gcp: Traffic recommendation is missing or uses a default scenario; recalculate after final sizing
- demo-gcp: Assumed input cpu\_usage: 2 vCPU x 730 hours per e2-standard-2 node; confirm resource specification with selected SKU.
- demo-gcp: Assumed input disk\_usage: 30 GB disk is known, but charged GiB-month interpretation has not been confirmed.
- demo-gcp: Assumed input ingress\_per\_env: Active and preview GCE ingresses per namespace; live forwarding rules and fees need verification.
- demo-gcp: Assumed input memory\_usage: 8 GiB x 730 hours per e2-standard-2 node; confirm resource specification with selected SKU.
- demo-gcp: Assumed input sql\_disk\_usage: 20 GB SQL disk is known, but catalog billing unit and autosize growth are not measured.
- demo-gcp: Resource assessment SHA-256: 68a29a14eddcb9942530dfff1c6ef0a2007c95693d1b24b9f9c89211b46529cb
- demo-gcp: Monthly-hours scenario: 730; resource usage is explicit. Public pre-tax prices exclude credits and negotiated discounts.
- demo-gcp: SKU usage is pooled once; item costs use input-order marginal attribution. Item range extrema need not sum to aggregate range extrema.
- demo-gcp: KRW conversion: 1343.456106 KRW/USD as of 2026-10-08; ECB EXR daily reference rates: KRW/EUR divided by USD/EUR; input rounded to 6 decimals
- demo-onprem: Existing k3d hardware. Onprem PostgreSQL is separate for test and prod. Cloud fee zero is not total operating cost zero.
- demo-onprem: Live validation uses current configured resources. Unmeasured monthly usage and unsupported additional charges remain unknown; no zero-cost replacement is applied.
- demo-onprem: Existing onprem hardware has no cloud charge; power, hardware and labor are separate operating costs
- demo-onprem: Resource assessment SHA-256: 68a29a14eddcb9942530dfff1c6ef0a2007c95693d1b24b9f9c89211b46529cb
- demo-onprem: Monthly-hours scenario: 730; resource usage is explicit. Public pre-tax prices exclude credits and negotiated discounts.
- demo-onprem: SKU usage is pooled once; item costs use input-order marginal attribution. Item range extrema need not sum to aggregate range extrema.
- demo-onprem: KRW conversion: 1343.456106 KRW/USD as of 2026-10-08; ECB EXR daily reference rates: KRW/EUR divided by USD/EUR; input rounded to 6 decimals
