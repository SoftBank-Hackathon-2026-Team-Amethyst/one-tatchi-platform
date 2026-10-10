# 장애 훈련 (Chaos Drill) 설계

상태: 초안 (2026-10-10)

## 한 줄 요약

**Slack에서 버튼 한 번으로 test 환경에 일부러 장애를 내고, 원터치 배포의 가드레일(AI 승격 판단 · Blue-Green · 되돌리기)이 실제로 막아 내는지 확인한다. 결과는 Slack · Grafana · 감사 로그에 남는다.**

지금까지는 "가드레일이 있다"고 말할 수 있었다. 장애 훈련을 넣으면 "가드레일이 동작한다"를 매번 보여 줄 수 있다.

## 왜 필요한가 (어필 포인트)

지금까지 만든 것들은 모두 "문제가 생기면 막는다"는 장치다. 하지만 평소 배포는 대부분 성공하기 때문에 막는 장면을 볼 일이 거의 없다.

| 이미 만든 것 | 장애 훈련이 증명하는 것 |
|---|---|
| T5 test / prod 분리, 운영 앞 사람 승인 | test에서 낸 장애가 prod로 번지지 않는다 |
| T7 AI 승격 판단 (규칙 거부권 포함) | 깨진 green을 AI · 규칙이 **abort**한다 |
| T8 · T13 yolo 자동 승격 · 자동 머지 | 사람이 없는 경로에서도 깨진 버전은 main까지 가지 않는다 |
| T26 Slack 버튼 (승격 · 취소 · 되돌리기) | 승격 뒤에 문제가 생겨도 Slack **undo** 한 번으로 돌아간다 |
| T28 DB 상태 검증 | DB가 끊기면 `/health`가 503을 내고 판단에 잡힌다 |
| T17 중앙 Grafana | 훈련 결과가 대시보드에 근거로 남는다 |

## 목표와 비목표

**목표**
- Slack 명령 하나로 장애 시나리오를 실행하고, 기대 결과와 비교해 통과 · 실패를 알린다.
- 시나리오는 platform 템플릿이 정하고, 앱은 이름만 고른다 ("AI는 변수만 채우고 규칙은 템플릿이 지킨다").
- AWS · GCP · 온프레미스에서 같은 방식으로 동작한다 (클라우드 전용 장애 도구를 쓰지 않는다).

**비목표**
- prod에 장애를 내지 않는다. 장애 대상 네임스페이스는 `test`로 **고정**하고 입력으로 받지 않는다.
- 노드 · 클라우드 계층 장애(AZ 장애, RDS 페일오버 등)는 1단계에서 하지 않는다.

## 선행 정리

### P1. test와 prod의 DB 분리

지금 AWS · GCP는 test와 prod가 같은 DB 인스턴스 · 같은 DB · 같은 시크릿을 쓴다. AWS는 그 시크릿이 RDS 마스터 계정이다. 이대로 test에 장애를 내면 prod 데이터가 함께 영향을 받는다.

- 1단계: 같은 인스턴스 안에서 **DB와 계정을 환경별로 분리**한다. test 계정은 prod DB에 권한이 없고, 마스터 계정 대신 앱 전용 계정을 쓴다. 온프레미스는 이미 환경별로 DB가 따로라 바꿀 것이 없다.
- 2단계(선택): test 전용 인스턴스. DB 인스턴스 자체를 멈추는 시나리오를 넣으려면 이것이 필요하다.

1단계 시나리오의 DB 장애는 **앱 쪽에서 흉내 내는 장애**(`dbError`)라서 DB · 계정 분리만으로 충분하다.

### P2. `/api/chaos`는 prod에서 닫기

`be/src/routes/chaos.ts`는 이미 `CHAOS_ENABLED=true`일 때만 `POST /api/chaos`를 등록한다. 그런데 `deploy/values-be.yaml` 한 파일을 test와 prod가 같이 쓰기 때문에, 지금은 prod에서도 열려 있다.

