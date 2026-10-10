# promote-judge

Blue-Green 배포에서 green(새 버전)을 승격할지 버릴지 정한다 (T7, 설계 문서 6.5 · FR-7).
위치를 composite action으로 정한 이유는 [ADR 0002](../../../docs/adr/0002-promotion-judge-placement.md).

## 흐름

`deploy.yml`이 서비스들을 배포하고 green이 `Paused`가 된 서비스들(`releases`)을 같은 job에서 한 번에 넘긴다. 대상 레포는 호출부에서 모드와 키만 넘긴다.

```yaml
  test:
    uses: <org>/one-tatchi-platform/.github/workflows/deploy.yml@vX.Y.Z
    with:
      promote-mode: auto            # yolo. janto는 생략(manual)
      promote-window-seconds: "30"  # 선택
    secrets: inherit                # ANTHROPIC_API_KEY · SLACK_BOT_TOKEN
```

각 단계는 `group.sh`가 서비스마다 아래 스크립트를 돌린다. 서비스별 결과는 `$RUNNER_TEMP/promote-judge/<release>/`.

| 단계 | 스크립트 | 하는 일 | 결과 파일 (서비스별) |
|---|---|---|---|
| 1 | `smoke.sh` | `<release>-preview`에 port-forward로 붙어 관찰 창 동안 smoke 요청을 반복한다. **서비스들을 동시에** 관찰한다 | `smoke-results.jsonl` |
| 2 | `metrics.sh` | 에러율 · p95 계산, green 파드 재시작 수 · Ready 조회, 기준값과 비교 | `metrics.json` |
| 3 | `judge.sh` | 지표와 규칙 판정을 Claude에 보내 `{decision, reason}`을 받는다. 그다음 **묶음 결정**: 모두 promote면 promote, 하나라도 abort면 전체 abort | `judgment.json` (+ 묶음 `promote-judge/judgment.json`) |
| 4 | `act.sh` | auto면 `kubectl argo rollouts promote · abort`, manual이면 실행하지 않는다. Job Summary에 근거를 남긴다 | Job Summary |

- 규칙 판정이 fail이면 AI 답과 관계없이 abort다 ([ADR 0004](../../../docs/adr/0004-promotion-judge-rule-veto.md)).
- 서비스는 함께 승격 · 취소한다. 한 서비스라도 abort면 promote로 판단한 서비스도 abort하고 `source: group`으로 남긴다 ([ADR 0005](../../../docs/adr/0005-promotion-judge-group.md)).
- 1 · 2단계가 실패하거나, API 키가 없거나, Claude 호출이 실패 · 시간 초과 · 거절 · 형식 오류면 재시도 없이 abort다.

## 입력

| 입력 | 기본값 | 설명 |
|---|---|---|
| `releases` | (필수) | 서비스(Rollout) 이름들, 공백 구분. green은 Service `<release>-preview` |
| `namespace` | (필수) | `test` \| `prod` |
| `target` | (필수) | `aws` \| `gcp` \| `onprem`. 알림 · 감사 로그 표기용 |
| `environment` | (필수) | `test` \| `prod`. 알림 · 감사 로그 표기용 |
| `mode` | `manual` | `auto`: 판단대로 실행 (yolo). `manual`: 근거와 버튼만 (janto) |
| `smoke-file` | `.deploy/smoke.json` | smoke 요청 목록. 형식은 아래 "smoke 파일" |
| `window-seconds` | `30` | 관찰 창(초) |
| `request-timeout-seconds` | `5` | 요청 하나의 제한 시간(초). 넘으면 실패 |
| `max-error-rate` | `0` | 허용 에러율(%) |
| `max-p95-ms` | `2000` | 허용 p95 응답 시간(ms). 비우면 검사 안 함 |
| `max-restarts` | `0` | 허용 green 파드 재시작 수 (생성 이후 합계) |
| `model` | `claude-sonnet-5-5` | 판단 모델 |
| `api-timeout-seconds` | `60` | Claude API 호출 제한 시간(초). 넘으면 재시도 없이 abort |
| `promote-wait-seconds` | `60` | auto에서 promote 뒤 Healthy를 기다리는 시간(초). 넘으면 실패 |
| `anthropic-api-key` | `""` | 비어 있으면 AI 판단 없이 abort |

## 출력

