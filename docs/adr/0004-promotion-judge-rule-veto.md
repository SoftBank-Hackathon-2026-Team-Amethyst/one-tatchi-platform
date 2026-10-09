# [ADR-0004] 승격 판단에서 규칙과 AI의 관계

* **상태 (Status):** 승인됨(Accepted)
* **날짜 (Date):** 2026-10-09
* **관련:** T7 (#16), [ADR 0002](0002-promotion-judge-placement.md), [ADR 0003](0003-green-access-port-forward.md), 설계 문서 6.5 · FR-7

## 1. 배경 및 문제 상황 (Context and Problem Statement)

* **상황:** `metrics.sh`가 smoke 지표(에러율 · p95)와 green 파드 상태(Ready · 재시작)를 기준값과 비교해 규칙 판정(pass / fail)을 만든다. 설계 문서는 "AI가 지표를 보고 promote / abort를 정하고 근거를 남긴다"고 하고, 이슈는 "(검토) 숫자 판정은 AnalysisTemplate"을 남겨 두었다.
* **문제:** 규칙 판정과 AI 판단 중 무엇이 최종 결정인지 정해야 한다. 팀 원칙은 "AI도 검사를 건너뛸 수 없다"이다.
* **목표:**
  * 완료 기준(정상 버전은 promote, 500을 내는 버전은 abort)을 확실히 지킨다.
  * AI가 판단과 근거를 만든다(AI 활용).
  * AI가 틀려도 문제 있는 버전이 승격되지 않는다.

## 2. 고려한 옵션들 (Considered Options)

### 1. 규칙만

스크립트 또는 Argo Rollouts AnalysisTemplate이 기준값으로만 정한다.

**Pros**
* 빠르고 예측 가능하며 API 비용이 없다.

**Cons**
* AI가 판단하지 않아 설계(6.5, FR-7)와 맞지 않는다.
* 근거가 규칙 문장뿐이다.

### 2. AI만

지표를 Claude에 보내고 답을 그대로 따른다.

**Pros**
* 설계 문구와 가장 가깝다.

**Cons**
* AI가 잘못 promote하면 500을 내는 버전이 승격된다.
* 기준값 검사를 AI가 건너뛸 수 있어 팀 원칙과 충돌한다.

### 3. 규칙 + AI, 규칙에 거부권

규칙 판정과 지표를 함께 AI에 보낸다. 규칙이 fail이면 AI 답과 관계없이 abort다. 규칙이 pass면 AI 판단을 따른다(AI가 더 엄격하게 abort할 수 있다).

**Pros**
* 기준값을 넘은 버전은 항상 abort라 완료 기준을 확실히 지킨다.
* 규칙을 통과해도 AI가 지표 이상(예: 특정 경로만 느림)을 보고 abort할 수 있다.
* 컴플라이언스 원칙(AI도 검사를 건너뛸 수 없다)과 같다.

**Cons**
* 규칙이 fail일 때 AI는 결정이 아니라 설명만 한다.

### 4. 규칙 + AI, AI가 규칙을 뒤집을 수 있음

규칙 판정은 참고로만 주고 AI가 최종 결정한다.

**Pros**
* AI 재량이 가장 크다.

**Cons**
* 옵션 2와 같은 위험이 있다.

## 3. 결정 사항 (Decision Outcome)

* **옵션 3(규칙 + AI, 규칙에 거부권)을 선택한다.**
* **옵션 1의 AnalysisTemplate은 AI 없이 클러스터 안에서 자동 판정해야 할 때 검토한다.**
* **옵션 2, 4는 채택하지 않는다.**

**이유**
* 완료 기준과 팀 컴플라이언스 원칙을 동시에 지키는 유일한 옵션이다.
* AI는 모든 경우에 판단 근거를 만들고, 규칙이 pass일 때는 결정권도 가진다.

## 4. 결과

* 규칙이 fail이어도 AI를 호출한다. 결정은 abort로 고정하고, AI에게는 원인 설명을 받아 근거로 남긴다(데모의 "AI 판단 근거" 장면, 운영 승인 화면).
* AI 판단이 없거나 쓸 수 없으면 abort다: API 키 없음, 호출 실패 · 시간 초과, 거절(`stop_reason: refusal`), 형식 오류. 설계 문서대로 재시도하지 않는다.
* `judgment.json`의 `source`로 결정 출처를 남긴다: `ai`(AI 결정) · `rule`(규칙 거부권) · `fallback`(AI 판단 없음).
* 모델은 입력 `model`로 바꾼다. 기본값 `claude-sonnet-5-5`.
