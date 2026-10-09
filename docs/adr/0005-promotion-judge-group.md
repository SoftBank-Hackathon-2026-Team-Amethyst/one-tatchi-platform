# [ADR-0005] 서비스 묶음 단위 승격 판단

* **상태 (Status):** 승인됨(Accepted)
* **날짜 (Date):** 2026-10-09
* **관련:** T7 (#16), T5 (#68 deploy.yml 구조 변경), [ADR 0002](0002-promotion-judge-placement.md), [ADR 0004](0004-promotion-judge-rule-veto.md)

## 1. 배경 및 문제 상황 (Context and Problem Statement)

* **상황:** T5(#68)에서 `deploy.yml`이 서비스마다 job을 나누던 구조에서 "환경당 job 하나에서 서비스를 순서대로(BE → FE) 배포"하는 구조로 바뀌었다. prod 승인을 서비스 수만큼이 아니라 한 번만 받기 위해서다. 그래서 모든 서비스의 green이 Paused로 뜬 뒤, Slack 버튼(`all`)으로 함께 승격 · 취소한다.
* **문제:** `promote-judge`는 서비스 하나만 판단하도록 만들어졌다. 서비스 여러 개를 어떤 단위로 판단하고 실행할지 정해야 한다.
* **목표:**
  * BE · FE 버전이 섞이지 않는다.
  * 배포 시간(T9, 2분대)을 서비스 수만큼 늘리지 않는다.
  * 원가연(T5)의 배포 반복문을 크게 고치지 않는다.

## 2. 고려한 옵션들 (Considered Options)

### 1. 묶음 판단: 동시에 관찰하고 함께 결정

배포 단계가 끝난 뒤 Paused인 서비스들을 한 번에 넘긴다. smoke는 서비스마다 동시에 돌리고, 지표 · AI 판단은 서비스별로 한 뒤 하나라도 abort면 전체 abort, 모두 promote면 전체 promote한다.

**Pros**
* 서비스가 함께 올라가거나 함께 남아 버전이 섞이지 않는다. 버튼(`all`) · prod 승인 단위와 같다.
* 관찰 창이 한 번(기본 30초)이라 서비스 수와 관계없이 시간이 같다.
* `deploy.yml`에는 판단 단계 1개와 Paused 서비스 목록 출력만 더한다.

**Cons**
* 한 서비스만 문제여도 정상인 서비스까지 되돌린다.
* 서비스마다 Claude를 호출해 서비스 수만큼 API 호출이 생긴다.

### 2. 서비스별 판단: 배포 반복문 안에서 하나씩

배포 반복문 안에서 서비스마다 smoke · 판단 · 실행을 한다.

**Pros**
* 서비스마다 독립적으로 결정한다.

**Cons**
* BE만 promote, FE는 abort처럼 버전이 섞일 수 있다.
* 관찰 창이 서비스 수만큼 늘어난다(서비스 2개면 +60초).
* T5가 막 만든 배포 반복문을 직접 고쳐야 한다.

## 3. 결정 사항 (Decision Outcome)

* **옵션 1(묶음 판단)을 선택한다.**
* **옵션 2는 서비스를 독립적으로 배포 · 승격하는 구조로 바뀌면 다시 검토한다.**

**이유**
* 현재 배포 · 승인 · 버튼이 모두 "서비스 묶음" 단위라 판단도 같은 단위여야 일관된다.
* 배포 시간 목표에 가장 유리하다.

## 4. 결과

* `promote-judge` 입력이 `release` → `releases`(공백 구분)로 바뀐다. `group.sh`가 서비스마다 기존 스크립트(smoke · metrics · judge · act)를 돌린다.
* 묶음 결정은 `promote-judge/judgment.json`, 서비스별 결과는 `promote-judge/<release>/`에 남는다.
* 묶음 abort 때문에 함께 abort한 서비스는 `source: group`, 원래 판단은 `ai_decision_alone`으로 남긴다.
* `deploy.yml`의 배포 단계는 Paused인 서비스 목록(`paused`)을 출력한다. 첫 배포처럼 바로 Healthy인 서비스는 판단하지 않는다.
