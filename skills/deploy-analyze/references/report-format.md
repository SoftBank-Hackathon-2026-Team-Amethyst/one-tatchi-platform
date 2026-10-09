# 분석 보고서와 배포 설정 형식

## `.deploy/report.md`

리뷰 지점 1에서 사람이 읽는다. 결론을 맨 위에 둔다. 사용자의 언어로 쓴다.

```md
# 분석 보고서

## 추천
- 배포 대상: onprem
- 이유 한 줄: 민감 데이터(regulated)와 사내 보관 요구. 맥북 k3d 클러스터와 self-hosted runner가 있다
- 검토한 대안: aws / gcp (각 후보를 제외한 이유)

<!-- pricing-summary:start -->
price.py report가 만든 추천 후보 비용 블록을 여기에 갱신한다.
<!-- pricing-summary:end -->

## 인프라 구성
서비스별 런타임 · 크기(replicas, resources) · DB · 네트워크(노출 여부) 표.

## 확장 계획
지금 구성이 버티는 한계와 그 다음 순서.

## 필요한 코드 수정
Dockerfile 추가, 로컬 DB를 운영 DB로, 헬스체크 추가, lint · build 스크립트 추가 등. 없으면 "없음".

## 보안 · 규제
발견한 문제와 조치. 배포를 막는 것은 따로 표시. compliance 값과 운영 승인 경로(regulated → prod 승인 / none → prod-auto).

## 가정
브리프에 없어서 추정한 값과 근거. 없으면 "없음".
```

## 비용 표와 추천 요약의 연결

예산 분석기는 [예산 분석 지침](analyzers/budget.md)과 [보고서 생성 계약](cost-reporting.md)을 따른다. budget.md 비용 표와 report.md의 비용 블록은 같은 costs.json에서 생성한다. 표의 소계나 항목별 범위를 다시 더해 전체 비용을 만들지 않는다.

분석 보고서의 추천 후보를 정한 뒤 해당 candidate_id로 price.py report를 실행한다. --summary-output은 .deploy/analysis/cost-summary.md다. --report .deploy/report.md를 함께 주면 pricing-summary 표지 안만 교체하고 추천 이유·인프라·확장·코드 수정·보안·기존 본문은 보존한다. 표지가 없거나 중복되면 기존 본문을 임의로 덮어쓰지 않고 실패한다. 처음 작성하거나 이전 형식에서 갱신할 때는 위 표지 한 쌍을 두고 기존 수동 비용 문구를 제거한다.

- 전체/증분과 USD/KRW, 소계/완전한 합계, 명시/가정 구성을 구분한다.
- 예산 초과와 초과 가능 경고, 미산정 사유와 절감안 또는 절감액 미산정 사유를 요약에도 남긴다.
- 조회 시각과 가격 적용 시점, 환율 값·기준일·출처와 근거 JSON을 확인한다. 보고서 생성 시각을 단가 조회 시각으로 사용하지 않는다.
- 온프레미스 클라우드 0원과 운영 비용 미산정을 구분한다.
- 최종 services의 replicas · resources · DB · 환경 범위가 계산 입력과 다르면 자원 매핑부터 다시 실행하고 비용 블록을 재생성한다. 가격 조건·단위가 바뀌면 새 lookup을 실행한다. 사용량·수량만 바뀌는 시나리오는 `reuse-prices`로 원본 조건과 해시를 검증하고 재사용 근거를 남길 수 있다. 조회 시각을 새로 만들거나 해시만 임의로 수정하지 않는다.
- API가 실패하면 부분 결과를 사용하고 알려진 가격을 최신 조회값처럼 대체하지 않는다.

## `.deploy/config.yaml`과 `.deploy/plan.yaml`

두 파일로 나눈다. `config.yaml`은 **파이프라인이 읽고 사람이 지키는 값**(CODEOWNERS 리뷰 대상), `plan.yaml`은 **스킬 사이의 인계값**(리뷰 없이 스킬이 갱신). 키와 열거값은 영어, 주석은 사용자의 언어.

| 파일 | 키 | 누가 쓰나 | 누가 읽나 |
|---|---|---|---|
| `config.yaml` | `template_version` | `deploy-provision`(처음), 이후 `template-update` PR | `config-guard`, `bump-template-version.sh` |
| `config.yaml` | `compliance` | `write_brief.py`(브리프 답변) | `deploy.yml` gate(운영 environment 선택), `config-guard` |
| `plan.yaml` | `target` | `deploy-analyze` 종합 | `deploy-provision`(워크플로 호출부 기본 대상, `infra/envs/<target>`) |
| `plan.yaml` | `services` | `deploy-analyze` 종합 | `deploy-provision`(값 파일, `services` JSON, `checks` 입력, `smoke.json`), `check-artifacts.sh` |

`config.yaml`은 `write_brief.py`와 `deploy-provision`(`template_version` 한 번)만 쓴다. 종합 단계는 건드리지 않는다.

```yaml
# .deploy/config.yaml — 파이프라인이 읽는다. 사람이 지키는 값만 둔다 (CODEOWNERS).
template_version: v1.9.0
compliance: regulated
```

```yaml
# .deploy/plan.yaml — 스킬 사이의 인계값. deploy-analyze가 쓰고 deploy-provision이 읽는다. 파이프라인은 읽지 않는다.
target: onprem                  # aws | onprem | gcp. 워크플로 호출부의 기본 대상(레포 변수 DEPLOY_TARGET이 없을 때)
services:
  - name: demo-app-be           # 이미지 저장소 · Rollout · k8s Service 이름
    path: be                    # 빌드 컨텍스트 (Dockerfile 위치)
    runtime: node               # node | python → checks.yml의 node-dirs | python-dirs
    port: 8000                  # containerPort · service.port
    health: /health             # probe.path
    public: false               # true면 ingress.enabled (aws). onprem은 터널이 FE Service로 바로 간다
    database: true              # true면 envFromSecrets: [<앱>-db], migration 사용 가능
    migration: db/init.sql      # 배포마다 적용할 SQL (여러 번 실행해도 안전해야 한다). 없으면 생략
    resources: { cpu: 100m, memory: 128Mi, memoryLimit: 256Mi }
    replicas: { default: 2, aws: 1, onprem: 1 }
  - name: demo-app-fe
    path: fe
    runtime: node
    port: 3000
    health: /
    public: true
    database: false
    resources: { cpu: 100m, memory: 128Mi, memoryLimit: 256Mi }
    replicas: { default: 2, aws: 1, onprem: 1 }
```

규칙:

- `plan.yaml`은 스킬이 통째로 다시 써도 된다(사람 편집 전제 없음). `config.yaml`은 다른 키와 주석을 보존한다.
- 비밀값을 적지 않는다. 환경변수 값이 필요하면 값 파일의 `env`(고정값) 또는 `envFromSecrets`(Secret 이름)로만 표현한다.
- `compliance`와 `template_version`(`config.yaml`)은 종합 단계에서 쓰지 않는다.
- `services` 순서가 배포 순서다. DB를 쓰는 BE를 먼저, 그것을 프록시하는 FE를 뒤에 둔다.
- 서비스 이름은 `<앱>-<서비스>`. 앱 이름은 레포 이름(소문자 · 숫자 · 하이픈).
