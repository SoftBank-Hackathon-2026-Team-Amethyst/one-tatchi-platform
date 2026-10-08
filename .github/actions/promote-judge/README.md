# promote-judge

Blue-Green 배포에서 green(새 버전)을 승격할지 버릴지 정한다 (T7, 설계 문서 6.5 · FR-7).
위치를 composite action으로 정한 이유는 [ADR 0002](../../../docs/adr/0002-promotion-judge-placement.md).

## 흐름

`deploy.yml`이 green을 띄우고 Rollout이 `Paused`가 된 뒤 같은 job에서 부른다.

| 단계 | 스크립트 | 하는 일 | 결과 파일 (`$WORK_DIR`) |
|---|---|---|---|
| 1 | `smoke.sh` | `<release>-preview`에 port-forward로 붙어 관찰 창 동안 smoke 요청을 반복한다 | `smoke-results.jsonl` |
| 2 | `metrics.sh` | 에러율 · p95 계산, green 파드 재시작 수 · Ready 조회, 기준값과 비교 | `metrics.json` |
| 3 | `judge.sh` | 지표와 규칙 판정을 Claude에 보내 `{decision, reason}`을 받는다 | `judgment.json` |
| 4 | `act.sh` | auto면 `kubectl argo rollouts promote · abort`, manual이면 실행하지 않는다. Job Summary에 근거를 남긴다 | |

- 규칙 판정이 fail이면 AI 답과 관계없이 abort다.
- 1 · 2단계가 실패하거나, API 키가 없거나, Claude 호출이 실패 · 거절 · 형식 오류면 abort다.

## 입력

| 입력 | 기본값 | 설명 |
|---|---|---|
| `release` | (필수) | 서비스(Rollout) 이름. green은 Service `<release>-preview` |
| `namespace` | (필수) | `test` \| `prod` |
| `target` | (필수) | `aws` \| `gcp` \| `onprem`. 알림 · 감사 로그 표기용 |
| `environment` | (필수) | `test` \| `prod`. 알림 · 감사 로그 표기용 |
| `mode` | `manual` | `auto`: 판단대로 실행 (yolo). `manual`: 근거와 버튼만 (janto) |
| `smoke-file` | `.deploy/smoke.json` | smoke 요청 목록. 형식은 아래 "smoke 파일" |
| `window-seconds` | `30` | 관찰 창(초) |
| `request-timeout-seconds` | `5` | 요청 하나의 제한 시간(초). 넘으면 실패 |
| `max-error-rate` | `0` | 허용 에러율(%) |
| `max-p95-ms` | `2000` | 허용 p95 응답 시간(ms) |
| `max-restarts` | `0` | 관찰 중 허용 재시작 수 |
| `model` | `claude-opus-5-5` | 판단 모델 |
| `anthropic-api-key` | `""` | 비어 있으면 AI 판단 없이 abort |
| `slack-token` · `slack-channel` | `""` | 비어 있으면 알림 생략 |
| `audit-bucket` | `""` | 비어 있으면 감사 로그 생략 |

## 출력

| 출력 | 설명 |
|---|---|
| `decision` | `promote` \| `abort` |
| `reason` | 판단 근거 한두 문장 |
| `report` | 지표 · 규칙 판정 · AI 판단 JSON 파일 경로 |

## smoke 파일

대상 레포의 `.deploy/smoke.json`. 서비스(release) 이름별로 요청 목록을 둔다.

```json
{
  "demo-app-be": [
    {"method": "GET", "path": "/health", "expect": 200},
    {"method": "GET", "path": "/api/info", "expect": 200},
    {"method": "POST", "path": "/api/guestbook", "expect": 200, "body": {"name": "smoke", "message": "hi"}}
  ],
  "demo-app-fe": [
    {"method": "GET", "path": "/", "expect": 200}
  ]
}
```

- `method` 기본 `GET`, `expect` 기본 `200`, `body`는 있으면 JSON으로 보낸다.
- 관찰 창 동안 첫 바퀴는 목록 전체, 이후에는 `GET`만 반복한다. 쓰기 요청은 한 번만 보낸다.
- 파일이 없거나 그 서비스 항목이 없으면 `GET /health → 200`만 확인한다. 파일이 올바른 JSON이 아니면 smoke 단계가 실패하고 판단은 abort다.
- FE green의 `/api`는 blue BE로 프록시되므로 FE 목록에는 FE 자체 경로만 넣는다.
- green 접속은 `kubectl port-forward svc/<release>-preview` ([ADR 0003](../../../docs/adr/0003-green-access-port-forward.md)).

결과 `smoke-results.jsonl`은 요청마다 한 줄이다. 연결 실패 · 시간 초과는 `status: 0`.

```json
{"pass":1,"method":"GET","path":"/health","expect":200,"status":200,"ms":12,"ok":true}
```

## 테스트

```bash
bash .github/actions/promote-judge/tests/run.sh
```

가짜 green(`tests/fake_server.py`)과 가짜 kubectl(`tests/fake-kubectl`)로 클러스터 없이 돈다.

## 기준값 근거

| 입력 | 값 | 근거 | 상태 |
|---|---|---|---|
| `max-error-rate` | 0% | 설계 문서 12장 제안값. 500이 한 번이라도 나오면 abort | 확정 |
| `max-restarts` | 0 | 관찰 중 재시작한 버전을 막는다 | 확정 |
| `max-p95-ms` | 2000 | 멈춤 · 극단적 지연만 거르는 느슨한 값. port-forward 경유 지연을 감안했다 | 잠정. 정상 버전 실측 후 조정 |
| `request-timeout-seconds` | 5 | 멈춘 버전이 에러율로도 걸리게 한다 | 확정 |
| `window-seconds` | 30 | 설계 원안 60초는 서비스 2개를 차례로 배포하면 test에서만 +2분이다. 배포 시간 목표(T9)와 함께 정한다 | 잠정 |
