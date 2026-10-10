# [ADR-0018] 계층별 배포 위치: `plan.yaml`의 `layers`와 `database_scope`

* **상태 (Status):** 승인됨(Accepted). 계약 · 검사(`check-artifacts.sh`) · AWS 루트 템플릿 · 스킬 문서 · 이전 절차는 T32에서 구현하고 로컬로 검증했다(PR #209). demo-app test에서의 실제 검증(CRUD · 재배포 뒤 보존 · 연결 실패 시 승격 차단)은 T33으로 이관했다(2026-10-11, 배규태 · 원가연 합의).
* **날짜 (Date):** 2026-10-10
* **관련:** T32 (#155), T33 (#160), T28 (#130), [ADR 0016](0016-cloud-db-tls-and-memory-fallback.md)(DB TLS), [ADR 0017](0017-db-link-tailscale.md)(DB 통로 `db_link`), 설계 문서 6.3 · 6.4 · FR-9

## 1. 배경 및 문제 상황 (Context and Problem Statement)

* **상황:** 배포 대상은 앱 전체에 하나다. `plan.yaml`의 `target`(aws · gcp · onprem)이 워크플로 호출부의 기본 대상과 Terraform 루트(`infra/envs/<target>`)를 정하고, DB도 같은 대상에 만든다(AWS면 RDS).
* **문제:** "앱은 클라우드, 데이터는 사내"처럼 계층마다 위치를 나누는 구성을 적을 방법이 없다. 이미 운영 중인 앱은 test · prod가 같은 RDS를 쓰므로(demo-app), DB 위치를 통째로 바꾸면 운영 데이터 이전이 먼저 필요하다.
* **목표:**
  * FE · BE · DB의 위치를 설정으로 고른다. 키가 없으면 지금과 같다.
  * 첫 지원 조합은 FE · BE = AWS, DB = 온프레미스 하나다.
  * 운영 데이터를 자동으로 옮기거나 기존 DB를 자동으로 지우지 않는다. 이미 운영 데이터가 있는 앱은 test만 먼저 옮길 수 있어야 한다.
  * 산출물을 만드는 스킬(`deploy-provision`)과 검사(`check-artifacts.sh`)가 같은 정보로 판단한다.

## 2. 고려한 옵션들 (Considered Options)

### 계층별 위치를 적는 형식

#### 1. `layers: {fe, be, db}` 선택 키, `target`은 앱 대상으로 유지

**Pros**
* 키가 없으면 기존 동작이라 이미 배포 중인 레포를 바꿀 필요가 없다.
* 이번 조합은 앱 대상이 aws 하나라 `target`을 읽는 기존 코드(호출부, `infra/envs/<target>`)를 바꾸지 않는다.
* 후속 조합(FE=GCP 등)도 같은 키로 적는다.

**Cons**
* 서비스가 FE · BE 두 계층에 맞지 않는 앱(예: worker)은 계층 이름이 어색하다.

#### 2. 서비스마다 대상(`services[].target`)

**Pros**
* 서비스 수와 관계없이 적을 수 있다.

**Cons**
* 서비스별로 다른 클라우드에 앱을 올리는 것은 이번 범위 밖인데 형식과 검사 규칙만 커진다.

#### 3. `target`에 합성 값(`aws+onprem-db`)

**Pros**
* 키가 늘지 않는다.

**Cons**
* 조합이 늘 때마다 값이 늘고, `target`을 읽는 모든 곳을 고쳐야 한다.

### 외부 DB를 쓸 환경을 고르는 위치

#### 1. `plan.yaml`의 `database_scope` (생략하면 모든 환경)

**Pros**
* AWS 루트를 렌더하는 `deploy-provision`과 `check-artifacts.sh`가 같은 값을 보고 RDS를 남길지 정한다. 운영 DB를 빼는 렌더를 검사로 막을 수 있다.

**Cons**
* 계약 키가 하나 는다.

#### 2. AWS Terraform 변수만 (예: `db_link` 맵의 키)

**Pros**
* 계약이 `layers` 하나로 단순하다.

**Cons**
* 스킬은 렌더할 때 Terraform 변수를 보지 않아 RDS를 뺄 수 있다. 막으려면 RDS를 `count`로 켜고 끄고 기존 주소를 `moved`로 옮겨야 해 재생성 · 삭제 계획 위험이 생긴다.
* 스킬이 다시 만드는 `terraform.tfvars`에 사람이 적은 값이 덮어써질 수 있다.

#### 3. 고르지 않음 (하이브리드면 모든 환경)

**Pros**
* 가장 단순하다.

**Cons**
* 이미 운영 중인 앱은 test를 검증하기 전에 운영 데이터부터 옮겨야 한다. 규제 대상이면 운영 승인도 먼저 받아야 한다.

## 3. 결정 사항 (Decision Outcome)

* **형식은 `layers` 선택 키(옵션 1)를 쓴다.** `target`의 의미는 그대로다.
* **환경 범위는 `plan.yaml`의 `database_scope`(옵션 1)로 고른다.** 생략하면 모든 환경이다.
* **지원 조합은 하나다:** `target: aws`, `layers: {fe: aws, be: aws, db: onprem}`.

**이유**
* 기존 레포와 기존 코드의 동작을 바꾸지 않고 시작할 수 있다.
* AWS 루트를 만드는 주체가 스킬이므로, RDS 유지 여부는 렌더 시점에 스킬이 알아야 한다.
* 조합을 하나로 묶어야 계약 · 검사 · 템플릿 · 실제 연결을 끝까지 검증할 수 있다. 조합마다 통로 · 자격증명 · 비용 계산이 달라진다.

**규칙** (형식과 예시는 `skills/deploy-analyze/references/report-format.md`)
* `layers`를 쓰면 세 키를 모두 적고, `fe` · `be`는 `target`과 같다.
* `layers.db`가 `target`과 다르면 `database: true`인 서비스가 하나 이상 있다.
* `database_scope`는 `layers.db`가 `target`과 다를 때만 쓴다(`test` · `prod`). 새 앱은 생략하고, 운영 데이터가 있는 앱만 좁힌다. 빠진 환경은 기존 클라우드 DB를 계속 쓰고 스킬은 그 DB를 지우지 않는다.
* 계약에는 기기를 적지 않는다. `onprem`은 팀이 운영하는 온프레미스 클러스터이고, 기기는 러너 라벨 · 클러스터 이름이 정한다.
* 클라우드에서 DB로 가는 통로는 `modules/db_link/tailscale`(ADR 0017)이다. 산출물은 `database_scope`의 환경마다 AWS 루트의 `db_link` 입력(tailnet 이름 · 자격증명 시크릿 이름)을 렌더하고, `<앱>-db` Secret은 기존과 같은 형식(Secrets Manager의 username/password JSON + 통로 주소)으로 `service-base`가 만든다. Terraform 변수 `db_link`는 렌더 결과이고, 무엇을 넣을지의 근거는 `plan.yaml`이다.
* 지원하지 않는 조합은 인프라 변경 전에 `check-artifacts.sh`가 오류로 멈춘다.

## 4. 결과와 한계

* **후속 확장:** FE=GCP / BE=AWS / DB=onprem, DB를 다른 클라우드에 두는 조합, 서비스별 대상은 같은 `layers` 형식 위에서 조합별로 추가한다. 조합마다 통로 · 자격증명 · 검사 · 템플릿 · 검증이 필요하다.
* **운영 데이터 이전은 자동화하지 않는다.** `database_scope`에 운영 환경을 넣기 전에 사람이 [이전 절차](../hybrid-db.md)(백업 · 복원 · 전환 · 확인 · 기존 DB 정리)를 따른다. RDS 모듈은 기본값이 삭제 보호 없음 · 최종 스냅샷 건너뜀이라, RDS를 빼는 렌더를 적용하기 전에 수동 스냅샷이 필수다. 무중단 이전과 DB 이중화는 별도 작업이다.
* **온프레미스 가용성이 앱 가용성이 된다.** 현재 온프레미스 기기는 데모용 맥북이다. 기기가 꺼지거나 잠들면 클라우드에 떠 있는 앱도 DB를 잃는다. 연결이 끊겼을 때 승격이 막히는지는 실제 검증에서 확인한다.
* **비용 분석은 이 조합을 아직 계산하지 않는다.** 예산 분석기(T16)는 단일 대상만 비교한다. 하이브리드 후보의 비용은 보고서에 미산정으로 표시한다.
* 분석 스킬의 "하이브리드는 추천하지 않는다" 규칙은 이 조합에 한해 바뀐다(`deploy-analyze/SKILL.md` 추천 규칙 6).
* 검사(`check-artifacts.sh`)는 렌더가 `plan.yaml`과 맞는지만 본다. 운영 데이터가 있는 앱이 `database_scope`를 생략하는 실수는 분석 단계의 보존 규칙(기존 RDS가 있으면 `[test]`로 시작)과 PR의 Terraform plan 확인으로 막는다.
