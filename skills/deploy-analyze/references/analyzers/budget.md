# 예산 분석기

후보별 월 비용을 실제 가격 조회 도구와 계산 결과로 비교한다. 입력은 앱 레포와 `.deploy/brief.md`, 트래픽 결과이며 산출물은 `.deploy/analysis/budget.md`와 `cost-summary.md`다. 단일 배포 대상 AWS · GCP · 온프레미스를 비교한다.

## 확인할 입력

- 브리프의 KRW monthly_budget 범위를 그대로 사용한다. null과 max:null은 미정이며 무제한이나 0원이 아니다.
- 트래픽 분석 결과의 서비스별 replicas · CPU · 메모리와 실제 환경 루트의 자원을 함께 확인한다. 노드 수를 replicas와 같은 비율로 바꾸지 않는다.
- 값은 환경 루트 → 실제 참조 태그의 모듈 기본값 → 문서화한 가정 순으로 사용한다. SDK·모듈·브리프의 다른 계약을 임의로 변경하지 않는다.
- 비용 비교의 기본 범위는 전체 비용이다. 사용자에게 명시된 경우에만 앱 추가 증분을 기준으로 판정한다. test/prod 공유 자원을 중복 계산하지 않는다.
- 환율 값·기준일·출처를 명시 입력한다. 환율을 모르면 USD 결과를 남기고 KRW 예산은 미정으로 둔다.

## 실행 순서

아래 `<skill-dir>`은 deploy-analyze 설치 디렉터리, `<app-root>`는 실제 대상 앱이다. 실행 전 [자원 매핑](../resource-mapping.md), [가격 계약](../price-format.md), [계산 계약](../cost-calculation.md)을 읽는다. 의존성은 requirements.txt에 있다.

1. 분석 스킬이 환경 루트와 참조 모듈·차트, 트래픽 결과를 읽어 `pricing-inventory.json`을 작성한다. 정확한 SKU 또는 사용 유형을 아직 모르면 비용 항목을 삭제하거나 가격을 만들어 넣지 않는다. C4 형식에 맞게 미정 사용량과 가정을 기록한다. `demo-inventory.json`은 설정 스냅샷 예시이며 최신 앱 구성으로 다시 작성해야 한다.
   `demo-catalog-inventory.json`은 정확한 공개 카탈로그 선택자를 연결한 서울 구성 예시다. 같은 규격·리전·과금 방식인지 확인한 후 필요한 선택자를 사용한다. 다른 트래픽 목적지나 DB 규격에 그대로 적용하지 않는다. GCP의 Networking·무료 구간·NAT 과금 수량과 시크릿·메트릭의 단위는 가격 계약을 따른다.
2. map으로 자원 목록을 가격 입력으로 변환한다. 트래픽이 없거나 기본 시나리오라면 그렇게 표시하고 종합 때 최종 추천 크기로 재계산한다.
3. lookup으로 실제 단가를 조회한다. 가격 API가 실패했을 때 알고 있는 공개 가격을 최신 조회값처럼 대신 넣지 않는다.
   사용량·수량만 바뀌고 가격 선택 조건이 같은 데모/대안은 가격 계약의 `reuse-prices`로 원본 입력·단가를 검증해 재사용할 수 있다. 원래 조회 시각과 재사용 근거를 함께 남긴다. [ADR-0014](../../../../docs/adr/0014-demo-cost-assumptions.md)의 숫자는 데모 가정이며 일반 사용자에게 자동 적용하지 않는다.
4. calculate로 비용과 예산을 계산한다. C4 입력에서는 resource-assessment.json도 전달한다.
5. report로 후보 비용 표와 추천 후보의 비용 요약을 같은 costs.json에서 생성한다. 추천 후보 ID는 선택한 배포 대상과 구성에 맞게 명시한다.