| 출력 | 설명 |
|---|---|
| `decision` | 묶음 결정 `promote` \| `abort` |
| `reason` | 판단 근거. abort면 abort한 서비스들의 근거, promote면 서비스별 근거 (`<release>: …`를 ` / `로 이음) |
| `report` | 묶음 결정 JSON 경로. 서비스별 지표 · 판단은 같은 폴더의 `<release>/` |
| `executed` | auto에서 실제로 성공한 조작(`promote` \| `abort`). manual이거나 명령이 실패하면 빈 값 |

## smoke 파일

대상 레포의 `.deploy/smoke.json`. 서비스(release) 이름별로 요청 목록을 둔다.

```json
{
  "demo-app-be": [
    {"method": "GET", "path": "/health", "expect": 200, "expect_body": {"database": "connected"}},
    {"method": "GET", "path": "/api/info", "expect": 200, "expect_body": {"dbConnected": true}},
    {"method": "POST", "path": "/api/guestbook", "expect": 200, "body": {"name": "smoke", "message": "hi"}}
  ],
  "demo-app-fe": [
    {"method": "GET", "path": "/", "expect": 200}
  ]
}
```

- `method` 기본 `GET`, `expect` 기본 `200`, `body`는 있으면 JSON으로 보낸다.
- `expect_body`(JSON 객체, 선택): 응답 본문을 JSON으로 읽어 이 키 · 값이 **모두** 같아야 통과한다. 상태 코드가 맞아도 본문이 어긋나면 실패이고, 본문이 JSON이 아니어도 실패다. 중첩 객체는 그 키 전체를 비교한다. 객체가 아니면 smoke 단계가 실패하고 판단은 abort다. DB가 끊겨도 `/health`가 200인 앱의 메모리 폴백을 잡으려고 둔다 (T28, [ADR 0016](../../../docs/adr/0016-cloud-db-tls-and-memory-fallback.md)).
- 관찰 창 동안 첫 바퀴는 목록 전체, 이후에는 `GET`만 반복한다. 쓰기 요청은 한 번만 보낸다.
- 파일이 없거나 그 서비스 항목이 없으면 `GET /health → 200`만 확인한다. 파일이 올바른 JSON이 아니면 smoke 단계가 실패하고 판단은 abort다.
- FE green의 `/api`는 blue BE로 프록시되므로 FE 목록에는 FE 자체 경로만 넣는다.
- green 접속은 `kubectl port-forward svc/<release>-preview` ([ADR 0003](../../../docs/adr/0003-green-access-port-forward.md)).

결과 `smoke-results.jsonl`은 요청마다 한 줄이다. 연결 실패 · 시간 초과는 `status: 0`. `expect_body`가 어긋나면 `body_mismatch`에 어떤 키가 어떻게 달랐는지 남는다.

```json
{"pass":1,"method":"GET","path":"/health","expect":200,"status":200,"ms":12,"ok":true,"body_mismatch":null}
{"pass":1,"method":"GET","path":"/health","expect":200,"status":200,"ms":14,"ok":false,"body_mismatch":"database=\"fallback-memory\" (기대 \"connected\")"}
```

## 지표와 규칙 판정

`metrics.sh`가 `metrics.json`을 만든다. 에러율 · p95는 설계 문서 6.5대로 smoke 트래픽 기준이다(green은 승격 전이라 사용자 트래픽이 없다).

| 지표 | 얻는 방법 |
|---|---|
| 요청 수 · 실패 수 · 에러율(%) · 실패 묶음 | `smoke-results.jsonl`. 실패는 상태 코드 불일치 · 연결 실패 · `expect_body` 불일치(`body_mismatch`) 모두 |
| p95 | 응답 시간 오름차순에서 ceil(0.95 × n)번째 값 (nearest-rank) |
| green 파드 수 · Ready · 재시작 | kubectl. Rollout의 `status.blueGreen.previewSelector` 해시 라벨(`rollouts-pod-template-hash`)을 가진 파드 |

아래 중 하나라도 해당하면 `rule.verdict`는 `fail`이고 `rule.reasons`에 이유가 남는다.

- smoke 결과가 없다
- 에러율 > `max-error-rate`, p95 > `max-p95-ms`(비우면 생략), 재시작 > `max-restarts`
- Ready가 아닌 green 파드가 있다, green 파드가 없다, 파드 정보를 읽지 못했다
- 기준값 입력이 숫자가 아니다

