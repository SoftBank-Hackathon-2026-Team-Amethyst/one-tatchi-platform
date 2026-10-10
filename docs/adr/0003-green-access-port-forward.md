# [ADR-0003] 승격 판단 시 green 접속 방식

* **상태 (Status):** 승인됨(Accepted)
* **날짜 (Date):** 2026-10-09
* **관련:** T7 (#16), [ADR 0002](0002-promotion-judge-placement.md), 설계 문서 6.5 · FR-6 · FR-7

## 1. 배경 및 문제 상황 (Context and Problem Statement)

* **상황:** green은 승격 전에는 Service `<release>-preview`로만 열려 있어 사용자 트래픽이 없다. 그래서 판단 근거를 만들려면 파이프라인이 green에 직접 smoke 요청을 보내야 한다. 판단은 배포 job 안에서 돈다(ADR 0002).
* **문제:** 러너가 green에 어떻게 접속할지 정해야 한다. 배포 대상마다 미리보기 주소 사정이 다르다.
  * aws: ALB의 미리보기 포트(`:8080`)가 있다.
  * onprem: green은 터널에 열지 않는다. `deploy.yml`의 "주소" 단계는 URL 대신 `port-forward` 명령 문자열을 만든다.
  * 현재 demo-app은 onprem에만 배포한다.
* **목표:**
  * 모든 배포 대상(aws · onprem · gcp)에서 같은 코드로 동작한다.
  * T5가 수정 중인 `deploy.yml`을 고치지 않는다.
  * green을 승격 전에 외부에 더 열지 않는다.

## 2. 고려한 옵션들 (Considered Options)

### 1. `kubectl port-forward svc/<release>-preview`

러너에서 preview Service로 로컬 포트를 열고 `http://127.0.0.1:<포트>`로 요청한다.

**Pros**
* 클러스터 접속(`kube-access`)만 되면 배포 대상과 관계없이 같은 방식이다.
* `deploy.yml`의 주소 계산이나 출력에 기대지 않는다.
* green을 외부에 열 필요가 없다.

**Cons**
* Ingress · 로드밸런서를 거치지 않아 그 구간의 문제는 잡지 못한다.
* Service로 포워딩해도 실제로는 파드 하나에 붙는다. 여러 파드에 고르게 요청하지 않는다.
* 쿠버네티스 API 서버를 거쳐 응답 시간이 실제보다 조금 길게 잡힌다(특히 원격 클러스터).

### 2. 미리보기 주소(Ingress) 사용

`deploy.yml`이 계산한 미리보기 주소로 요청한다.

**Pros**
* 실제 사용자 경로(로드밸런서 → Service → 파드)와 같다.
* 여러 파드에 요청이 나뉜다.

**Cons**
* onprem에는 미리보기 주소가 없다. green을 터널에 열어야 하고, 그러면 승격 전 버전이 외부에 노출된다.
* `deploy.yml`이 preview 주소를 출력으로 내보내도록 고쳐야 한다(T5와 충돌).
* 배포 대상마다 주소를 얻는 방법이 달라 분기가 늘어난다.

## 3. 결정 사항 (Decision Outcome)

* **옵션 1(`kubectl port-forward`)을 선택한다.**
* **옵션 2(미리보기 주소)는 모든 배포 대상에 미리보기 주소가 생기고 Ingress 구간까지 검증해야 할 때 다시 검토한다.**

**이유**
* 현재 데모 대상인 onprem에서 바로 쓸 수 있는 방법은 옵션 1뿐이다.
* 배포 대상별 차이를 `kube-access`에만 두는 기존 설계(이식성)와 맞는다.
* `deploy.yml`을 고치지 않아 T5와 병렬로 작업할 수 있다.

## 4. 결과

* `smoke.sh`는 preview Service의 첫 번째 포트로 port-forward를 열고, 관찰 창이 끝나면 닫는다.
* Ingress · 로드밸런서 구간은 판단 범위에서 빠진다. 그 구간은 승격 후 active 주소로 확인한다.
* p95 기준값은 port-forward 경유 지연을 감안해 느슨하게 둔다(`max-p95-ms` 2000, 잠정).
* port-forward가 열리지 않거나 도중에 끊기면 smoke 결과가 없거나 실패로 남아 판단은 abort가 된다.

## T30 보완 (2026-10-10)

기존 차트의 공개 preview Ingress는 제거한다. 공개 preview 포트를 다시 사용하는 선택은 폐기한다. 현재 접근 경계와 기존 설치 마이그레이션은 [ADR 0011](0011-private-green-access.md)을 따른다. port-forward 사용 자체가 클러스터 내부 접근을 차단하거나 Agent만 허용한다는 뜻은 아니다.