```sh
uv run --no-project --with-requirements "<skill-dir>/requirements.txt" python "<skill-dir>/scripts/price.py" map --inventory "<app-root>/.deploy/analysis/pricing-inventory.json" --output "<app-root>/.deploy/analysis/pricing-input.json" --assessment "<app-root>/.deploy/analysis/resource-assessment.json"
uv run --no-project --with-requirements "<skill-dir>/requirements.txt" python "<skill-dir>/scripts/price.py" lookup --input "<app-root>/.deploy/analysis/pricing-input.json" --output "<app-root>/.deploy/analysis/prices.json"
uv run --no-project --with-requirements "<skill-dir>/requirements.txt" python "<skill-dir>/scripts/price.py" calculate --input "<app-root>/.deploy/analysis/pricing-input.json" --prices "<app-root>/.deploy/analysis/prices.json" --assessment "<app-root>/.deploy/analysis/resource-assessment.json" --output "<app-root>/.deploy/analysis/costs.json"
uv run --no-project --with-requirements "<skill-dir>/requirements.txt" python "<skill-dir>/scripts/price.py" report --input "<app-root>/.deploy/analysis/pricing-input.json" --prices "<app-root>/.deploy/analysis/prices.json" --costs "<app-root>/.deploy/analysis/costs.json" --assessment "<app-root>/.deploy/analysis/resource-assessment.json" --candidate "<candidate-id>" --budget-output "<app-root>/.deploy/analysis/budget.md" --summary-output "<app-root>/.deploy/analysis/cost-summary.md"
```

각 명령의 종료 코드 3은 유효한 부분 결과다. 출력의 status와 issues를 확인한 뒤 다음 단계로 전달할 수 있다. 1·2는 파일·내부·입력 오류이므로 원인을 바로잡고 해당 단계를 다시 실행한다. 종료 코드 3을 성공 코드 0으로 바꾸거나 누락 항목을 제거하지 않는다. 셸의 set -e만으로 순서를 실행하면 부분 결과에서 중단될 수 있으므로 종료 코드를 분기해서 처리한다.

## 비용과 절감안 표시

report가 만든 표·요약의 금액·판정·조회 시각을 그대로 사용한다. 사람이 읽는 설명은 주변에 추가할 수 있지만 독립적으로 금액을 추정하거나 소계를 전체 비용으로 고치지 않는다.

- over면 경고와 대안 견적 또는 절감액 미산정 사유를 함께 남긴다.
- may_exceed면 사용량 범위에 따라 예산을 넘을 수 있음을 표시한다.
- unknown이면 필요한 단가·사용량·환율·구성 조건을 표시하며 예산 충족으로 바꾸지 않는다.
- 온프레미스는 클라우드 비용과 전기·장비·인건비를 구분한다. 클라우드 0원으로 전체 예산을 충족했다고 말하지 않는다.

절감안을 수치로 제시하려면 별도 대안 입력·단가·비용을 만든 뒤 compare로 savings.json을 생성한다. report에 `--savings <savings.json> --alternative-costs <alternative-costs.json>`를 함께 전달한다. 별도 대안이 없으면 보고서에 그 이유가 표시된다. 더 작은 DB·노드·NAT 공유·시연 운영 시간 등은 가용성·규제·템플릿 지원을 확인해야 하는 검토 방향이다. replicas 축소만으로 노드 절감액을 만들지 않는다.

## 결과와 종합 연결

`.deploy/analysis/budget.md`에는 후보별 고정/변동 소계 · 전체/증분 · 원화 · 예산 판정 · 조회 시각, 경고·절감안, 미산정 사유, SKU·단위·가격 적용 시점, 환율·가정·근거 해시가 나온다.

`.deploy/analysis/cost-summary.md`에는 추천 후보의 비용 블록이 나온다. 최종 보고서는 [보고서 형식](../report-format.md)의 pricing-summary 표지 안에 이 내용을 넣는다. report 명령의 `--report <app-root>/.deploy/report.md`로 그 블록만 갱신할 수 있다. 합성 예시와 실제 API 검증은 구분하고, `.deploy/config.yaml`은 수정하지 않는다.