```json
{"requests": 2, "failed": 1, "error_rate": 50, "p95_ms": 30, "max_ms": 30, "passes": 1,
 "failures": [{"method": "GET", "path": "/api/info", "expect": 200, "status": 500, "body_mismatch": null, "count": 1}],
 "release": "demo-app-be", "green_hash": "green123", "pods": {"count": 2, "ready": 2, "restarts": 0},
 "thresholds": {"max_error_rate": 0, "max_p95_ms": 2000, "max_restarts": 0},
 "rule": {"verdict": "fail", "reasons": ["에러율 50% > 기준 0%"]}}
```

## AI 판단

`judge.sh`가 `metrics.json`을 Claude Messages API(curl)에 보내고 `judgment.json`을 만든다.

- 구조화 출력(`output_config.format`, JSON schema)으로 `{"decision": "promote" | "abort", "reason": "..."}`만 받는다. thinking 블록은 건너뛰고 text 블록을 읽는다.
- 규칙이 fail이어도 호출한다. 결정은 abort로 고정하고, AI가 쓴 원인 설명을 근거로 남긴다.
- `fallbacks: "default"`(헤더 `anthropic-beta: server-side-fallback-2026-07-01`): 안전 분류기가 거절하면 서버가 다른 모델로 다시 시도한다. 그래도 거절이면 abort다.
- 결정 출처 `source`: `ai`(규칙 pass, AI 결정) · `rule`(규칙 fail, 거부권) · `fallback`(AI 판단 없음 → abort) · `group`(이 서비스는 promote였지만 다른 서비스가 abort라 함께 abort, `ai_decision_alone`에 원래 판단)

```json
{"decision": "promote", "source": "ai", "reason": "에러율 0%, p95 38ms로 기준 안이고 green 파드 2개 모두 Ready라 승격한다.",
 "model": "claude-sonnet-5-5", "ai_seconds": 4,
 "ai": {"decision": "promote", "reason": "…", "error": null},
 "rule": {"verdict": "pass", "reasons": []}, "metrics": {"requests": 120, "error_rate": 0, "p95_ms": 38, "...": "..."}}
```

## 실행과 기록

| 모드 | promote | abort | step 결과 |
|---|---|---|---|
| `auto` (yolo) | `kubectl argo rollouts promote` → `status`로 Healthy 확인 | `kubectl argo rollouts abort` | promote는 Healthy면 성공. **abort는 실패** — 다음 단계(main 자동 머지 · prod)로 넘어가지 않게 한다 |
| `manual` (janto) | 실행하지 않음 | 실행하지 않음 | 항상 성공. 사람이 Slack 버튼(`rollout.yml`)으로 결정한다 |

- Job Summary에 결정 · 근거 · 지표 · 실패한 요청 표를 남긴다.
- Slack 알림과 감사 로그는 이 액션이 보내지 않는다. 호출하는 쪽(`deploy.yml`)이 출력 `decision` · `reason` · `executed`를 기존 알림 · 감사 로그 단계에 넘긴다(메시지 중복 방지, 액션 단독 테스트).

## 테스트

```bash
bash .github/actions/promote-judge/tests/run.sh
```

CI `scripts` 잡(`scripts/tests/run.sh`)에서도 돈다. 이 잡은 main의 필수 검사가 아니므로 PR 전에 로컬에서 확인한다.

가짜 green(`tests/fake_server.py`), 가짜 kubectl(`tests/fake-kubectl`), 가짜 Claude API(`tests/fake_claude.py`)로 클러스터 · API 키 없이 돈다.

## 기준값 근거

| 입력 | 값 | 근거 | 상태 |
|---|---|---|---|
| `max-error-rate` | 0% | 설계 문서 12장 제안값. 500이 한 번이라도 나오면 abort | 확정 |
| `max-restarts` | 0 | 뜬 뒤 한 번이라도 재시작한 green을 막는다 | 확정 |
| `max-p95-ms` | 2000 | 멈춤 · 극단적 지연만 거르는 느슨한 값. port-forward 경유 지연을 감안했다 | 잠정. 정상 버전 실측 후 조정 |
| `request-timeout-seconds` | 5 | 멈춘 버전이 에러율로도 걸리게 한다 | 확정 |
| `window-seconds` | 30 | 설계 원안 60초는 서비스 2개를 차례로 배포하면 test에서만 +2분이다. 배포 시간 목표(T9)와 함께 정한다 | 잠정 |
