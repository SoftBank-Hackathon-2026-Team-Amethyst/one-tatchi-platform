# 맥북 온프레미스 운영 (T27, v2)

평상시에는 **충전기·네트워크 연결, 덮개 열림, 로그인 세션 유지** 상태에서 화면만 잠그거나 끈다.
launchd의 `caffeinate -s`가 AC 전원에서 시스템 잠자기를 막는다. 화면 잠금·화면 꺼짐·FileVault는 그대로 유지한다.
덮개 닫기, 수동 잠자기, 로그아웃, 배터리 장시간 운용은 보장하지 않는다.
재부팅 후에는 FileVault 해제와 로그인 한 번이 필요하다. 자동 로그인은 설정하지 않는다.

## 기기별 준비

Python 3.9+, Docker Desktop, k3d, kubectl, Terraform 1.11+, Helm 4를 설치하고 PATH에서 실행할 수 있게 한다.
배포 runner의 공통 스크립트에는 jq·yq v4·gh도 필요하다.
GitHub의 **demo-app → Settings → Actions → Runners → New self-hosted runner** 안내로 공식 runner를 등록한다.
runner 디렉터리는 임시 폴더·Actions `_work` 밖의 고정 경로로 정한다. `svc.sh install`은 실행하지 않는다.
이미 공식 서비스를 사용 중이면 `./svc.sh stop && ./svc.sh uninstall`로 기존 서비스만 해제한 뒤 이 도구로 연결한다.
runner 등록·클러스터·DB·PVC는 삭제하지 않는다.

| 기기 | profile | cluster / API port | runner 고유 라벨 | 배포 선택 |
|---|---|---|---|---|
| 기본 기기 | default | 기존 이름(기본 onetouch) / 기존 포트 | onprem | onprem |
| 추가 기기 예시 | secondary | onetouch-secondary / 6558 | onprem-secondary | onprem-secondary |

다른 작업의 클러스터(예: `t17-local`)는 이 도구에 연결하지 않는다. 두 기기의 state를 공유하거나 복사해 사용하지 않는다. profile은 사람 이름이 아니라 기기 식별자이며 다른 이름으로 추가할 수 있다.
GitHub 변수 `ONPREM_CLUSTER`(기본값 `k3d-onetouch`)와 `ONPREM_SECONDARY_CLUSTER`에 각 기기의 실제 kube context를 설정한다. 기존 클러스터는 이름을 바꾸거나 재생성하지 않는다.
기존 환경은 **기존 state가 있는 루트**를 지정한다. 클러스터는 있는데 state가 없으면 모든 변경을 중단하고 원본 state부터 찾는다.

다음 내용을 `config.json`으로 저장한다. 비밀값은 넣지 않는다. 경로는 자신의 절대 경로로 바꾼다.

```json
{
  "profile": "secondary",
  "cluster": "onetouch-secondary",
  "api_port": 6558,
  "service": "demo-app",
  "terraform_root": "/absolute/path/demo-app/infra/envs/onprem",
  "runner_dir": "/absolute/path/actions-runner-secondary",
  "environments": ["test", "prod"]
}
```

## 새 클러스터만 생성

v2로 생성한 onprem 루트에서 사용한다. 스크립트의 `terraform` 명령을 통해 인증정보를 메모리로 공급한다.
tfvars에는 name/service 같은 일반 설정만 둔다. `onprem_auth`, `onprem_db_passwords`, TF_LOG는 파일이나 환경에 따로 저장하지 않는다.

```bash
python3 scripts/onprem/onpremctl.py --config /absolute/path/config.json terraform init
python3 scripts/onprem/onpremctl.py --config /absolute/path/config.json terraform apply -target=module.cluster
python3 scripts/onprem/onpremctl.py --config /absolute/path/config.json terraform apply -target=module.cluster_addons
python3 scripts/onprem/onpremctl.py --config /absolute/path/config.json terraform apply
```

