# [ADR-0019] 배포 실패 증거 수집: 클러스터 상태는 실패한 job 안에서, Actions 로그는 진단 job에서

* **상태 (Status):** 채택됨(Accepted). 수집 스크립트(`cluster.sh` · `collect.py` · `redact.sed`)는 T12에서 구현하고 가짜 kubectl · gh로 검증했다. `deploy.yml` 연결과 demo-app 실제 실패 검증은 같은 작업에서 이어 한다.
* **날짜 (Date):** 2026-10-11
* **관련:** T12 (#21), T7 (#16, 승격 판단의 Claude 호출 방식), T10(yolo 리포트, 공통 액션 구조), [`.github/actions/failure-diagnosis/`](../../.github/actions/failure-diagnosis/README.md)

## 1. 배경 및 문제 상황 (Context and Problem Statement)

* **상황:** 배포 단계(`publish` · `deploy` job)가 실패하면 Slack에 "작업 실패. 실행 로그를 확인해 주세요"만 간다. T12는 실패 증거를 모아 Claude로 원인을 요약해 실행 요약 · Slack · PR 코멘트에 남긴다. 요약의 품질은 어떤 증거를 넣느냐에 달려 있다.
* **문제:**
  * 실패 원인이 Actions 로그에 없는 경우가 있다. demo-app run [38070479286](https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/demo-app/actions/runs/38070479286)의 로그에는 `pre-upgrade hooks failed: resource Job/test/demo-app-be-migration … failed: 3/1`만 남는다. 실제 원인(SQL 오류 등)은 클러스터의 마이그레이션 Job 파드 로그에 있다. 그래서 실패 시점의 클러스터 상태도 모아야 한다.
  * GitHub Actions의 job 로그는 job이 끝나야 API로 받을 수 있다. 실패한 step 바로 뒤의 step에서는 그 step의 출력을 API로 읽지 못한다.
  * 클러스터에 접속할 수 있는 곳은 배포 job뿐이다. onprem은 맥북 self-hosted 러너에서만 접근할 수 있고, 이 러너에 Python 같은 도구를 더 요구하고 싶지 않다.
  * 기존 배포 단계와 공용 `slack-notify`는 다른 담당의 작업물이다. T12는 실패 시 단계와 새 job을 **더하기만** 하기로 했다.
* **목표:**
  * 실패한 step의 오류 줄 · 로그 끝과, 실패 시점의 클러스터 상태(Rollout · 이벤트 · 문제 파드 로그 · 마이그레이션 Job 로그)를 함께 얻는다.
  * 기존 배포 단계 스크립트는 고치지 않는다.
  * onprem 러너에는 bash · kubectl · jq · sed 외의 도구를 요구하지 않는다.
  * 수집이 실패해도 배포 결과와 기존 알림은 바뀌지 않는다.

## 2. 고려한 옵션들 (Considered Options)

### 1. 같은 job 안에서 모두 수집 (출력 `tee` + 실패 시 단계)

배포 단계 출력을 `tee`로 파일에도 남기고, 같은 job의 `if: failure()` 단계가 그 파일 끝과 클러스터 상태를 함께 모은다.

**Pros**
* 클러스터 접속이 이미 있다. 재로그인이 없고 onprem self-hosted 러너도 그대로 쓴다.
* 실패 직후의 클러스터 상태를 바로 본다.
* job이 늘지 않아 알림이 늦어지지 않는다.

**Cons**
* 기존 배포 단계 스크립트에 `tee`를 넣어야 한다(다른 담당 영역 수정).
* 로그 가공을 onprem 러너에서 해야 해 Python 없이 bash로 처리해야 한다.
* `publish` job에도 같은 수정을 따로 붙여야 한다.

### 2. 별도 진단 job에서 모두 수집 (API 로그 + 클러스터 재접속)

실패한 job 뒤에 도는 진단 job(`needs`, `if: failure()`)이 끝난 job의 로그를 API로 받고, 클러스터에 다시 접속해 상태를 모은다.

**Pros**
* 기존 배포 단계를 고치지 않는다.
* 실패한 job의 전체 로그를 받는다.
* ubuntu 러너에서 돌아 Python을 쓸 수 있다.

**Cons**
* 대상별(aws · gcp · onprem) 클러스터 인증을 진단 job에서 다시 해야 한다. onprem은 맥북 러너에서만 접근할 수 있다.
* 재접속하는 사이 green 정리 · 롤백으로 실패 시점의 상태가 사라질 수 있다.
* job이 하나 늘어 알림이 조금 늦다.

### 3. 혼합: 클러스터 상태는 실패한 job 안, Actions 로그는 진단 job

실패한 `deploy` job 안에 **새로 추가하는** `if: failure()` 단계(`cluster.sh`)가 클러스터 상태를 모아 artifact로 올린다. 새 진단 job(ubuntu)은 job이 끝난 뒤 API로 실패한 `deploy` · `publish` job의 로그를 받아(`collect.py`) 클러스터 상태와 합친다.

**Pros**
* 기존 배포 단계를 고치지 않는다(실패 시 단계와 job을 더하기만 한다).
* 클러스터 상태는 접속이 살아 있는 실패 직후에 모은다. 재로그인이 없다.
* onprem 러너에는 bash · kubectl · jq · sed만 요구한다. 로그 가공은 ubuntu 진단 job이 Python으로 한다.
* 실패한 step을 포함한 job 로그 전체를 API로 받는다.

**Cons**
* 단계와 job이 하나씩 늘어 구성이 옵션 1 · 2보다 복잡하고, 알림이 조금 늦다.
* demo-app 호출부에 `actions: read` 권한이 없어 로그 API에 봇 App 토큰(`one-tatchi-bot`)이 필요하다.
* 공개 레포의 artifact는 다른 사람도 받을 수 있어 클러스터 출력의 비밀값을 올리기 전에 가려야 한다.

## 3. 결정 사항 (Decision Outcome)

* **옵션 3(혼합)을 선택한다.** 클러스터 상태는 실패한 `deploy` job 안의 새 `if: failure()` 단계(`cluster.sh`)가, Actions 로그는 새 진단 job(`collect.py`)이 API로 모은다.
* **옵션 1의 출력 `tee`는 채택하지 않는다.** 기존 배포 단계 수정이라서다. 실패한 step의 출력은 진단 job이 API로 받는다.
* **옵션 2의 클러스터 재접속은 채택하지 않는다.** 진단 job은 클러스터에 접속하지 않는다.

**이유**
* 마이그레이션 실패처럼 원인이 클러스터에만 남는 경우가 있어 실패 직후의 클러스터 상태가 필요하다. 그 시점에 접속이 살아 있는 곳은 실패한 job뿐이다.
* job 로그는 job이 끝나야 API로 받을 수 있으므로, 기존 단계를 고치지 않고 실패한 step의 출력을 얻는 방법은 뒤에 도는 job에서 API로 받는 것이다.
* "기존 단계와 공용 `slack-notify`는 고치지 않고 더하기만 한다"는 T12 작업 원칙과 onprem 러너의 도구 제약을 함께 만족하는 것은 옵션 3뿐이다.

## 4. 결과

* **구성 요소** (`.github/actions/failure-diagnosis/`)
  * `cluster.sh`: 실패한 `deploy` job 안에서 돈다. 서비스별 Rollout phase · 메시지, Warning 이벤트 최근 40개, Ready가 아니거나 재시작한 서비스 파드 10개의 로그 끝(재시작했으면 `--previous`), `<서비스>-migration` Job 상태 · 로그 → `cluster.json`.
  * `collect.py`: 진단 job에서 돈다. 실패한 `deploy` · `publish` job(최대 3개)의 로그에서 실패 step · 오류 줄 · 첫 `##[error]` 앞뒤를 뽑아 `cluster.json`과 합쳐 `evidence.json`(형식: `evidence.schema.json`)을 만든다.
  * `redact.sed`: 두 스크립트가 함께 쓰는 비밀값 가리기 규칙. GitHub는 등록된 시크릿만 가리므로 클러스터 · 앱 로그의 접속 문자열 비밀번호와 토큰 형태를 가린다. 가린 뒤 JSON이 깨지면 내용을 버리고 수집 실패로 남긴다.
* **수집 실패 처리:** 두 스크립트 모두 하나가 실패해도 멈추지 않고 `collection.<항목>.status`(`ok` · `failed` · `not_collected`)와 이유를 남긴다. `publish`만 실패했으면 클러스터 상태는 `not_collected`다. 수집 단계는 배포 결과를 바꾸지 않는다.
* **크기 상한:** 실패 step 로그 끝 12000자, 오류 줄 30개(줄당 500자), 파드 · Job 로그 끝 4000자, 이벤트 40개. Claude 입력과 비용을 제한한다.
* **`deploy.yml` 변경:** `deploy` job 끝에 실패 시 단계 하나, 실패한 job 뒤에 진단 job 하나를 더한다. 기존 단계와 기존 실패 알림은 그대로 두고 원인 요약은 새 Slack 메시지로 보낸다.
* **남은 확인:** 봇 App 토큰으로 job 로그 API가 열리는지, 실제 클러스터와 macOS bash 3.2에서 `cluster.sh`가 도는지는 `deploy.yml` 연결 뒤 demo-app에서 일부러 실패를 일으켜 확인한다.
