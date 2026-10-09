# [ADR-0002] AI 승격 판단 부품의 위치

* **상태 (Status):** 승인됨(Accepted)
* **날짜 (Date):** 2026-10-09
* **관련:** T7 (#16), 선행 T5 (#10), 설계 문서 6.5 · FR-7

## 1. 배경 및 문제 상황 (Context and Problem Statement)

* **상황:** 재사용 워크플로 `deploy.yml`은 green을 띄운 뒤 Rollout이 `Paused`가 되면 멈춘다. 서비스마다 matrix job으로 하나씩 배포한다(`max-parallel: 1`). 그 뒤의 promote / abort 판단은 T7이 맡는다.
* **문제:** 판단 로직(smoke 요청 → 지표 수집 → Claude 판단 → promote / abort)을 파이프라인의 어디에 둘지 정해야 한다. `deploy.yml`은 T5에서 계속 수정 중이고, 배포 시간 목표는 2분대(T9)다.
* **목표:**
  * T5 작업과 충돌하지 않는다.
  * 배포 시간을 불필요하게 늘리지 않는다.
  * 클러스터 없이도 판단 로직을 따로 테스트할 수 있다.
  * 배포 대상(aws · onprem · gcp)과 관계없이 같은 코드로 동작한다.

## 2. 고려한 옵션들 (Considered Options)

### 1. 별도 composite action

`.github/actions/promote-judge/`에 판단 로직을 두고, `deploy.yml`의 배포 job 안에서 한 단계로 호출한다.

**Pros**
* 판단 로직이 독립된 폴더에 있어 `deploy.yml` 변경은 호출 몇 줄로 끝난다.
* 같은 job 안에서 돌아 클러스터 접속(`kube-access`), 서비스 이름, 네임스페이스를 그대로 쓴다. 추가 로그인이나 job 대기 시간이 없다.
* 스크립트 단위로 가짜 서버 · 가짜 kubectl을 써서 테스트할 수 있다.
* 레포의 기존 부품 방식(`kube-access`, `image-push`, `audit-log`, `slack-notify`)과 같다.

**Cons**
* 연결하려면 `deploy.yml`에 몇 줄은 넣어야 해서 T5와 한 번은 맞춰야 한다.
* 관찰 시간만큼 배포 job이 길어진다.

### 2. `deploy.yml`에 직접 작성

배포 job의 마지막 단계들로 판단 로직을 바로 쓴다.

**Pros**
* 파일 하나로 끝나 구조가 단순하다.
* 같은 job이라 필요한 값을 바로 쓴다.

**Cons**
* T5로 수정 중인 파일을 동시에 크게 고쳐 충돌 위험이 크다.
* `deploy.yml`이 길어지고 판단 로직만 따로 테스트하기 어렵다.

### 3. 별도 재사용 워크플로

`promote.yml`을 만들고, 대상 레포 호출부에서 배포 job 다음 job(`needs: deploy`)으로 부른다.

**Pros**
* `deploy.yml`과 완전히 분리된다.
* 따로 실행 · 재실행하기 쉽다.

**Cons**
* job이 하나 더 떠서 러너 할당과 클러스터 재로그인 시간이 든다. 2분대 목표에 불리하다.
* matrix job의 출력은 서비스별로 넘기기 어려워, 판단할 서비스 정보를 다시 찾아야 한다.
* demo-app 호출부도 고쳐야 하고, T8(자동 머지)이 이 job 결과를 기다리도록 연결도 바꿔야 한다.

## 3. 결정 사항 (Decision Outcome)

* **옵션 1(별도 composite action)을 선택한다.**
* **옵션 3(별도 재사용 워크플로)은 판단을 배포와 따로 다시 돌려야 할 필요가 생기면 검토한다.**
* **옵션 2(`deploy.yml`에 직접 작성)는 채택하지 않는다.**

**이유**
* T5와 겹치는 부분이 호출 몇 줄뿐이라 병렬 작업이 가능하다.
* 같은 job 안에서 돌아 추가 job · 재로그인 시간이 없다. 배포 시간 목표에 가장 유리하다.
* 레포의 기존 공통 부품 방식과 같아 읽고 유지하기 쉽다. 배포 대상별 차이는 `kube-access`에 맡긴다.

## 4. 결과

* 판단 로직은 `.github/actions/promote-judge/`에 둔다. 입력은 서비스 이름 · 네임스페이스 · 모드(auto / manual) · 관찰 시간 · 기준값 · 모델 · API 키이고, 출력은 `decision` · `reason` · `report`다.
* `deploy.yml`에는 "주소" 단계 뒤에 호출 단계를 추가한다(T7 C7). 위치와 입력 추가는 T5 담당자와 맞춘다.
* 관찰 시간만큼 서비스별 배포 job이 길어진다. 관찰 시간 기본값은 배포 시간 목표(T9)와 함께 정한다.
* 판단 방식(규칙과 AI의 관계, 실패 시 기본값)과 지표 출처는 별도 ADR로 정한다.