- platform `deploy.yml`에 **환경별 덧붙임 파일**을 추가한다. `deploy/values-be.yaml`을 쓰는 서비스라면 `deploy/values-be.<environment>.yaml`이 있을 때 그 파일을 뒤에 덧붙인다. 지금의 `deploy/<target>/values.yaml` 덧붙임과 같은 방식이다.
- demo-app은 `deploy/values-be.yaml`에서 `CHAOS_ENABLED`를 빼고, `deploy/values-be.test.yaml`에만 `CHAOS_ENABLED: "true"`를 둔다.
- 결과: prod에는 `POST /api/chaos` 라우트 자체가 없다(404). `GET /api/chaos`는 상태 조회라 그대로 둔다.

test도 인터넷에 공개돼 있어 누구나 test에 장애를 낼 수 있다. 데모 기간에는 이를 허용하고(FE 화면의 장애 버튼 시연), 데모 이후에는 토큰 헤더를 붙이거나 ingress에서 `/api/chaos`를 막는다.

## 전체 흐름에서의 위치

장애 훈련은 **배포 파이프라인과 별도로** 돈다. 평소 배포에는 영향이 없다.

```
[평소 배포]
checks → publish → deploy test (Blue-Green) → promote-judge → prod 관문(사람) → prod

[장애 훈련]  Slack /chaos <시나리오>
               │
               ▼
      demo-app chaos.yml (workflow_dispatch) ─ uses → platform chaos.yml@vX.Y.Z
               │  namespace = test 고정, test 배포 · rollout과 같은 concurrency group
               ▼
      0. green 확인       Rollout 상태를 읽고 진행 / 거절을 정한다 → 거절이면 Slack에 이유를 알리고 끝
      1. green 준비       대기 중인 green을 쓰거나, 요청했으면 훈련용 green을 띄운다
      2. 장애 주입        green 파드에만 (blue는 건드리지 않음)
      3. 판단 돌리기      기존 promote-judge (smoke → metrics → judge), 실행은 하지 않음(manual)
      4. blue 확인        active 서비스에 smoke → blue가 멀쩡한지
      5. 정리             장애 해제 → (훈련용 green이면) abort · revision 되돌리기 (항상 실행)
      6. 채점             기대 결과와 비교 → 통과 / 실패
               │
               ▼
      Slack 결과 메시지 · Grafana 근거 · S3 감사 로그
```

### 나중에 붙일 것: 배포 중 버티기 검사

T29(이중화)로 `replicas`가 2 이상이 되면, 평소 test 배포의 관찰 창 동안 green 파드 하나를 죽이고도 promote가 나오는지 보는 옵션(`.deploy/config.yaml`의 `chaos: pod-kill`)을 promote-judge에 추가한다. 지금은 `replicas: 1`이라 파드 하나만 죽어도 서비스가 멈추므로, 이 검사는 매번 abort가 난다.

## 단계별 동작

### 0. green 확인

장애는 green에만 넣으므로, 시작 전에 green이 있는지부터 본다. Slack 봇은 클러스터 권한이 없고 GitHub API만 쓰므로(`slack-bot/app/github.py`), 확인은 **워크플로 첫 단계**에서 하고 결과를 Slack에 돌려준다.

서비스(Rollout)마다 아래를 읽는다.

```bash
kubectl get rollout <release> -n test -o json | jq '{
  phase:   .status.phase,                           # Healthy | Paused | Progressing | Degraded
  paused:  (.status.pauseConditions // [] | length > 0),
  active:  .status.blueGreen.activeSelector,
  preview: .status.blueGreen.previewSelector }'
```

| 상태 | 뜻 | 처리 |
|---|---|---|
| `Paused`이고 `preview ≠ active` | green이 떠서 승격 결정을 기다리는 중 (janto의 manual 대기) | **그 green으로 진행** |
| `Healthy`이고 `preview = active` (또는 비어 있음) | green 없음 | 기본은 **거절**: "대기 중인 green이 없어요". `new-green`을 붙여 요청했으면 훈련용 green을 띄워 진행 |
| `Progressing` | 배포 · 승격이 진행 중 (yolo auto의 관찰 창 포함) | **거절**: "배포 진행 중이에요. 끝난 뒤 다시 시도해 주세요" |
| `Degraded` · 읽기 실패 | 이미 이상한 상태 | **거절**: 상태와 메시지를 그대로 알린다 |

