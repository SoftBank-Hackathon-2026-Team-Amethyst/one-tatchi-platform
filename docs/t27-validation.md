# T27 검증 기록

날짜별 누적 기록이다. 현재 판정은 마지막 실기 검증 항목을 따른다.

검증일: 2026-10-09. 플랫폼 기준 main `fca944a`, demo-app 통합 기준 main `7893547`(T17 #40 포함).
T17의 브랜치와 `t17-local`은 보존한다. 아직 두 기기의 T27 완료 기준 전체를 충족한 상태는 아니다.

## 자동 검사

- `scripts/tests/run.sh`: Linux 컨테이너에서 기존 T7·T13·T14·지표·버전 갱신 검사와 신규 onprem/OCI 검사 통과.
- 신규 onprem 27개, OCI 11개, yolo 승격 11개 Python 테스트 통과. 기기 라우팅은 기본 `onprem`과 추가 `onprem-secondary`를 사용한다.
- macOS 기본 Bash 3.2에서도 템플릿 렌더/산출물 검사를 실행했다. 값에 따옴표가 추가되던 기존 문자열 치환을 수정했고 v1/v2 계약 분기 모두 통과했다.
- Terraform fmt, 변경 모듈 init/validate, Helm의 digest 렌더/기존 tag 호환, Trivy IaC HIGH/CRITICAL 검사 통과.
- actionlint 1.7.12: 새 workflow 입력/표현식 오류 없음. 기존 `actions/create-github-app-token@v3`의 client-id에 관한 내장 메타데이터 오탐은 공식 v3 action.yml로 대조했다. 공식 정의에는 client-id가 존재하고 app-id는 필수가 아니다.

## 현재 맥북: secondary 프로필

- 기존 `macbook-onprem` / `onprem`은 변경하지 않았다. 이 runner는 확인 시 offline이었다.
- 새 runner `macbook-onprem-secondary` / `onprem-secondary`는 online, 전용 launchd 서비스 3개가 실행 중이다.
- AC 전원과 관리 대상 caffeinate assertion을 확인했다. 관리 대상 caffeinate만 종료했을 때 launchd가 재시작했다. 화면 잠금 30분 검증과는 별개의 점검이다.
- 독립 클러스터·test/prod DB·환경별 터널을 생성했다. 실제 클러스터 이름은 로컬 설정과 `ONPREM_SECONDARY_CLUSTER` 변수로 연결한다. 범용 코드에 소유자 이름을 넣지 않는다.
- 전체 최초 apply: 8개(DB/서비스 기반) 생성, 변경·삭제 0. 재적용 plan: `No changes`, detailed exit code 0.
- live DB 비밀번호 2개와 관리자 인증정보 2개를 메모리에서 읽어 state, `.backup`, 저장 plan 내부 ZIP까지 대조했다. 알려진 비밀값 일치 0. 값은 로그에 남기지 않았다.
- 별도 legacy 형식 state fixture에서 age 암호화→실제 복호화 검증→Terraform state push→평문 백업/plan 제거를 처음부터 실행했다. DB 비밀번호와 실제 환경 state는 바뀌지 않았다. 이전 후 fixture의 실제 리소스 plan도 `No changes`였다. **이는 기존 기본 기기의 실제 state 이전 완료를 뜻하지 않는다.**

## 실제 이미지 빌드

demo-app `d5c7464`의 앱 소스 그대로 각 서비스의 amd64·arm64 OCI를 한 번 빌드했다. 두 아키텍처 각각 Trivy 0.75.0의 기존 정책(HIGH/CRITICAL, 수정 가능 취약점, 기존 ignorefile)을 통과했다. 이후 통합한 T17 변경분은 demo-app PR 검사에서 다시 검증한다.

| 서비스 | OCI index digest |
|---|---|
| BE | `sha256:14b6634ebab25523bd030b6837619948696e34c6611f79f43d715b3a0ffc8748` |
| FE | `sha256:7c0674039acc76d08db05ca1883154acc8e41bc50010db9bb53e05b9e209bfbb` |

Buildx의 wrapper index를 Trivy에 바로 주면 leaf digest를 찾지 못하는 실제 오류를 확인했다.
검사용 추출 디렉터리의 index만 평탄화해 각각의 leaf digest를 선택하도록 수정했다. 배포할 OCI archive 바이트는 변경하지 않는다.
보고서의 실제 image config digest와 architecture도 archive와 대조한다.
BE archive를 격리된 임시 레지스트리로 Skopeo `--all --preserve-digests` 복사한 뒤 원격 manifest를 읽었다.
두 아키텍처가 함께 발행됐고 원격 index digest가 위 BE digest와 일치했다. hosted Actions 연동 검증은 별도로 남아 있다.

## 2026-10-09 시점의 남은 실기 검증

실제 hosted [검증 실행](https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/demo-app/actions/runs/37924044466)에서
두 아키텍처 검사 → 같은 run artifact 다운로드 → GHCR digest 보존 발행은 통과했다.
첫 배포는 앱 적용 전 Bash 실행 경로의 공백 때문에 실패했다. secondary runner만 공백 없는 고정 경로로 이동하고 같은 등록 ID와 검사 이미지를 유지해 실패한 배포 job만 재실행한다.
installer에도 실제 runner/work 경로 검사와 BOM이 있는 공식 설정 파일 테스트를 추가했다.

- hosted Actions의 같은-run artifact 발행·digest 배포와 test→prod 실제 승격 확인.
- 현재 맥북의 test/prod 검증 데이터 저장, 외부 5초 간격 probe와 잠금/화면 꺼짐 30분, runner 진단 및 재시작 없음 확인.
- 별도 재부팅·로그인 후 10분 내 복구와 데이터 보존 확인.
- 기존 기본 기기의 원본 state 확인·이전·잠금/재부팅 검증.
- Linux 실기 검증은 선택 후속 항목. Linux 컨테이너 자동 테스트를 머신 실기 검증으로 세지 않는다.

실기 검증 워크플로: `onprem-verify.yml`. 잠금/해제 시각은 사람이 별도로 기록해야 한다.
이슈 체크는 해당 변경의 머지와 실제 검증 후 진행한다.


## 2026-10-10 T27 재부팅 복구 후속

범위는 사용자가 선택한 현재 맥북 `secondary`다. 기존 T17 작업, 다른 맥북·AWS·GCP는 변경하지 않는다.
현재 맥북의 10분 잠금 결과를 완료 근거로 유지한다. 두 맥북의 30분 검증으로 확대해 해석하지 않는다.
기존 로컬 문서의 미커밋 수정은 원래 worktree에 보존하고 이번 구현은 별도 T27 브랜치에서 진행했다.

- 선행 앱: main `b8bc6d8e1de8a9a84e574997806777e48c3a2c09`. DB 재연결 수정 `3b0caf7` 포함을 확인했다. 기능을 다시 작성하지 않았다.
- [Actions 38037479505](https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/demo-app/actions/runs/38037479505): 기존 두 아키텍처 빌드·검사·OCI artifact 발행 통과. test와 prod에 동일 BE `sha256:cc5e6e5b4262a73654490c92a29e587e5159ecdf5c03d80a5f2083394a782828`, FE `sha256:eddca0ef02f040e9fd8df0a998d6600ff8df69cec39646bdfb1b4a3bd7e3045d`를 배포했다. 차트는 `2.2.1`로 고정했다.
- test 검사 BE 442건/FE 200건, prod 검사 BE 414건/FE 192건 모두 실패 0. 판단 근거 확인 후 로컬 CLI로 test·prod 승격 완료. prod의 `one-tatchi-bot` 보호 규칙은 사용자가 기존 승인 버튼으로 승인했고 동일 digest 검사는 유지했다.
- 단일 서버 격리 환경의 1.33.4에서 Docker IP `.3 → .5` 변경 시 실제 네트워크 정책 fatal 오류와 반복 종료 5회를 재현했다.
- 같은 서버 이름·인증 파일·볼륨으로 1.33.6을 적용했다. k3d nginx가 예전 IP를 보관하는 별도 문제를 확인해 복구 순서에 해당 프로필의 API 프록시 재시작을 추가했다.
- 이후 실제 IP 변경 `.6 → .7 → .8 → .9` 3회 모두 통과. 매회 약 54초에 Docker/Node IP 일치, 같은 PVC UID·데이터, Service·내부/외부 DNS 통과. Docker 반복 종료 0.
- 1.33.6에서 새 PVC 생성·마운트·읽기·쓰기 통과. 실제 containerd `2.1.5-k3s1.33`, runc `1.3.3`, CoreDNS `1.13.1`, Local Path Provisioner `0.0.32` 확인.
- 실기 Quick Tunnel fixture: test/prod 모두 외부 검증, test 터널 단독 재시작 시 새 URL, tunnel scale 0일 때 이전 test URL 제거, scale 1 후 새 주소 복구를 확인했다. 정적 HTTP fixture의 검사이며 DB 보존 검증과 구분한다.
- 실제 secondary의 정지 상태 볼륨 5개·노드 인증·k3d 시작 파일·컨테이너 설정·Terraform state를 age로 암호화했다. 복구 키는 백업/저장소 밖에 별도로 보관했다.
- 이전 1.33.4 이미지의 `network=none` 복원 클론에서 PVC 3개·test/prod SQL 검증 글·앱 API·인증정보 일치와 백업 이전 Prometheus 데이터 조회를 확인했다. 외부 통신 실패도 확인했다.
- 같은 복원 클론에서 DB를 내려 둔 상태로 BE를 시작했다. health 503/fallback-memory 이후 DB를 올리자 같은 BE 컨테이너가 재시작 0회로 health 200/connected와 기존 SQL 데이터를 반환했다.
- Linux 컨테이너의 저장소 전체 scripts 회귀 검사 통과. 변경 루트 및 클러스터 모듈 Terraform fmt/init/validate 통과. 복구 실패·오래된 URL·이전 부팅·공통 마감시간·볼륨 보존·버전 기록 방지 검사 포함.

이 구현 검증 당시에는 실제 맥북 재부팅·로그인 관측을 별도로 남겼다. 최종 실기 판정은 다음 항목에 기록한다.
백업·원본 설정·상세 런타임 로그는 공개 저장소에 올리지 않는다.


실제 secondary 적용 결과: Docker 이미지 `rancher/k3s:v1.33.6-k3s1`와 Kubernetes `v1.33.6+k3s1` 일치.
원래 Docker 볼륨 5개, test/prod·Prometheus PVC UID 3개, 앱 digest·차트와 양쪽 DB 검증 글/인증정보를 보존했다.
노드 인증 Secret이 `k3s.cattle.io/node-password`로 전환된 뒤 exec kubeconfig 인증과 재등록이 정상이다.
노드 IP 일치, Pod 19개 Ready, ExternalSecret 2개 Ready, 내부/외부 DNS, Metrics Server 및 과거/현재 Prometheus 조회 통과.
교체 후 fatal 로그와 Docker 반복 종료는 0이었다. 일반 터미널에서 설치본 CLI를 호출할 때도 launchd와 같은 관리 PATH를 쓰도록 보완했다.


## 2026-10-10 현재 맥북 재시작 실기 검증 완료

사용자가 현재 `secondary` 맥북의 전원을 종료한 뒤 다시 시작하고 로그인했다.
로그인과 Codex 실행 외에 Docker 수동 실행·복구 명령·앱 재배포를 하지 않았음을 확인했다.
읽기 전용 관측기는 다음 승인 기준을 통과했다.

- 로그인 LaunchAgent 시작부터 600초 이내 자동 복구, 이후 300초 이상 연속 정상 상태. 시간 기준은 실제 로그인 시각의 근사치다.
- 이번 부팅의 복구 성공 기록과 runner의 새 연결 및 GitHub online 확인.
- 실제 Docker IP 변경 후 Kubernetes Node IP 일치, 지정한 K3s 버전 유지.
- test/prod의 기존 PVC·이미지·차트·인증정보 유지 및 SQL과 외부 API 양쪽에서 검증 데이터 확인.
- 재시작으로 바뀐 test/prod Quick Tunnel URL을 자동 갱신하고 새 주소의 화면·API·DB health 확인.
- 안정성 관측 구간의 앱·DB 추가 재시작 없이 운영되며 T17 중앙 지표 수신도 회복.

T17 검증 후 남은 test의 중단된 배포는 재부팅 전에 기존 정상 배포와 정합화했다.
prod·DB·PVC와 T17 중앙 수집 설정의 보존을 확인한 뒤 원래 T27 데이터 기준으로 관측했다.
원본 관측 결과와 사용자 확인, 상세 검증 증거는 로컬 기록으로 보관한다.

이번 결과는 현재 맥북의 재부팅 항목 완료 근거다. 기존 기본 기기의 state 이전이나 Linux 실기 검증까지 완료한 것으로 확대하지 않는다.
DB 장기 불통 시 liveness 분리 문제는 별도 후속 #211로 유지한다.

## 2026-10-10 팀 변경 이후 state 후속 점검

T17의 저장 plan apply 인증 재주입과 관측 설정, T33의 ephemeral/write-only OAuth 입력,
T32의 AWS/onprem DB 연결 계약, T35의 환경별 값 파일을 검토했다.
현재 secondary의 DB·k3d 인증 구조를 되돌리는 변경은 없으며, 관측 인증값도 state에 전달하지 않는 경로를 유지한다.

- secondary의 state·기존 backup/plan·tfvars·관리 설정에 새 저장 plan을 포함해 검사했다. 실제 DB·관리자·T17 관측 비밀값 일치와 알려진 기존 비밀값 저장 필드는 발견되지 않았다. 이 기기는 Tailscale operator를 사용하지 않으므로 해당 실기 검증은 주장하지 않는다.
- 새 전체 plan은 변경 없음이며 원본 state 바이트도 유지됐다. Terraform show에 남은 ephemeral 입력의 빈 기본값/접속 주소는 실제 비밀번호·인증키와 구분했다. 앱 재배포나 Terraform apply는 하지 않았다.
- 현재 state·plan·루트 설정의 암호화 백업을 생성하고 메모리에서 복호화해 모든 파일을 대조했다. 개인키는 백업·저장소 밖에 보관한다. DB 볼륨 변경/복원은 하지 않았다.
- 원래 재부팅 기준의 SQL/API 데이터·PVC·앱 digest·차트·DB 인증정보와 runner online을 다시 확인했다.
- 검사에 JSON 이스케이프·압축 plan 내부·base64 연결 문자열·교체 전 인증정보의 기존 저장 필드 확인을 추가했다. T17 입력 파일은 이전 도구의 삭제 대상에 포함하지 않는다.

기본 맥북에는 접근할 수 없으므로 그 기기의 실제 state 이전 항목은 미완료다.
[실행 절차](t27-state-migration.md)를 준비했으며, 소유자가 실제 이전·변경 없음·데이터 보존을 확인해야 한다.
Linux 실기 검증은 선택 후속으로 남긴다. 이미 통과한 secondary의 잠금/재부팅 증거는 그대로 유지한다.
