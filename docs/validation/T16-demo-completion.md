# T16 해커톤 데모 완료 검증

검증 기준: [ADR-0014](../adr/0014-demo-cost-assumptions.md). 실제 API 가격표와 데모 예상 사용량을 조합한 견적이며 실제 청구액을 검증한 자료가 아니다.

## 완료 기준과 증거

| T16 요구사항 | 검증 결과 | 근거 |
|---|---|---|
| AWS/GCP 리전별 단가 → JSON | AWS 21개·GCP 23개 실제 API 조회 성공, 실패 0개 | [실조회 가격](t16-catalog-mapping/prices.json), [검증 JSON](t16-catalog-mapping/verification.json) |
| 추천 구성·트래픽 → 월 비용 | 월 730시간, 환경별 BE/FE replicas 1과 자원 요청량, 사용량 범위를 매핑·계산 | [데모 자원 목록](t16-demo/baseline-inventory.json), [평가](t16-demo/baseline/resource-assessment.json), [계산](t16-demo/baseline/costs.json) |
| 단일 대상 비교·예산 경고·절감안 | AWS 기본 견적과 공개 환경 축소 대안 비교, GCP 미산정·온프레미스 운영비 별도 표시 | [예산 표](t16-demo/baseline/budget.md), [절감 결과](t16-demo/savings.json) |
| janto 리뷰 지점 1 월 비용 표시 | report.md의 관리 비용 블록과 리뷰 요약을 같은 costs.json에서 생성·대조 | [분석 보고서](t16-demo/report.md), [리뷰 지점 1 요약](t16-demo/review-point-1.md), [plan.yaml](t16-demo/plan.yaml) |

AWS 데모 견적 범위는 월 USD 335.95525~340.19265, 원화 451,341.13~457,033.89원이다. 공개 앱 환경을 하나로 줄이는 대안은 USD 312.23025~316.46765다. 차액 범위는 월 USD 19.4876~27.9624이며 두 구성 모두 월 10만 원 예산을 초과한다. 비교는 사용량 범위의 최악·최선 조합을 사용하므로 동일한 트래픽을 가정해도 절감액을 단일값으로 단정하지 않는다.

GCP는 무료 적용·계정 기존 사용량 미정으로 부분 견적이다. 온프레미스의 클라우드 요금 0원은 운영비 0원이 아니다. AWS 유료 커스텀 메트릭과 자원 목록 밖의 DNS·백업·추가 네트워크 텔레메트리 등은 이 데모 견적 범위에 포함하지 않았다. 이 범위의 가정과 제외 항목을 보고서에 표시한다.

## 실행·검증 구분

- 실제 API 조회는 [가격 매핑 검증](T16-catalog-mapping.md)에서 수행했다. 데모와 절감 대안은 `reuse-prices`로 원본 입력·가격표·가격 선택 조건을 대조한 뒤 계산했다. [가격 재사용 근거](t16-demo/baseline/price-reuse.json)의 원본 조회 시각을 그대로 보존했다. 새 API 호출을 했다고 주장하지 않는다.
- 실제 demo-app 커밋 7893547913b57705d7f2e366f375b15beadcbba4의 임시 사본에서 보고서와 계획을 생성했다. FE 포트 3000·헬스 경로 /, BE 포트 8000·/health와 자원 요청량을 실제 값 파일과 대조했다. [설정 보존 근거](t16-demo/verification.json)에 config.yaml의 분석 전후 동일한 해시를 기록했다.
- 리뷰 지점 1은 janto-deploy가 report.md의 추천·월 비용·가정을 요약해 보여 주는 지점이다. 이 자료는 그 지점의 비용·경고·절감안 표시와 보고서 인계를 검증한다. 실제 배포 승인을 받거나 deploy-provision·배포·운영 승격을 실행한 기록은 아니다.
- 테스트 191개가 통과했다. 실제 API 픽스처와 데모 입력으로 정상 예산·예산 초과·예산 미정·모의 API 일부 실패·트래픽 크기 변경을 검증했다. 모의 실패를 실제 공급자 장애로 기록하지 않는다. replicas를 2로 바꿔도 노드 3대가 자동 변경되지 않는지, 비용과 리뷰 요약이 같은 계산 결과인지 확인했다.
- 가격 재사용은 리전·대상·SKU·규격·단위 변경, 원본 해시 불일치, 새 자원과 NAT 상한 모델을 거부한다. 단가를 임의로 만들어 넣거나 조회 시각을 갱신하는 방식으로 재계산하지 않는다.

## 재현

의존성을 설치한 뒤 저장된 실제 가격표로 아래 순서를 실행한다. 결과는 `/tmp` 등 별도 폴더에 보관하고 입력을 덮어쓰지 않는다. 예시는 baseline-inventory.json이며 alternative-inventory.json도 같은 순서로 계산한다.

```sh
python skills/deploy-analyze/scripts/price.py map \
  --inventory docs/validation/t16-demo/baseline-inventory.json \
  --output /tmp/pricing-input.json --assessment /tmp/resource-assessment.json
python skills/deploy-analyze/scripts/price.py reuse-prices \
  --input /tmp/pricing-input.json \
  --source-input docs/validation/t16-catalog-mapping/pricing-input.json \
  --prices docs/validation/t16-catalog-mapping/prices.json \
  --output /tmp/prices.json --evidence /tmp/price-reuse.json
python skills/deploy-analyze/scripts/price.py calculate \
  --input /tmp/pricing-input.json --prices /tmp/prices.json \
  --assessment /tmp/resource-assessment.json --output /tmp/costs.json
```

map·calculate의 종료 코드 3은 미정 항목을 보존한 정상적인 부분 결과다. AWS의 전체 비용 범위는 계산됐지만 앱 추가 증분·GCP 계정 조건·온프레미스 운영비가 미정이어서 실행 전체를 complete로 바꾸지 않는다. 새 최신 단가가 필요하면 기존 인증으로 lookup을 실행한다.