- 서비스가 여럿이면(BE · FE) 모두 같은 상태여야 진행한다. 묶음 승격(ADR 0005)과 같은 이유다.
- 확인과 주입 사이에 누가 승격 · 취소 버튼을 누르면 안 되므로, `rollout.yml`과 **같은 concurrency group**에서 돈다. 훈련이 끝날 때까지 버튼 동작은 대기한다.
- 확인한 `preview` 해시를 기억해 두고, 주입 · 정리 직전에 한 번 더 같은지 본다. 다르면 아무것도 하지 않고 실패로 알린다.

### 1. green 준비

**대기 중인 green이 있을 때**: 그 green에 그대로 주입한다. 실제 승격 후보 버전으로 "이 버전에 장애가 나면 판단이 막는가"를 확인하는 셈이다. 정리 단계에서 장애만 해제하고 **abort하지 않는다**. 승격 여부는 원래대로 사람이 Slack 버튼으로 정한다.

**`new-green`으로 요청했을 때**: 현재 Rollout의 파드 템플릿에 annotation(`one-tatchi/drill: <실행 ID>`)을 붙인다. 이미지는 그대로지만 revision이 바뀌어, Blue-Green이 green을 띄우고 `Paused`에서 멈춘다(차트 기본값 `autoPromotionEnabled: false`). 이 green은 정리 단계에서 지운다.

### 2. 장애 주입

| 종류 | 방법 | 대상 |
|---|---|---|
| 앱 장애 (에러 · 지연 · DB) | green **파드마다** `kubectl port-forward pod/<파드>`로 붙어 `POST /api/chaos` | green 파드만 |
| 파드 장애 | `kubectl delete pod <green 파드 하나>` | green 파드만 |

- `chaosState`는 파드 메모리에 있다. 서비스 주소로 한 번만 보내면 파드 하나에만 들어가므로, **파드마다** 직접 보낸다.
- green 파드는 `rollouts-pod-template-hash=<previewSelector>` 라벨로 고른다(`metrics.sh`와 같은 방식). blue에는 보내지 않는다.

### 3. 판단 돌리기

기존 `promote-judge`를 `mode: manual`로 그대로 부른다. 관찰 창 · 규칙 · AI 판단은 평소 배포와 **완전히 같은 코드**다. 그래서 훈련 결과는 곧 실제 배포에서 판단이 어떻게 나올지를 보여 준다.

### 4. blue 확인

지금의 smoke는 green(`<release>-preview`)만 본다. 훈련에서는 active 서비스(`<release>`)에도 같은 smoke 요청을 보내 **blue 에러율 0%**를 확인한다. "장애가 사용자 쪽으로 새지 않았다"를 보여 주는 증거다.

### 5. 정리 (항상 실행)

`if: always()`로, 앞 단계가 실패해도 반드시 아래를 실행한다.
1. green 파드마다 `POST /api/chaos/reset`, `GET /api/chaos`로 해제됐는지 확인
2. **대기 중이던 green**이면 여기서 끝. Rollout은 `Paused` 그대로 사람의 결정을 기다린다
3. **훈련용 green**이면 `kubectl argo rollouts abort` → green 제거, annotation을 원래 값으로 되돌려 spec을 stable과 같게 만든다 → Rollout `Healthy`
4. 기대한 상태(`Paused` 또는 `Healthy`)가 아니면 훈련 결과를 **실패**로 하고 Slack에 경고한다

장애 해제를 확인하지 못한 green을 사람이 모르고 승격하면 안 된다. 그래서 1이 실패하면 Slack 메시지에 "장애가 남아 있을 수 있어요, 승격하지 마세요"를 굵게 넣고 abort 버튼을 함께 보낸다.

### 6. 채점

