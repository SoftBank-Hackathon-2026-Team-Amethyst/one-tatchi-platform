# T27 검증 기록

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

## 남은 실기 검증

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
