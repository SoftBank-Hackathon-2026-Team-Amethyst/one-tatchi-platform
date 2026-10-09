# 가격 조회 · 비용 계산 계약 (T16 / C1)

이 문서는 배포 분석 도구의 구성 입력, 단가 조회 결과, 비용 계산 결과와 실패 처리 계약을 정의한다. 스킬 원본은 platform에, 실제 분석 산출물은 대상 앱의 `.deploy/analysis/`에 둔다. C1은 계약과 예시를 추가하는 커밋이다. C2에서 입력 검증과 AWS 단가 조회를 구현했고 C3에서 GCP 단가 조회를 연결했다. 비용 계산은 C5에서 추가한다.

## 확정한 도구 구성

- 진입점은 `scripts/price.py` 하나다. 공급자별 조회와 계산 내부는 필요에 따라 모듈로 나눈다.
- 계산할 구성은 명시적인 JSON으로 받는다. Terraform 실행, apply, state 다운로드로 입력을 자동 추출하지 않는다.
- `pricing-input.json`, `prices.json`, `costs.json`을 분리해 보존하고 기존 Markdown 보고서로 연결한다.
- 금액과 사용량 계산은 `Decimal`을 사용한다. 소수는 JSON 십진 문자열로 저장하고 표시 단계에서 반올림한다.
- 인증은 SDK 기본 자격증명 경로 또는 환경변수로 전달한다. 입력 · 출력 · 오류에 인증정보를 기록하지 않는다.
- 조회 실패나 사용량 미정은 누락으로 남긴다. 미조회 항목을 0원으로 대체하지 않는다.

## 기존 시스템과의 연결

1. 예산 분석 스킬이 브리프의 KRW 예산 범위, 트래픽 추천, 환경 루트와 참조 태그에서 명시적인 입력을 만든다.
2. 도구가 입력을 검증하고 후보별 단가를 조회한다. AWS와 GCP 단가를 같은 형태로 정규화한다.
3. 계산 결과를 `.deploy/analysis/budget.md`와 `.deploy/report.md`에서 함께 사용한다.

브리프의 다섯 질문과 [예산 범위 계약](brief-format.md)은 유지한다. 트래픽 분석의 Markdown 형식, `plan.yaml`과 `config.yaml`의 소유권을 바꾸지 않는다. 이 계약 추가만으로 분석기 실행 순서나 기존 보고서 작성 지침을 변경하지 않으며, 해당 연결은 C6에서 적용한다. `aws | gcp | onprem` 중 단일 대상을 하나의 후보로 계산하고 하이브리드 후보는 받지 않는다.

## CLI 계약

validate와 AWS · GCP lookup은 실행할 수 있다. calculate는 C5에서 구현할 인터페이스이며 아직 실행할 수 없다. `<skill-dir>`은 설치된 deploy-analyze 디렉터리다. 모든 파일 경로를 명시하며 작업 디렉터리에서 앱 루트를 추측하지 않는다.

```sh
python <skill-dir>/scripts/price.py validate --input <app-root>/.deploy/analysis/pricing-input.json
python <skill-dir>/scripts/price.py lookup --input <app-root>/.deploy/analysis/pricing-input.json --output <app-root>/.deploy/analysis/prices.json
python <skill-dir>/scripts/price.py calculate --input <app-root>/.deploy/analysis/pricing-input.json --prices <app-root>/.deploy/analysis/prices.json --output <app-root>/.deploy/analysis/costs.json
```