처음 두 `-target`은 provider와 CRD를 준비하는 부트스트랩 전용이다. 이후에는 전체 plan/apply를 사용한다.
새 DB만 임의 비밀번호를 만든다. 기존 Secret은 그대로 읽어서 사용한다.
DB/PVC가 존재하는데 Secret이 없으면 중단한다. 새 비밀번호 생성, DB 재생성으로 해결하지 않는다.
저장 plan에 ephemeral 값은 담기지 않는다. 이 wrapper는 저장 plan의 apply를 거부한다. 일반 plan → apply 흐름으로 기존 Secret과 기기 소유권을 다시 확인한다.

## 서비스 설치와 운용

```bash
python3 scripts/onprem/onpremctl.py --config /absolute/path/config.json install
```

실행 파일과 설정은 `~/Library/Application Support/one-tatchi/onprem/<profile>/`로 복사된다.
이후에는 그 안의 `bin/onpremctl.py --config …/config.json`을 사용한다.
고정 경로의 Python·k3d·Terraform 등 실행 파일은 유지해야 한다.

| 명령 | 동작 |
|---|---|
| doctor / status | AC 전원·잠자기 assertion·서비스·Docker·pod 상태·현재 test/prod 터널 주소 확인 |
| start | 자신의 LaunchAgent 3개만 시작, 이미 실행 중이면 중복 생성하지 않음 |
| stop | 자신의 잠자기 방지·runner·복구 서비스를 해제. 클러스터/DB/Docker는 유지 |
| uninstall | stop 후 자신의 LaunchAgent 파일만 제거. 데이터·state·runner 등록·로그는 보존 |
| terraform | 소유권과 DB 비밀번호를 확인한 뒤 Terraform 실행 |
| migrate-state | 암호화 복구 백업을 검증한 뒤 기존 평문 state를 이전 |

로그인 시 `restore`가 Docker Desktop을 열고, 준비를 기다린 뒤 **기존** k3d → Kubernetes → cloudflared 순서로 확인한다.
runner는 Kubernetes 준비 후 공식 `runsvc.sh`로 시작한다. 실패하면 launchd가 재시도한다.
`logs/restore.error.log`, `restore.json`에 실패 단계가 남는다. 자동 apply·이미지 배포·트래픽 승격은 하지 않는다.
Docker가 macOS 권한/약관 동의를 요구한다면 최초 설치 때 처리한다. 시스템 설정의 백그라운드 항목 차단도 해제해야 한다.

## 기존 v1 state 이전 (기존 기기)

기존 runner의 작업을 마친 뒤 다른 Terraform 실행이 없는 시간에 수행한다. 먼저 root를 v2의 ephemeral 입력/provider 구조로 바꾸고 `terraform init`한다.
이 단계에서는 **apply하지 않는다**. 클러스터 이름·포트·DB 이름·Secret namespace는 기존 값을 유지한다.
`age`를 설치하고 복구 키를 준비한다. 암호화 백업은 state 루트 밖에, 개인키는 별도 안전한 장소에 보관한다.

```bash
age-keygen -o /safe/place/onprem-recovery.agekey
# 출력된 공개 recipient(age1...)를 아래에 사용한다.
python3 scripts/onprem/onpremctl.py --config /absolute/path/config.json migrate-state \
  --recipient age1... --identity /safe/place/onprem-recovery.agekey \
  --backup /safe/place/onprem-before-v2.age
python3 scripts/onprem/onpremctl.py --config /absolute/path/config.json terraform plan
```

도구는 state의 lineage·serial·클러스터와 실제 Secret을 대조한다. 알려진 DB 비밀번호와 k3d 인증 필드만 정리하며 리소스 ID는 유지한다.
원본 state, `.tfstate.backup`, `.tfplan` 및 확장자 없는 Terraform plan ZIP을 메모리에서 묶어 age로 암호화하고 실제 복호화까지 대조한다.
다른 이름의 plan은 `--plan-file /absolute/path/file`로 명시한다. root 밖의 백업·복사본은 자동 삭제하지 않으므로 별도로 확인한다.
정리 뒤 알 수 없는 비밀값이 남거나 파일이 변경되면 삭제하지 않고 실패한다. 로그에는 값 대신 위치·개수만 출력한다.
백업 복구는 별도 디렉터리에 복호화해 내용을 확인하고, 작업 중단 상태에서 기존 lineage/serial과 비교한 뒤 수행한다. 무조건 `state push -force`하지 않는다.
평문 파일 삭제는 SSD에서 과거 블록의 물리적 완전 삭제를 보장하지 않는다. FileVault와 기존 백업 보존 정책은 유지한다.