시나리오마다 **기대 결과**가 있고, 실제 결과가 같으면 통과다. "abort가 나와야 통과"인 시나리오가 대부분이라는 점이 일반 배포와 다르다.

## 시나리오 목록 (platform 템플릿이 정함)

| 이름 | 주입 | 기대 판단 | 기대 blue | 확인하는 가드레일 |
|---|---|---|---|---|
| `error-burst` | `errorRate: 1` | abort (source: rule) | 에러 0% | 규칙 거부권 |
| `slow-response` | `latencyMs: 3000` | abort (p95 > 2000ms) | 에러 0% | p95 기준 |
| `db-down` | `dbError: true` | abort | 에러 0% | T28 DB 상태 검증 |
| `flaky` | `errorRate: 0.05` | abort | 에러 0% | 에러율 기준 0% (조금 깨진 것도 막는다) |
| `pod-kill` | green 파드 하나 삭제 | promote (T29 이후) | 에러 0% | 이중화 · 자가 복구 |
| `bad-after-promote` | 승격 직후 에러 주입 | (판단 없음) | Slack undo로 복구 | T26 되돌리기 |

- 1차 구현은 위 네 줄(`error-burst`, `slow-response`, `db-down`, `flaky`)이다. 앱의 `/api/chaos`와 `kubectl`만 쓰므로 새로 설치할 것이 없다.
- `bad-after-promote`는 사람이 Slack에서 undo를 누르는 시연용이다. 자동 채점은 하지 않는다.
- 2단계로 Chaos Mesh(쿠버네티스 CRD, EKS · GKE · k3d 공통)를 붙이면 네트워크 지연 · 패킷 손실 · CPU 압박 시나리오를 앱 코드 없이 추가할 수 있다.

## Slack 연동

기존 `/rollout`과 같은 구조로 만든다 (`slack-bot/app/rollout.py`).

```
/chaos error-burst aws              ← 대기 중인 green에 주입. 환경은 test 고정
/chaos error-burst aws new-green    ← green이 없으면 훈련용 green을 띄워서 주입
/chaos list                         ← 시나리오 목록
```

- 봇은 입력 형식과 `ALLOWED_USER_IDS`만 확인하고 demo-app `chaos.yml`에 `workflow_dispatch`(scenario, target, new_green, requested_by)를 보낸다. green이 있는지는 봇이 알 수 없으므로 워크플로의 0단계가 판단한다.
- 버튼으로도 시작할 수 있다. janto(manual) 배포의 "승격 대기" 알림에 지금의 `[승격] [취소]` 옆에 `[🧪 장애 훈련]`을 붙인다. 이 알림은 green이 `Paused`일 때만 오므로 사용자가 대상을 고를 필요가 없다. 그래도 알림 뒤에 상태가 바뀌었을 수 있어서 0단계 확인은 그대로 거친다.
- 시작 메시지: "🐰 장애 훈련 시작 — error-burst @ aws.test (실행 링크)"
- 거절 메시지: "🐰 장애 훈련을 시작하지 않았어요 — 대기 중인 green이 없어요. `new-green`을 붙이면 훈련용 green을 띄워요" / "배포 진행 중이에요"
- 결과 메시지:

```
🐰 장애 훈련 통과 — error-burst @ aws.test
  기대: abort  →  실제: abort (규칙: 에러율 100% > 기준 0%)
  AI 근거: "모든 요청이 500이라 승격하지 않는다."
  blue(사용자 쪽): 에러율 0%, p95 41ms
  정리: 장애 해제 · green 제거 · Rollout Healthy
  [Grafana에서 보기] [실행 로그]
```

- 기대와 다르면 "🚨 장애 훈련 실패"로 보내고, 어느 가드레일이 뚫렸는지 적는다(예: "에러율 100%인데 promote가 나왔다").

## Grafana 연동

이미 있는 경로를 그대로 쓴다. 새 데이터 소스는 만들지 않는다.