- `validate`: 네트워크 없이 입력만 검사하며 파일을 쓰지 않는다.
- `lookup`: 입력과 공급자 응답을 검증하고 단가 결과를 저장한다. 비용 계산은 하지 않는다.
- `calculate`: 저장된 입력과 단가를 사용하며 네트워크나 클라우드 변경을 수행하지 않는다.
- 인증값을 CLI 인자나 JSON에 넣는 옵션은 제공하지 않는다.
- 표준 출력은 `status`, `output`(파일을 쓰지 않으면 null), `issues`를 담은 JSON 객체 한 개다. 상세 결과는 지정한 출력 파일에 저장한다. 진단 메시지는 표준 오류에 쓰며 인증 헤더 · 비밀값 · 원본 SDK 예외 전체를 출력하지 않는다.
- CLI의 입력 오류 issue는 code: invalid_input, 파일 · 내부 오류는 code: io_error 또는 internal_error를 사용한다. 형식은 조회 issue와 같고 후보 · 항목을 특정할 수 없으면 해당 ID는 null이다.
- 필수 옵션 누락과 알 수 없는 옵션은 입력 오류다. 모든 명령에서 종료 코드의 의미를 동일하게 유지한다.

| 종료 코드 | 의미 | 결과 파일 |
|---|---|---|
| 0 | 입력 검증 성공 또는 필요한 항목을 모두 처리했다. | lookup · calculate는 complete 결과를 쓴다. |
| 2 | 입력 JSON · 계약 · 파일 간 연결 오류다. | 기존 결과를 보존한다. |
| 3 | 조회 또는 산정의 일부가 실패했거나 필수 사용량이 미정이다. | partial 결과와 누락 항목을 쓴다. 모두 실패해도 partial이다. |
| 1 | 파일 접근 · 저장 실패 또는 예상하지 못한 내부 오류다. | 새 결과를 사용 가능한 것으로 보고하지 않는다. |

예산 초과는 실행 실패가 아니다. 완전한 계산 결과가 예산을 넘더라도 종료 코드는 0이며 `budget.status`로 표시한다. 예산이나 환율 미정만으로 USD 계산 자체를 partial로 만들지는 않는다.

## C4 자원 목록 매핑

price.py map --inventory <inventory.json> --output <pricing-input.json> --assessment <resource-assessment.json>으로 스킬이 명시한 자원 목록을 가격 입력으로 변환한다. [자원 매핑 계약](resource-mapping.md)에 출처 우선순위·필수 자원·공유 범위·replicas와 노드 증설 구분을 정의한다. 이 명령은 네트워크나 Terraform을 실행하지 않는다. 부분 매핑은 종료 코드 3과 미정 항목을 남긴다. 산출물 둘의 해시를 맞춰 확인해야 하며 단가 조회 성공과는 구분한다.

## C2 AWS 조회 사용법과 지원 범위

의존성은 스킬의 requirements.txt에 있다. 다음 명령은 실제 앱 입력을 검증하거나 단가를 조회한다.

```sh
uv run --no-project --with-requirements <skill-dir>/requirements.txt python <skill-dir>/scripts/price.py validate --input <app-root>/.deploy/analysis/pricing-input.json
uv run --no-project --with-requirements <skill-dir>/requirements.txt python <skill-dir>/scripts/price.py lookup --input <app-root>/.deploy/analysis/pricing-input.json --output <app-root>/.deploy/analysis/prices.json
```

AWS SDK 기본 자격증명 경로를 사용한다. 필요한 읽기 권한은 pricing:DescribeServices, pricing:GetAttributeValues, pricing:GetProducts다. API 클라이언트는 us-east-1에 접속하고 상품 조건은 후보의 region을 사용한다. 연결 제한은 5초, 응답 제한은 15초, SDK 표준 재시도는 최초 요청을 포함해 최대 3회다. 자격증명을 JSON이나 명령 인자에 넣지 않는다.

조회는 공개 On-Demand USD 단가를 사용한다. 약정 할인 · 크레딧 · 계정별 할인과 세금은 포함하지 않는다. API 응답의 SKU와 가격 적용 시점을 보존하며, 복수 상품이나 중복 · 불연속 과금 차원을 임의로 선택하거나 더하지 않는다.

| resource_kind / billing_dimension | 필수 attributes |
|---|---|
| ec2 / instance_hours | instance_type, operating_system, tenancy |
| rds / instance_hours | instance_class, engine, deployment |
| rds / storage | usage_type, engine, deployment |
| ebs / storage | usage_type |
| eks / cluster_hours | usage_type |
| nat / gateway_hours, processed_data | usage_type |
| alb / load_balancer_hours, lcu_hours | usage_type |
| ecr / storage | usage_type |
| logs / ingestion, storage | usage_type |
| internet_egress / transfer | usage_type, to_location |