이후 plan에서 DB/Secret/PVC 교체, 삭제, 비밀번호 변경이 나오면 apply하지 않는다. 정상 이전은 기존 Secret/데이터가 유지되고 재apply가 무변경이어야 한다.

## 배포·터널·이미지

deploy와 rollout은 기기 선택을 같은 runner·cluster·알림 대상에 전달한다. Slack 버튼도 `onprem-secondary.test` 등의 대상을 유지한다.
PR은 hosted runner에서만 검사한다. self-hosted에 PR 코드를 실행하지 않는다.
`tunnel.py`는 해당 서비스/환경을 가리키는 현재 cloudflared pod의 현재 시작 이후 로그만 읽는다.
공개 서비스의 터널 없음·대상 불일치·조회 실패·URL 누락은 실패다. 내부 BE에 외부 주소가 없는 것은 정상이다.
Quick Tunnel URL은 재시작하면 바뀔 수 있으므로 `status`에서 다시 확인한다.

checks에서 두 아키텍처를 한 번 빌드·검사하고 같은 run의 OCI artifact를 hosted publisher가 digest 보존 복사한다.
배포 시 재빌드하지 않는다. artifact 만료/누락, 다른 SHA/run, 검사 미통과, 기존 SHA 태그의 digest 충돌은 실패한다.
이미 발행한 run은 실패한 배포 job만 재실행한다. 전체 checks를 재실행해 다른 바이트가 만들어졌다면 기존 태그를 덮어쓰지 않는다.
prod는 test에서 Healthy/stable인 **동일 repository@digest**만 사용한다. AI의 promote 추천만으로 승격 완료를 간주하지 않는다.

v2는 변경된 onprem 모듈 계약이다. `.deploy/config.yaml`의 선택형 `infra_versions`로 기존 AWS/GCP 루트를 v1에 고정할 수 있다.
자동 버전 갱신도 이 고정을 유지한다. v2 릴리스는 기존 소비자에게 전체 루트 자동 갱신을 요청하지 않는다.

## 실기 검증과 기록

각 기기에서 별도로 검증하며 다른 기기의 성공을 대신 기록하지 않는다.

1. test/prod 게시판에 서로 다른 검증 글을 저장하고 각각의 글 ID·본문을 기록한다.
2. 외부 hosted probe를 35분 실행하고 두 URL을 5초마다 확인한다. baseline status와 Docker 시작 시각을 보관한다.
3. 화면을 잠그고 화면 꺼짐까지 포함해 최소 30분 유지한다. 잠금·해제 시각은 사용자가 기록한다.
4. 잠금 도중 해당 runner의 진단 job이 성공하고 계속 온라인인지 확인한다.
5. HTTP 오류 0, 동일 DB 글, 동일 pod UID·container startedAt·restartCount와 Docker 시작 시각을 확인한다.
6. 별도 안전한 시점에 재부팅·로그인 후 추가 명령 없이 10분 내 복구와 데이터 보존을 확인한다.

잠금 테스트와 재부팅 테스트는 다른 검증이다. 자동 테스트만 통과한 경우 실기 검증 완료로 표시하지 않는다.
Linux 실기 검증은 선택 후속 작업이다.

참고: [Apple 전원 설정](https://support.apple.com/guide/mac-help/change-battery-settings-mchlfc3b7879/mac),
[GitHub 사용자 서비스](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/configure-the-application?platform=mac),
[Terraform write-only](https://developer.hashicorp.com/terraform/language/manage-sensitive-data/write-only).
