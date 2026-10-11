# [ADR-0020] 여러 배포 대상 동시 배포: 호출부 matrix, 모든 대상의 test가 통과해야 prod

* **상태 (Status):** 채택됨(Accepted). 호출부 템플릿은 T39(#243, PR #245)에서 구현했다. demo-app 적용과 Slack 승인 확인은 같은 작업에서 이어 한다.
* **날짜 (Date):** 2026-10-11
* **관련:** T39 (#243), T6(운영 승인), T8(yolo main PR), [`deploy.yml.tmpl`](../../skills/deploy-provision/templates/.github/workflows/deploy.yml.tmpl)

## 1. 배경 및 문제 상황 (Context and Problem Statement)

* **상황:** 재사용 `deploy.yml`은 `target`을 하나만 받는다. 호출부는 레포 변수 `DEPLOY_TARGET`으로 대상 하나를 고르고, 다른 대상은 수동 실행으로 따로 배포했다.
* **문제:** 같은 커밋을 aws · gcp · onprem에 함께 올리려면 실행을 대상 수만큼 반복해야 하고, 대상마다 다른 버전이 운영에 남을 수 있다.
* **목표:**
  * push 한 번으로 고른 대상 모두에 같은 이미지를 배포한다.
  * 재사용 워크플로와 App Chart는 바꾸지 않는다. 대상이 하나인 레포는 동작이 같다.
  * 대상별 동시성 잠금 · 감사 로그 · 승격 버튼은 지금처럼 대상(`target-label`) 단위로 남는다.

## 2. 고려한 옵션들 (Considered Options)

### 1. 호출부 matrix, 모든 대상의 test가 통과해야 prod (A)

`targets` job이 대상 목록으로 matrix JSON을 만들고, `test` · `prod` job이 그 matrix로 재사용 워크플로를 대상마다 호출한다. `prod`는 `needs: test`라 matrix 전체가 성공해야 시작한다.

**Pros**
* 운영에는 모든 대상에 같은 버전이 올라가거나, 어느 대상에도 올라가지 않는다.
* 호출부만 바뀐다. 재사용 워크플로 계약(`target` 하나)은 그대로다.

**Cons**
* 가장 느린 대상(대개 onprem)이 prod 시작을 늦춘다. 한 대상의 장애가 다른 대상의 운영 반영을 막는다.

### 2. 대상마다 test → prod를 따로 진행 (B)

test와 prod를 묶은 로컬 재사용 워크플로를 matrix로 호출한다.

**Pros**
* 한 대상의 실패가 다른 대상의 운영 반영을 막지 않는다.

**Cons**
* 대상마다 운영 버전이 달라질 수 있다. 감사 로그와 롤백 판단이 대상별 버전을 따로 추적해야 한다.
* 호출부에 워크플로 파일이 하나 더 생긴다.

### 3. 재사용 워크플로가 대상 목록을 받기

`deploy.yml`이 `targets` 배열을 받아 안에서 matrix를 돈다.

**Cons**
* 모든 대상 레포의 계약이 바뀌고, 대상별 동시성 · 승인 · yolo job을 전부 다시 짜야 한다.

## 3. 결정 (Decision)

**옵션 1(A)을 채택한다.**

* 대상 목록: `DEPLOY_TARGETS`(쉼표 구분) → `DEPLOY_TARGET` → `plan.yaml`의 `target`. 수동 실행은 대상 하나 또는 `all`.
* `fail-fast: false`: 한 대상이 실패해도 나머지 대상의 test 결과는 끝까지 본다. prod는 어느 대상도 진행하지 않는다.
* 목록의 첫 대상이 기준 대상이다. yolo 리포트 · main PR(`yolo-auto-merge`)은 기준 대상에서만 만든다.

## 4. 결과 (Consequences)

* yolo 브랜치에서 자동 머지는 기준 대상의 승격만 본다. 다른 대상의 실패는 그 대상의 알림으로만 남는다.
* prod 승인 대기(`approve` job)가 대상 수만큼 생긴다. Slack 승인 버튼(`<run_id>@prod`) 한 번으로 모두 처리되는지 demo-app에서 확인한다.
* onprem runner가 꺼져 있으면 그 대상 job이 대기하고 prod 전체가 기다린다. runner 상태 확인은 별도로 다룬다.
* 대상 간 데이터 동기화와 주소 하나로의 트래픽 분산은 범위 밖이다. 대상별 고정 주소는 T31 · T38이 다룬다.