usage_type은 공급자 카탈로그에서 확인한 정확한 usagetype 문자열이다. 지역 접두사를 추측해 만들지 않는다. 조회기는 DescribeServices로 서비스 필드를 확인하고 GetAttributeValues로 usage_type이 존재하는지 확인한다. 자원 목록에 필요한 사용 유형을 채우는 작업은 C4와 연결된다. 기본 EC2 프로필은 Compute Instance · preInstalledSw: NA · capacitystatus: Used이며 이에 충돌하는 속성은 거부한다.

추가 필터는 operation, license_model, volume_api_name, product_family, to_location, from_location을 사용할 수 있다. API 속성 이름으로 변환한 뒤 서비스 메타데이터에 있는지 확인한다. rate_code는 상품 필터가 아니라 가격 차원 선택용이며, 선택된 구간이 전체 사용량을 설명하지 못하면 미조회로 남긴다. internet_egress는 견적 리전을 fromRegionCode로 지정한다. 정확한 과금 차원을 확정하지 못하면 다른 공식 가격으로 임의 대체하지 않는다.

Hrs · hrs · Hours는 hour, GB-Mo · GB-month는 gb_month, GB는 gb, Requests는 request, LCU-Hrs는 lcu_hour로 정규화한다. 변환 계수는 1이다. 단위가 맞지 않거나 조건부 appliesTo가 있는 항목은 미조회로 남긴다. GB를 GiB로 임의 변환하지 않는다.

C3에서 GCP 조회를 연결했다. 온프레미스의 비어 있지 않은 항목은 unsupported_resource로 남긴다. 어느 공급자의 조회가 실패해도 다른 공급자의 성공 결과는 보존한다. 온프레미스의 빈 items는 조회할 클라우드 항목이 없어 complete이며 운영 비용 미산정 가정은 입력에 유지한다. 비용과 예산 판정은 아직 생성하지 않는다.

로컬 테스트:

```sh
uv run --no-project --with-requirements skills/deploy-analyze/requirements.txt python -B -m unittest discover -s skills/deploy-analyze/tests -v
```

[pricing 워크플로](../../../.github/workflows/pricing.yml)가 변경된 스킬의 가격 조회와 기존 브리프 테스트를 함께 실행한다. 합성 API 응답 테스트와 실제 API 실조회는 구분한다.

## C3 GCP 조회 사용법과 지원 범위

lookup 명령과 입력 파일 형식은 AWS와 같다. 후보 target은 gcp, 견적 region은 asia-northeast3 같은 실제 리전 코드다. 스킬의 requirements.txt에 google-auth와 requests를 추가했다.

인증은 google.auth.default()로 기존 ADC를 읽는다. 기존 사용자 ADC의 스코프는 유지한다. 스코프가 필요한 서비스 계정 자격증명에는 cloud-billing.readonly를 메모리에서만 적용한다. 도구는 gcloud 로그인, ADC 파일 작성, IAM 변경, API 활성화를 수행하지 않는다. 기존 인증과 quota project 설정으로 Catalog API를 사용할 수 있어야 한다. 자격증명 로드 · 갱신 실패는 authentication_failed, API 비활성은 api_disabled로 기록한다.

Cloud Billing Catalog API의 services.list와 services.skus.list를 사용한다. 서비스 ID를 추측하지 않고 표시 이름으로 서비스를 찾으며, SKU 조회 시 currencyCode=USD를 명시한다. 페이지 크기는 5000이고 다음 페이지 토큰을 끝까지 처리한다. 동일 실행에서는 서비스와 SKU 목록을 재사용한다. 연결 제한은 5초, 응답 제한은 15초이며 인증 갱신은 최대 1회다. HTTP 429와 5xx는 재시도 가능 사유를 남기고 자체 Catalog 재시도는 하지 않는다.

