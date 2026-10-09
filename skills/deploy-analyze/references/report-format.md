# 분석 보고서와 배포 설정 형식

## `.deploy/report.md`

리뷰 지점 1에서 사람이 읽는다. 결론을 맨 위에 둔다. 사용자의 언어로 쓴다.

```md
# 분석 보고서

## 추천
- 배포 대상: onprem
- 이유 한 줄: 민감 데이터(regulated)와 사내 보관 요구. 맥북 k3d 클러스터와 self-hosted runner가 있다
- 예상 월 비용: 0원 (클라우드 없음) / 참고: aws 약 ○○원
- 검토한 대안: aws (보관 위치 요구로 제외) / gcp (구현체 없음, T4)

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
target: onprem                  # aws | onprem | gcp(구현 예정). 워크플로 호출부의 기본 대상(레포 변수 DEPLOY_TARGET이 없을 때)
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
