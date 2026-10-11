# chaos-drill

장애 훈련 (T36, 설계 [`docs/chaos-drill.md`](../../../docs/chaos-drill.md)). test의 green에 일부러 장애를 넣고,
AI 승격 판단 · 규칙 거부권 · Blue-Green이 실제로 막는지 확인한 뒤 원래 상태로 돌려놓는다.
재사용 워크플로 [`chaos.yml`](../../workflows/chaos.yml)이 단계마다 이 폴더의 스크립트를 직접 부른다 (`failure-diagnosis/cluster.sh`와 같은 방식).

## 흐름

```
대상 레포 chaos.yml (workflow_dispatch: scenario · target · new_green · requested_by)
  └─ uses platform chaos.yml@vX.Y.Z   namespace = test 고정, rollout.yml과 같은 concurrency group
       0. check.sh    Rollout 상태로 진행 / 거절        → check.json, <release>/green.json (확인한 green 해시)
       1. prepare.sh  (new-green) 훈련용 green 띄우기     → green.json에 해시
       2. inject.sh   green 파드마다 POST /api/chaos       → <release>/inject.json
       3. promote-judge (mode: manual)                   → $RUNNER_TEMP/promote-judge/ (평소 배포와 같은 코드)
       4. blue.sh     active 서비스에 smoke                → blue.json
       5. cleanup.sh  (항상) 장애 해제 · Rollout 원상 복구 → cleanup.json
       6. grade.sh    기대와 비교                          → result.json, Job Summary, Slack 본문
     audit-log(action: drill) · slack-notify(action: drill) · artifact(chaos-drill-*)
```

| 상태 (0단계) | 처리 |
|---|---|
| `Paused`이고 preview ≠ active | 대기 중인 green으로 진행 (`existing`). 정리는 장애만 풀고 Rollout은 `Paused` 그대로 둔다 |
| `Healthy`이고 green 없음 | 거절. `new-green: true`면 파드 템플릿 annotation `one-tatchi/drill: <실행 ID>`로 revision만 바꿔 훈련용 green을 띄운다 (`new`). 정리에서 abort → annotation 원래 값 복구 → `Healthy` 확인 |
| `Progressing` · `Degraded` · 읽기 실패 · 서비스끼리 상태 다름 | 거절. 아무것도 바꾸지 않는다 |

- 확인한 green 해시를 주입 · 정리 직전에 다시 비교한다. 다르면 아무것도 하지 않고 실패로 남긴다.
- 주입은 `inject-services`(BE)에만 한다. FE는 `/api`를 active BE로 프록시할 수 있어 blue에 들어갈 위험이 있다. `GET /api/chaos`의 `enabled`가 true가 아니면(CHAOS_ENABLED 꺼짐, T35) 실패한다.
- 채점: 주입 성공 ∧ 묶음 결정 == 기대 ∧ blue 에러율 0% ∧ 정리 완료. 하나라도 아니면 job 실패.
- 대기 중 green의 장애 해제를 확인하지 못하면 `promotion-unsafe=true`. Slack에 "승격하지 마세요" 경고와 abort 버튼이 붙는다.

## 시나리오 (`scenarios.json`)

| 이름 | 주입 | 기대 판단 | 확인하는 가드레일 |
|---|---|---|---|
| `error-burst` | `errorRate: 1` | abort | 규칙 거부권 (에러율 기준 0%) |
| `slow-response` | `latencyMs: 3000` | abort | p95 기준 2000ms |
| `db-down` | `dbError: true` | abort | smoke 본문 조건 `dbConnected` (T28). `/health`는 readiness라 장애 주입을 받지 않고, 데이터 라우트가 `isDbConnected`를 내린 뒤 `/api/info`가 어긋난다 |
| `flaky` | `errorRate: 0.05` | abort | 에러율 기준 0% |

장애 값 상한은 `limits`(`latencyMs` ≤ 10000). 시나리오는 platform이 정하고 대상 레포는 이름만 고른다.
`pod-kill`(T29 이후) · `bad-after-promote`(Slack undo 시연) · Chaos Mesh는 설계 문서의 "나중에 붙일 것".

## 호출 (대상 레포)

```yaml
# .github/workflows/chaos.yml
on:
  workflow_dispatch:
    inputs:
      scenario: { type: choice, options: [error-burst, slow-response, db-down, flaky], required: true }
      target: { type: choice, options: [aws, gcp, onprem, onprem-secondary], default: aws }
      new_green: { type: boolean, default: false }
      requested_by: { type: string, required: false }
permissions: { contents: read, id-token: write }
jobs:
  drill:
    uses: <org>/one-tatchi-platform/.github/workflows/chaos.yml@vX.Y.Z
    with:
      scenario: ${{ inputs.scenario }}
      services: demo-app-be demo-app-fe
      inject-services: demo-app-be
      target: ${{ startsWith(inputs.target, 'onprem') && 'onprem' || inputs.target }}
      target-label: ${{ inputs.target }}
      cluster: ...        # rollout.yml 호출부와 같은 식
      new-green: ${{ inputs.new_green }}
      requested-by: ${{ inputs.requested_by }}
      template-ref: vX.Y.Z
    secrets: inherit      # ANTHROPIC_API_KEY · SLACK_BOT_TOKEN
```

## 스크립트 환경변수

공통: `WORK_ROOT`, `NAMESPACE`, `KUBECTL`(테스트용), `POLL_SECONDS`, `REQUEST_TIMEOUT_SECONDS` (`lib.sh`).

| 스크립트 | 추가 환경변수 | step 출력 |
|---|---|---|
| `check.sh` | `RELEASES`, `NEW_GREEN` | `proceed`, `mode`, `reason` |
| `prepare.sh` | `RELEASES`, `DRILL_ID`, `WAIT_SECONDS`(300) | |
| `inject.sh` | `RELEASES`(주입 대상), `SCENARIO`, `SCENARIOS_FILE` | |
| `blue.sh` | `RELEASES`, `INJECT_RELEASES`, `SMOKE_FILE`, `WINDOW_SECONDS`(10) | |
| `cleanup.sh` | `RELEASES`, `INJECT_RELEASES`, `MODE`, `WAIT_SECONDS`(180) | `released` |
| `grade.sh` | `SCENARIO`, `INJECT_RELEASES`, `JUDGMENT_DIR`, `LABEL`, `MODE` | `result`, `promotion-unsafe`, `details` |

## 테스트

```
bash .github/actions/chaos-drill/tests/run.sh
```

`tests/fake-kubectl`(Rollout 상태 파일을 patch · abort가 바꾼다)과 `tests/fake_chaos.py`(파드마다 상태 파일을 가진 가짜 BE)로
거절 조건 · 파드별 주입 · 해시 변경 감지 · 해제 확인 · annotation 복구 · 채점을 검사한다. `scripts/tests/run.sh`(CI)에서 함께 돈다.
