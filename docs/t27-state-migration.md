# T27 기본 맥북 state 이전 실행 절차

기본 `onprem` 기기의 소유자가 그 기기에서 실행한다. secondary의 state를 복사해 적용하지 않는다.
현재 secondary는 v2로 생성돼 기존 평문 state 이전 대상이 아니다. 해당 기기의 검사 통과와 fixture 이전은 기본 기기의 실제 이전 완료를 뜻하지 않는다.
Linux 실기 검증도 별도 후속이며 Linux CI 통과로 대체하지 않는다.

## 작업 전 기록과 중단 조건

1. 현재 repo/루트/프로필·클러스터 이름·API 포트·K3s 이미지·state lineage/serial을 확인한다. 기존 state가 없거나 다른 기기 소유이면 중단한다.
2. 해당 기기의 배포와 Terraform 작업이 끝난 것을 확인하고, 작업 동안 새 배포가 시작되지 않게 해당 runner 서비스를 정지한다. 다른 프로필, Docker, DB는 정지하거나 재생성하지 않는다. 설치된 관리 도구가 있다면 `onpremctl stop`으로 해당 프로필 서비스만 내려놓고 작업 뒤 `start`한다. 작업 중 AC 전원과 별도 `caffeinate -s`를 유지한다.
3. test/prod 각각 기존 검증 글을 SQL과 공개 API로 읽고 개수/일치 여부를 기록한다. PVC UID, DB StatefulSet/Secret UID, DB Secret 지문, 앱 digest/차트와 Helm revision을 기록한다. 비밀번호·토큰·Secret JSON·kubeconfig 본문·state/plan은 공개 로그나 Git에 올리지 않는다.
4. T17이 있으면 `t17-metrics.auto.tfvars.json`, 관측 Helm 설정·PVC·인증 Secret 지문과 중앙 수집 상태를 추가 기록한다. T33이 있으면 `db_link` module 주소, `operator-oauth` 관리 주체, publish/consume 설정을 보존한다. T32의 DB 위치/환경 범위도 유지한다.
5. 현재 state와 모든 옛 `.backup`·저장 plan·JSON 사본 위치를 찾는다. 이전 도구는 루트 바로 아래만 정리한다. 다른 위치의 사본과 개인 백업은 별도 목록으로 관리한다. 기존 DB 데이터 백업/복원 근거도 확인한다. state 백업만으로 DB 데이터를 복원할 수 있다고 보지 않는다.

## 모듈 준비와 암호화 이전

이 문서와 함께 병합된 `scripts/onprem`을 사용한다. 기존 root를 v2의 ephemeral 입력·provider 구조로 준비하되 아직 apply하지 않는다.
클러스터 이름/포트/버전, Secret namespace, DB 이름과 리소스 주소, T17/T33 설정을 그대로 둔다.
공통 템플릿으로 기존 root 전체를 덮어쓰거나 모든 클라우드 ref를 함께 올리지 않는다.
Terraform 1.11 이상, Kubernetes provider 2.38 계열과 `age`가 필요하다.

```bash
# 실제 기기의 절대 경로로 지정한다. CFG에는 비밀값을 넣지 않는다.
CFG=/absolute/path/onprem-config.json
ROOT=/absolute/path/existing/onprem/root
IDENTITY=/separate/safe/location/onprem-recovery.agekey
BACKUP=/separate/backup/location/onprem-before-v2.age

# 새 복구 키가 필요할 때만 실행. 기존 키를 덮어쓰지 않는다.
age-keygen -o "$IDENTITY"
RECIPIENT=$(age-keygen -y "$IDENTITY")
python3 scripts/onprem/onpremctl.py --config "$CFG" terraform init
python3 scripts/onprem/onpremctl.py --config "$CFG" migrate-state \
  --recipient "$RECIPIENT" --identity "$IDENTITY" --backup "$BACKUP"
```

개인키는 repo·Terraform 루트·백업과 별도 위치에 권한 600으로 보관한다. TF_LOG 계열과 셸의 `set -x`는 끈다.
도구는 원본을 메모리에서 암호화하고 실제 복호화 결과를 대조한 뒤 state만 이전한다. 비밀번호 회전, Secret/PVC/DB 변경은 하지 않는다.
루트 안의 다른 이름 plan은 `--plan-file "$ROOT/old-plan"`으로 명시할 수 있다. 원본 state·백업·plan과 Terraform JSON 사본은 암호화 백업에 포함된 동일 바이트/동등 state만 제거한다.
T17 tfvars 같은 운영 설정은 정리 대상이 아니다. 알 수 없는 비밀값·변경된 파일이 있으면 실패 상태를 보존하고 조사한다.

## 변경 없음과 실제 보존 확인

```bash
python3 scripts/onprem/onpremctl.py --config "$CFG" terraform plan \
  -input=false -detailed-exitcode -out="$ROOT/after-migration.tfplan"
python3 scripts/onprem/onpremctl.py --config "$CFG" audit-state
# 루트 밖의 별도 사본은 각 파일을 추가한다.
python3 scripts/onprem/onpremctl.py --config "$CFG" audit-state \
  --file /absolute/path/other-copy.tfplan
```

plan 종료 0(`No changes`)과 감사의 `passed: true`를 모두 요구한다. 종료 2는 변경 있음, 1은 오류이므로 완료 처리하지 않는다.
저장 plan의 JSON에 ephemeral 변수 이름이나 빈 기본값이 남는 것과 실제 인증값 저장은 구분한다. 값의 부재는 압축 내부까지 검사한다.
일반 wrapper는 저장 plan apply를 지원하지 않는다. T17의 별도 관측 도구는 검토된 저장 plan에 인증정보를 메모리로 재주입하므로 해당 경로를 유지한다.
T33 OAuth 값을 일반 tfvars나 Helm values에 넣어 검사를 우회하지 않는다.

SQL/API 검증 글, DB 비밀번호 지문, Secret/StatefulSet/PVC UID, 앱 digest/차트와 T17 수집 설정이 사전 기록과 같아야 한다.
암호화 백업은 별도 디렉터리에서 복호화하고, 구성 파일과 state의 lineage·serial·리소스 ID를 이전 전 기록과 대조한다. 검증 후 불필요한 복호화 평문은 남기지 않는다.
프로필 서비스를 다시 시작하고 runner online, test/prod 최신 URL의 화면·API·실제 DB 데이터, T17 중앙 지표 재수신을 확인한다.
이 기록과 관련 PR 병합이 모두 확보된 뒤에만 T27의 실제 state 이전 항목을 체크한다.

## 실패 시 복구

작업을 멈추고 암호화 원본을 유지한다. state 이전만 수행했다면 DB와 PVC를 롤백하거나 클러스터를 삭제할 이유가 없다.
복원할 state와 현재 lineage/serial·리소스 ID를 먼저 대조한다. 최신 배포로 바뀐 state를 과거 것으로 덮어쓰거나 `state push -force`로 해결하지 않는다.
모듈/루트도 같은 백업 시점과 맞춰야 한다. T17 이후의 state에 그 이전 전체 볼륨 백업을 무조건 복원하지 않는다.
실제 기본 기기에 접근하지 못하거나 plan/감사/보존 검사 중 하나라도 실패하면 이슈 항목은 미완료로 유지한다.