[Catalog API 계약](https://docs.cloud.google.com/billing/docs/reference/rest/v1/services.skus/list)에 따라 리전 · 카테고리 · 소비 방식과 가격 적용 시점을 확인한다. 조회 시각과 effectiveTime은 구분한다. 전역 SKU는 GLOBAL 지리 정보 또는 명시적인 global 서비스 리전이 있을 때만 사용하며, 빈 리전 목록만으로 전역이라고 추정하지 않는다.

| resource_kind / billing_dimension | 조회할 서비스 표시 이름 |
|---|---|
| gke / cluster_hours | Kubernetes Engine |
| gke_node / cpu_hours, memory_hours | Compute Engine |
| gcp_disk / storage | Compute Engine |
| cloud_nat / gateway_hours, processed_data | Compute Engine |
| gcp_load_balancer / load_balancer_hours, processed_data | Compute Engine |
| cloud_sql / cpu_hours, memory_hours, instance_hours, storage | Cloud SQL |
| artifact_registry / storage | Artifact Registry |
| gcp_logs / ingestion, storage | Cloud Logging |
| gcp_internet_egress / transfer | Compute Engine |

각 항목의 attributes에 resource_family · resource_group과 정확한 description 또는 sku_id를 지정한다. 두 선택자를 함께 주면 모두 일치해야 한다. service_id를 추가하면 같은 표시 이름의 서비스를 구분할 수 있다. usage_type은 생략 시 OnDemand이며 다른 방식은 기본 견적에서 받지 않는다. 서버 크기나 SKU 설명을 추측하지 않고, 실제 T4 설정을 카탈로그의 정확한 항목으로 옮기는 규칙은 C4에서 정리한다. 후보가 여럿이면 ambiguous_sku로 남긴다.

CPU와 메모리는 각각 별도 item_id와 billing_dimension으로 기록한다. CPU 단위는 vcpu_hour, 메모리는 gib_hour를 사용할 수 있다. 예를 들어 노드 3대에 각 2 vCPU를 730시간 사용하면 quantity=3, monthly_usage=1460 vcpu_hour를 입력한다. 이는 단가 조회 입력의 사용량 예시이며 C3에서 월 비용은 계산하지 않는다.

단가와 구간 경계는 baseUnit · baseUnitConversionFactor로 정규화한다. h/s는 hour 또는 vcpu_hour, GiBy.h/GiBy.s/By.s는 gib_hour, GiBy.mo는 gib_month, GBy.mo는 gb_month, GiBy/GBy/By는 gib 또는 gb, count는 request를 지원한다. 필요한 baseUnit이 맞지 않으면 unsupported_unit으로 남긴다. 같은 월 단위는 공급자의 월 기준을 그대로 유지하며 바이트·초에서 월로 변환할 때의 기준은 730시간이다. displayQuantity는 표시 권장값이므로 가격에 곱하지 않는다.

공개 유료 구성의 기본 단가를 조회한다. 크레딧 · 약정 · 계정별 할인은 적용하지 않는다. 전체 단가가 0인 무료 SKU는 기본 후보에서 제외하고, 0원 구간이 있는 SKU는 무료 한도의 자격과 공유 범위가 확인되지 않아 unsupported_resource로 남긴다. 유료 SKU를 확정하지 못하면 가격을 임의 대체하지 않는다.

provider_details는 GCP price의 추가 근거다. 키는 usage_unit, base_unit, base_unit_conversion_factor, display_quantity, currency_conversion_rate, aggregation, effective_time, tiers다. 수치는 십진 문자열로 보존하며 tiers는 원본 시작 사용량 from, 정수부 units 문자열, nanos 정수를 담는다. aggregation은 공급자 aggregationLevel · aggregationInterval · aggregationCount 또는 null이다. 실제 계산기는 계정/프로젝트와 일/월 집계 범위를 확인해야 하며, 특히 일 단위 구간 요금을 월 사용량에 그대로 적용하면 안 된다. 이 처리는 C5에서 구현한다.

[gcp-input.json](examples/pricing/gcp-input.json)과 [gcp-prices-complete.json](examples/pricing/gcp-prices-complete.json)은 합성 서울 CPU 단가의 입력 · 결과 견본이다. 실제 API 조회 근거가 아니다.

## 공통 형식과 파일 연결

현재 입력 · 단가 · 계산 결과 예시의 `schema_version`은 `"2"`다. C3에서 GCP 원본 가격 근거를 보존할 provider_details를 추가하면서 버전을 올렸다. 입력 검증기는 기존 버전 `"1"` 입력도 지원하고 해시는 원래 입력 그대로 계산한다. lookup 출력은 항상 버전 `"2"`이며 계산 결과의 버전 2 구현은 C5에서 진행한다. 지원하지 않는 버전, 중복 JSON 키, 필수 키 누락, 정의되지 않은 키, 잘못된 타입은 오류다. 확장을 추가하면 계약 버전을 갱신한다.

- 금액 · 사용량 · 수량은 음수가 아닌 유한 십진 문자열이다. 지수 표기, NaN, Infinity와 쉼표를 허용하지 않는다. 개수 `quantity`는 양의 정수다.
- 조회 · 생성 시각은 UTC RFC 3339 문자열, 기준일은 `YYYY-MM-DD`다.
- `null`은 미정 또는 해당 없음이다. 0과 구분한다. 빈 문자열로 미정을 표시하지 않는다.
- `input_id`는 스킬이 매 실행마다 새로 부여하는 비어 있지 않은 식별자다. `candidate_id`와 `item_id`는 각각 입력 전체와 후보 안에서 유일하다.
- 입력 JSON을 키 정렬 · 공백 없는 직렬화 · UTF-8로 정규화하고 SHA-256을 계산한다. 모든 배열 순서는 보존한다. `prices.input_sha256`과 `costs.input_sha256`은 이 값과 일치해야 한다.
- 계산기는 `prices.schema_version`, `input_id`, `input_sha256`과 대상 · 리전 · 후보 · 항목 ID 집합을 대조한다. 누락, 중복, 추가 또는 불일치는 입력 오류다. 부분 조회 결과에도 각 입력 항목의 성공 · 실패 레코드가 있어야 한다.
- `costs.prices_sha256`에는 사용한 단가 파일의 같은 방식의 해시를 기록한다. Markdown 보고서도 input_id와 두 해시를 근거로 참조한다.
- 해시가 일치해도 가격이 최신이라는 뜻은 아니다. 보고서에 `queried_at`과 `effective_at`을 각각 표시하며, 입력이 달라지면 다시 조회 · 계산한다. 트래픽 추천이 바뀌면 자원 목록과 사용량 변경 여부를 확인한다.

## 구성 입력: pricing-input.json

최상위 키는 `schema_version`, `input_id`, `created_at`, `template_version`, `monthly_hours`, `monthly_budget`, `budget_basis`, `fx`, `candidates`다.

- `template_version`: 실제 자원 매핑에 참조한 `vX.Y.Z` 태그다.
- `monthly_hours`: 양의 십진 문자열. 기본 상시 시나리오는 `"730"`이며 시연 시간은 별도 입력으로 계산하고 가정에 표시한다.
- `monthly_budget`: T15의 `{min, max, currency: "KRW"}` 범위 또는 null이다. min · max는 정수이며 max는 null일 수 있다. 허용 범위는 brief-format.md의 선택값을 그대로 따른다. 원본 범위를 단일 값으로 바꾸지 않는다.
- `budget_basis`: `total | incremental`. 기본 제안은 total이다. incremental은 사용자가 비용 범위를 명시한 경우에만 사용하고 근거를 후보 가정에 남긴다.
- `fx`: null 또는 `{usd_to_krw, as_of, source}`. 환율은 양의 십진 문자열이고 출처는 비어 있지 않은 설명 또는 URL이다. 없으면 USD 결과는 남기되 KRW 비교는 미정이다.
- `candidates`: 비어 있지 않은 배열. 후보마다 `candidate_id`, `target`, `region`, `configuration_status`, `assumptions`, `items`를 둔다.
- `configuration_status`: `confirmed | assumed`. assumed이면 `assumptions`에 추정 구성과 근거를 기록한다.
- `region`: AWS · GCP는 견적 대상 리전 문자열, onprem은 null이다. API 접속 리전과 별개다.
- `items`: 비용 항목 배열. 비용 차원을 나누어 같은 자원의 시간 요금과 처리량 요금도 서로 다른 item_id로 표현한다. onprem의 클라우드 비용만 비교하는 경우 빈 배열을 허용하되 운영 비용 미산정을 가정에 표시한다.

항목마다 다음 키를 둔다.

| 키 | 의미 |
|---|---|
| item_id | 후보 안에서 유일한 비용 항목 식별자 |
| resource_id | 동일한 물리 자원 · 공유 자원을 식별하는 이름 |
| resource_kind | ec2, rds, gke_node 등 자원 종류 문자열 |
| billing_dimension | instance_hours, storage, processed_data 등 비용 차원 문자열 |
| attributes | 공급자 조회 필터에 사용할 문자열 매핑. 크기 · 엔진 · 운영체제 · tenancy · 배포 방식 등 조회에 필요한 값을 기록한다. |
| quantity | 같은 규격 자원 개수. 양의 정수 |
| shared | test/prod 또는 여러 앱이 공유하면 true |
| cost_type | fixed 또는 variable |
| unit | 계산기와 단가가 사용할 정규화 사용 단위 |
| monthly_usage | 자원 하나의 월 사용량 `{min, max}` 또는 null. min · max는 십진 문자열이며 max는 null을 허용한다. |
| incremental_usage | 현재 공용 환경에 앱 추가 시 자원 하나의 추가 사용량. monthly_usage와 같은 형식 |
| source | 구성 출처 `{path, ref, note}`. path는 설정 경로 또는 가정 이름, ref는 태그 · 커밋 또는 null, note는 선택 근거 |

사용량 범위는 `0 <= min <= max`이며, max가 null이면 상한 미정이다. monthly_usage는 앱 추가 후 구성 기준이며, 추가 사용량은 신규 자원을 포함한 비교의 정의를 가정에 적는다. 확인 가능한 범위에서 incremental_usage가 monthly_usage를 초과하면 입력 오류다. 미정 증분을 0으로 바꾸지 않는다. 상시 시간 항목의 사용량은 monthly_hours와 맞아야 하며 다른 과금 차원에 730을 일괄 적용하지 않는다.

지원할 정규화 단위는 `hour`, `gb_month`, `gib_month`, `gb`, `gib`, `request`, `vcpu_hour`, `gib_hour`, `lcu_hour`다. GB와 GiB를 혼용하지 않는다. 공급자 원본 단위와 변환 계수는 단가 결과에 남긴다. 새로운 단위는 계약과 계산기 지원을 함께 추가한다.

후보 내 `(resource_id, billing_dimension)`은 유일해야 한다. 공유 클러스터 · NAT · DB의 같은 과금 차원을 test/prod마다 중복 기록하지 않는다. SKU별 구간 계산은 동일 SKU · 단위의 사용량을 합친 뒤 수행한다. 증분 비용은 같은 구간 요금으로 계산한 추가 후 비용에서 기존 사용량(추가 후 사용량 − 추가 사용량)의 비용을 뺀다. 사용량 범위가 상관관계 없이 주어져 정확한 증분 범위를 계산할 수 없으면 증분을 미산정으로 표시한다. 또한 SKU와 무관한 계정 전체 무료 한도는 기본 견적에 적용하지 않는다.

## 단가 결과: prices.json

최상위 키는 `schema_version`, `input_id`, `input_sha256`, `queried_at`, `status`, `candidates`, `issues`다. status는 `complete | partial`이다.

각 후보는 `candidate_id`, `target`, `region`, `items`를 가진다. 각 항목은 `item_id`, `status`, `price`, `issue`를 가진다.

- status가 `available`이면 price를 기록하고 issue는 null이다.
- status가 `unavailable`이면 price는 null이고 issue에 원인을 남긴다.
- price 필수 키: `sku`, `provider_service`, `currency`, `source`, `effective_at`, `unit`, `source_unit`, `source_usage_per_unit`, `tiers`. 버전 2에서는 선택 키 provider_details를 추가한다. AWS는 기존 필수 키를 유지하고 GCP는 provider_details에 원본 가격 · 변환 · 집계 근거를 기록한다.
- currency는 USD다. source는 조회 API 식별자 또는 공식 자료 URL이다. 조회 시각과 가격 적용 시점을 구분한다.
- source_usage_per_unit은 정규화 단위 1에 해당하는 원본 사용량의 양의 십진 문자열이다. tiers의 단가는 이미 정규화 단위당 USD로 변환되어 있어 계산기에서 중복 환산하지 않는다.
- tiers는 `{from, to, unit_price}` 배열이다. 경계와 금액은 십진 문자열이며 마지막 to만 null이다. 첫 구간은 0에서 시작하고 구간은 빈틈 · 겹침 없이 오름차순이다. 구간 경계는 정규화 사용량 기준이다. 단일 요금도 `[0, 무한대)` 구간 하나로 표현한다.
- price.unit은 입력 item.unit과 일치한다. 단위 변환을 지원하지 않으면 unavailable로 기록한다.
- 여러 SKU가 일치하면 임의 첫 항목을 고르지 않는다. 필터로 하나를 확정하지 못하면 ambiguous_sku로 남긴다.

issue는 `{candidate_id, item_id, code, message, retryable}`이다. code는 `authentication_failed`, `permission_denied`, `api_disabled`, `timeout`, `rate_limited`, `not_found`, `ambiguous_sku`, `unsupported_resource`, `unsupported_unit`, `invalid_provider_response`, `unknown_usage`, `unknown_incremental_usage`, `unbounded_usage` 중 하나다. message는 비밀값을 제외한 원인이다. timeout · rate_limited는 재시도 가능한 것으로 표시할 수 있지만 자동 재시도 횟수는 공급자 구현에서 정한다.

최상위 issues는 실패 항목의 issue를 모은 목록이다. 인증 실패가 한 공급자에만 발생하면 해당 후보의 항목을 실패로 남기고 다른 후보 결과는 보존한다. 미조회 항목이 하나라도 있으면 partial이다.

## 계산 결과: costs.json

최상위 키는 `schema_version`, `input_id`, `input_sha256`, `prices_sha256`, `generated_at`, `queried_at`, `status`, `candidates`, `issues`다.

각 후보는 `candidate_id`, `target`, `region`, `configuration_status`, `assumptions`, `items`, `summary`, `budget`를 가진다.

항목별 결과는 `item_id`, `cost_type`, `status`, `total_usd`, `incremental_usd`, `issues`다. 항목 status는 `complete | partial`이며, 전체 · 증분 중 하나라도 산정되지 않으면 partial이다. 금액은 `{min, max}` 또는 null이다. 조회 · 사용량이 없으면 null과 사유를 남긴다. 계산 가능한 하한이 있지만 사용량 상한이 없으면 max는 null이다.

summary는 다음 키를 가진다.

- `fixed_usd`, `variable_usd`: 조회와 사용량이 알려진 항목의 소계 범위다. 항목 누락 시 완전한 합계로 표시하지 않는다.
- `known_total_usd`, `known_incremental_usd`: 알려진 항목의 소계 범위다. 알려진 항목이 하나도 없으면 null이다.
- `total_complete`, `incremental_complete`: 해당 범위의 모든 항목이 산정됐는지 표시한다. 비용 상한이 미정이면 false다.
- `total_krw`, `incremental_krw`: 완전한 USD 합계와 fx가 모두 있을 때만 산정한다. 그 외에는 null이며 USD 소계로 임의 KRW 합계를 만들지 않는다.

계산은 단가 × quantity × 자원 하나의 사용량을 기반으로 하되 SKU별 구간 요금을 적용한다. 0원은 실제 0원 SKU, 명시한 0 사용량 또는 기존 온프레미스 장비의 클라우드 비용 범위에서만 사용할 수 있다. onprem의 빈 items는 클라우드 비용 범위에서 USD 0으로 집계하며 운영 비용 미산정을 assumptions에 표시한다. 이를 전체 운영비 0원으로 설명하지 않는다.

budget 키는 `basis`, `range_krw`, `status`, `reason`이다. basis와 range_krw는 입력을 보존한다. 예산 경계와 구체적인 계산 정책은 C5에서 구현하지만 다음 상태를 구분한다.

- `over`: 비교 가능한 비용 하한이 예산 상한보다 크다. 누락이 있어도 알려진 비용만으로 초과가 증명되면 over가 가능하며, 결과의 부분 상태는 유지한다.
- `within`: 비교 범위가 완전하고 환율과 예산 상한이 있으며 비용 상한이 예산 상한 이하이다.
- `may_exceed`: 완전한 비용 범위가 예산 상한을 가로지른다.
- `unknown`: 예산 · 상한 · 환율 부재나 미산정 항목으로 판단할 수 없다. reason에 원인을 적는다.

입력의 configuration_status가 assumed이면 완전하게 계산했어도 추정 구성 기준임을 표시한다. 예산 초과 경고와 절감안은 C6의 보고서에 연결한다. 절감액은 별도 대안 견적을 계산한 경우에만 표시한다.

## 출력 파일과 실패 처리

- 입력과 기존 결과는 임의로 고치지 않는다. 새 결과를 재사용할 때 해시 검사를 생략하지 않는다.
- 출력 부모 디렉터리는 존재해야 한다. 파일 저장은 같은 디렉터리에 임시 파일을 작성한 뒤 교체한다. 입력 오류나 저장 실패에서는 기존 결과를 보존한다.
- 입력 파일과 출력 파일은 같을 수 없다. 출력 경로의 심볼릭 링크는 따라가지 않는다.
- partial 결과는 성공한 부분과 누락을 함께 담아 기존 결과를 교체한다. 보고서가 이전 complete 결과를 새 결과로 착각하지 않도록 status · input_id · queried_at을 확인한다.
- 두 결과 파일을 동시에 교체하는 트랜잭션은 제공하지 않는다. calculate는 prices의 입력 해시가 현재 입력과 일치하는 경우에만 실행한다.

## 계약 예시와 검증 범위

[examples/pricing/](examples/pricing/)에는 입력 · 완전 조회 · 부분 조회 · 계산 결과 · 입력 오류 예시가 있다. 모든 단가와 환율은 계약 설명용 합성값이며 실제 API 조회 또는 현재 요금을 증명하지 않는다. 정상 비용은 명시적인 수량 · 사용량으로 재계산할 수 있다.

- input.json + prices-complete.json → costs-complete.json: validate · lookup · calculate 종료 코드 0. 월 합계는 `(0.1 × 2 × 730) + (0.05 × 1 × 730) = 182.5 USD`, 합성 환율 1400 기준 255500 KRW다.
- input.json + prices-partial.json → costs-partial.json: lookup · calculate 종료 코드 3. DB 미조회로 알려진 소계는 146 USD이며 예산 판정은 unknown이다.
- input-invalid.json → validation-error.json: validate 종료 코드 2. 하이브리드 입력을 거부하고 결과 파일은 쓰지 않는다.


- C1 검증: JSON 파싱, 입력 · 결과의 필드와 식별자 연결, 해시 일치, 합성 비용 재계산, partial의 null · 누락 사유, 입력 오류 예시를 확인한다.
- C2 · C3 검증: 입력 검증, AWS · GCP 응답 정규화, ADC 보존과 공급자별 실패 처리는 자동 테스트로 확인한다. C5에서는 계산기와 결과 연결 검증을 추가한다. 이 계약을 구현하는 CLI와 검증기의 정상 · 부분 실패 · 입력 오류, 단위 · 구간 요금, 해시 불일치 · 기존 파일 보존 테스트를 추가한다.
- C7 검증: 실제 API 단가 · 조회 시각과 demo-app 분석 보고서를 검증한다. C1 예시를 실제 조회 증거로 사용하지 않는다.