| 무엇 | 어떻게 |
|---|---|
| 훈련 기록 | 기존 `publish-metrics`(CloudWatch Logs, ADR 0011)에 `kind: drill` 레코드를 추가한다. 시나리오 · 기대 · 실제 · 통과 여부 · green/blue 수치 · 관찰 시작/종료 · 실행 링크 |
| 대시보드 | `deploy-overview`에 "장애 훈련" 패널: 훈련 목록 표, 시나리오별 통과율, 마지막 훈련 시각 |
| 실시간 지표 | 훈련 중 green의 파드 상태 · 재시작은 기존 `kube_pod_*`로 보인다. smoke 트래픽은 실제 트래픽 집계에서 빠지므로(ADR 0011), 훈련의 수치는 훈련 기록 레코드에서 읽는다 |

평소 배포의 AI 판단 근거와 같은 대시보드에 나란히 보이므로, "평소에는 promote, 장애 훈련에서는 abort"를 한 화면에서 비교할 수 있다.

## 안전장치

- **namespace `test` 고정.** 워크플로 입력으로 받지 않는다(보안 리뷰 Vuln 2와 같은 구멍을 만들지 않기 위해).
- **green에만 주입.** blue와 prod에는 요청 경로가 없다.
- **정리는 항상 실행.** `if: always()`, 정리 실패는 훈련 실패로 알린다.
- **green이 있을 때만.** 0단계에서 green이 대기 중인지 확인하고, 아니면 아무것도 하지 않는다. 훈련용 green은 `new-green`으로 명시했을 때만 띄운다.
- **한 번에 하나.** test 배포 · `rollout.yml`과 같은 concurrency group을 써서 실제 배포나 승격 버튼과 겹치지 않는다.
- **시간 제한.** job `timeout-minutes: 15`. 장애 값에도 상한을 둔다(`latencyMs` ≤ 10000).
- **누가 했는지 기록.** `requested_by`(Slack 사용자)를 감사 로그(S3 Object Lock)에 남긴다.
- **권한.** 훈련 job은 test 배포와 같은 identity를 쓴다. 보안 리뷰 Vuln 1 조치(test 전용 저권한 identity)가 들어가면 그 identity를 그대로 쓴다.

## 데모 시나리오 (발표용, 약 3분)

1. Slack에서 `/chaos error-burst aws new-green` 입력. (janto 배포가 승격 대기 중이면 알림의 `[🧪 장애 훈련]` 버튼)
2. 화면에 FE 공개 주소를 띄워 둔다. 훈련 내내 정상 동작한다(blue).
3. 약 1분 뒤 Slack에 "🐰 장애 훈련 통과 — 기대 abort, 실제 abort" 메시지가 오고, AI 근거가 함께 보인다.
4. [Grafana에서 보기]를 눌러, 평소 배포 기록(promote) 옆에 훈련 기록(abort)이 나란히 있는 것을 보여 준다.
5. 마무리 멘트: "원터치는 빠르기만 한 게 아니라, 깨진 걸 실제로 막는다는 걸 매번 확인할 수 있습니다."

## 작업 나누기

`docs/tasks.md`에 등록했다.

| 작업 | 내용 | 선행 |
|---|---|---|
| `T34` | test · prod DB와 계정 분리 (P1) | T28 |
| `T35` | 환경별 값 파일, prod에서 `/api/chaos` 닫기 (P0) | T5, T13 |
| `T36` | `chaos.yml`: green 확인 · 주입 · 판단 · 정리 · 채점 | T7, T30, T34, T35 |
| `T37` | Slack `/chaos` · 승격 대기 알림 버튼, Grafana 훈련 기록 | T36, T26, T17 |

나중에 붙일 것(작업 미등록): 배포 중 버티기 검사(`pod-kill`, T29 이후), Chaos Mesh 모듈.

## 열린 질문

- 훈련을 정기적으로(예: 매일 1회) 자동 실행할지, Slack에서 요청할 때만 할지.
- 훈련 실패(가드레일이 뚫림)를 배포 차단으로 연결할지. 예를 들어 마지막 훈련이 실패했으면 yolo 자동 승격을 끄는 방식.
- 시나리오 목록을 대상 레포가 늘릴 수 있게 할지, platform에서만 관리할지.
