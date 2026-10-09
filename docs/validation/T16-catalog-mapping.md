# T16 가격 API 매핑 구현·검증

검증일: 2026-10-09.

데모 사용량·절감 대안·리뷰 지점 1 표시의 후속 검증은 [T16-demo-completion.md](T16-demo-completion.md)에 기록했다. 아래는 원래 카탈로그 연결 단계의 범위와 결과다.

## 결과

기존에 가격표를 가져오지 못한 25개 비용 항목의 API 연결을 모두 보완했다. 시크릿 접근 요청, S3 요청, 로드밸런서 송신 처리 비용도 별도로 추가했다. 실제 조회는 AWS 21개, GCP 23개 모두 성공했고 `prices.json`은 `complete`, 조회 오류는 0개다.

월 비용 계산 결과는 `partial`이다. 가격표 연결은 완료됐지만 트래픽·로그·이미지 저장량, 선택적 서비스의 사용 여부, 무료 적용 조건·계정 기존 사용량, 앱 추가분과 수용량은 모두 확인된 상태가 아니다. 현재 결과를 전체 월 요금이나 실제 청구서로 설명하면 안 된다.

## 무엇을 바꿨는가

- AWS 로그·송신에는 정확한 `usage_type`과 목적지를 지정했다. 공인 IPv4, 커스텀 메트릭, 시크릿, 감사 S3 저장소와 요청 비용의 조회 연결을 추가했다.
- GCP에는 실제 공개 API에서 확인한 SKU·서비스·리전·상품 분류를 지정했다. NAT와 로드밸런서는 v2beta 카탈로그의 `Networking` 서비스에서 조회한다. 입력이 다른 리전·DB 규격·송신 목적지라면 선택자도 바꿔야 한다.
- GCP v2beta의 정확한 SKU를 직접 조회한다. 공개 `Default` 종량제를 선택하고 약정 모델을 선택하지 않는다. API가 제공하지 않는 가격 적용일은 미제공으로 보존한다.
- 시크릿은 GB 저장량이 아닌 시크릿/활성 버전의 월 사용량, AWS 메트릭은 메트릭의 월 사용량, GCP Prometheus는 샘플 수로 계산한다. 백만 샘플당 반환 가격은 샘플당 단가로 정규화한다.
- Public NAT는 게이트웨이 개수가 아니라 할당된 VM-hours로 입력한다. 32대 초과의 상한 계산과 Private NAT는 현재 별도 모델이 필요하여 거부한다.
- GCP 로그 추가 보존은 기본 포함 기간을 넘는 사용량으로 구분했다. 로드밸런서 송·수신 처리량, 시크릿 저장과 접근 요청, S3 저장과 요청도 각각 별도 항목이다.
- 무료 구간의 가격표도 원본 그대로 저장한다. 확인된 적용 조건과 계정/프로젝트의 기존 사용량이 없으면 월 비용은 `unverified_free_tier`로 남긴다. 미조회 또는 미정 사용량을 0원으로 바꾸지 않는다.

## 산출물

- [자원 목록 예시](../../skills/deploy-analyze/references/examples/pricing/demo-catalog-inventory.json): 정확한 API 선택자와 사용량 미정을 함께 보존한다. 다른 구성에서 사용할 때는 해당 구성과 대조한다. 단가 자체를 내장하지 않는다.
- [실제 조회 결과](t16-catalog-mapping/prices.json): AWS 21개·GCP 23개 공개 단가, 원본 Money·단위·구간과 조회 시각을 보존한다.
- [검증 결과](t16-catalog-mapping/verification.json): 수정 전 미조회 25개가 모두 조회됐는지, 입력·결과 해시와 설정 보존 여부를 확인한다.
- [비용 보고서](t16-catalog-mapping/budget.md): 확인된 소계와 남은 월 비용 미산정 사유를 표시한다. 동일 폴더에 입력·자원 평가·계산 결과·비용 요약을 보존한다.
- `tests/fixtures/pricing/mapping/`: 공개 API 응답 10개 AWS 상품과 17개 GCP SKU를 저장한 회귀 검증 자료다. 인증정보와 실제 시크릿 값은 포함하지 않는다.

## 검증 근거와 한계

demo-app 구성 기준은 커밋 `7893547913b57705d7f2e366f375b15beadcbba4`, 참조 모듈은 `v1.16.0`이다. AWS ReadOnlyAccess와 지정된 기존 GCP 계정으로 가격을 읽었다. GCP 노출·주소·NAT 설정도 읽기 전용으로 확인했다. 사용자 승인으로 앞서 활성화한 Cloud Billing API 외에 이번 매핑 작업의 API 설정 변경·배포·인프라 생성은 없다.

전체 로컬 테스트 182개가 통과했다. 새 검증은 정확한 서비스·상품·단위 연결, 백만 샘플당 가격, NAT 수량 오류·상한 거부, 무료 구간 보존과 적용 조건 차단, 시크릿 단위 오용을 확인한다. 별도로 44개 항목을 실제 API로 조회했고, 입력·단가·평가 해시를 대조하여 비용 계산과 보고서 생성을 검증했다. 임시 앱의 `config.yaml` SHA-256은 분석 전후 동일하다.

앞서 대표 자원 범위에서 정상 예산·예산 초과·예산 미입력·일부 API 실패·크기 변경 5가지 시나리오와 단일 AWS 노드 축소 대안의 월 37.96 USD 차액도 실제 단가로 검증했다. 이 절감액은 지정한 대표 자원 범위의 대안이며 전체 인프라 절감액으로 확대하지 않는다.

조건부 커스텀 메트릭·감사 보존 비용은 사용 여부와 사용량을 확인해야 한다. GCP 인터넷 송신 예시는 서울에서 한국으로 향하는 Premium 트래픽만 지정했다. 다른 목적지, 추가 네트워크 텔레메트리 비용, 실제 계정의 모든 청구 항목을 자동으로 발견하는 기능은 아니다. 원격 CI와 실제 대화형 스킬의 리뷰 지점 1 UX는 이 기록에서 검증 완료로 처리하지 않는다.

## 재현 방법

기존 인증이 준비된 환경에서 다음과 같이 새 가격을 조회한다. `<analysis-dir>`은 생성한 결과를 보관할 디렉터리다. 명령에서 입력 예시와 결과 경로를 구분한다.

```sh
python skills/deploy-analyze/scripts/price.py map \
  --inventory skills/deploy-analyze/references/examples/pricing/demo-catalog-inventory.json \
  --output <analysis-dir>/pricing-input.json \
  --assessment <analysis-dir>/resource-assessment.json

python skills/deploy-analyze/scripts/price.py lookup \
  --input <analysis-dir>/pricing-input.json \
  --output <analysis-dir>/prices.json

python skills/deploy-analyze/scripts/price.py calculate \
  --input <analysis-dir>/pricing-input.json \
  --prices <analysis-dir>/prices.json \
  --assessment <analysis-dir>/resource-assessment.json \
  --output <analysis-dir>/costs.json
```

AWS SDK의 기존 인증과 GCP ADC를 기본으로 사용한다. 기존 gcloud 로그인 계정을 명시하려면 `lookup --gcp-account <account> --gcp-quota-project <project>`를 추가한다. 비밀 키·토큰은 JSON이나 명령 인자에 넣지 않는다. 이 예시의 map·calculate 종료 코드 3은 남은 사용량·조건 미정을 뜻하며, 이번 실제 lookup의 종료 코드는 0이었다.
