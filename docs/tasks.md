# 해야 할 일: 단계별 정리

> 원터치 배포 설계 문서(`plan.html` 11장)의 작업을 **선행 관계 순서대로** 정리한 것이다. 같은 단계 안의 작업은 동시에 진행할 수 있다.

## 읽는 법

- **단계**: 앞 단계의 선행 작업이 끝나야 시작할 수 있다. 같은 단계 안에서는 병렬로 진행한다.
- **우선순위**: `P0` 데모에 꼭 필요 · `P1` 점수에 중요 · `P2` 여유 있으면
- **구조**: 레포는 두 개다(둘 다 public). `one-tatchi-platform`(템플릿: Terraform 모듈, App Chart, 재사용 워크플로, bootstrap, 스킬)과 `demo-app`(대상 레포: 앱 코드와 에이전트 산출물).
- 각 작업은 GitHub 이슈 하나에 대응한다(제목 · 체크리스트 · 완료 기준).

## 작업 규칙

**진행 상황의 기준은 [프로젝트 보드](https://github.com/orgs/SoftBank-Hackathon-2026-Team-Amethyst/projects/1)(이슈)다.** 이 문서는 계획이고, 체크박스와 담당은 보드를 따라 자동으로 바뀐다.

1. 작업 전에 보드나 이 문서에서 **자기 작업**을 찾고, **선행** 작업이 끝났는지 본다.
2. 작업은 브랜치에서 한다(예: `t3-onprem-k3d`). `main`은 보호돼 있어 PR과 CI(`terraform` · `charts` · `iac-scan`) 통과가 필요하다. 리뷰 승인은 필요 없다.
3. 커밋 메시지와 PR 제목 앞에 작업 번호를 붙인다. 예: `[T3] k3d 클러스터 생성 스크립트 추가`. PR 본문에 `Refs #이슈번호`, 마지막 PR이면 `Closes #이슈번호`.
4. **끝낸 할 일은 이슈에서 체크한다**(이슈 화면에서 클릭하거나 `python3 scripts/sync_tasks.py tick T3 2`). 이 문서의 체크박스는 직접 고치지 않는다.
5. 담당을 바꾸려면 이슈의 Assignees를 바꾼다.
6. 그러면 자동으로(`sync-tasks` 워크플로):
   - 체크가 하나라도 생기면 보드 **In progress**, 전부 체크되면 이슈가 닫히고 **Done**
   - 이 문서의 체크박스 · 담당 · 역할 분담이 봇 PR로 갱신된다
   - 보드가 움직이면 Slack 채널에 알린다
7. 계획을 바꿀 때(작업 추가, 할 일 문장 수정 · 추가 · 다른 작업으로 이동, 우선순위)는 이 문서를 고쳐 PR로 올린다. 머지되면 이슈에 반영되고, 이미 한 체크는 유지된다.
8. 작업 번호(T번호)는 바꾸거나 다시 쓰지 않는다. 이슈와 짝을 맞추는 열쇠다. `plan.html`에는 진행 상황을 적지 않는다.

Claude Code는 `/todo-task`, Codex는 `$todo-task`로 이 순서를 따르는 스킬을 쓸 수 있다(`.claude/skills/todo-task`).

## 역할 분담

**원가연** · 플랫폼 코어 (11개, P0 8개)
- `T1` 레포 두 개와 bootstrap (P0)
- `T3` 온프레미스 구현체 (로컬 맥북) (P0)
- `T5` test / prod 분리와 브랜치 흐름 (P0)
- `T20` 템플릿 레포 구성과 릴리스 (P0)
- `T21` 레포 간 참조 검증 (P0)
- `T13` janto / yolo 두 경로로 스킬 정리 (P0)
- `T8` yolo main PR 자동 생성 · 자동 머지 (P0)
- `T34` test · prod DB와 계정 분리 (P1)
- `T35` 환경별 값 파일과 prod 장애 주입 차단 (P0)
- `T36` 장애 훈련 워크플로 (green 확인 · 주입 · 채점) (P1)
- `T37` 장애 훈련 Slack 명령과 Grafana 기록 (P1)

**이소울** · 파이프라인 (7개, P0 3개)
- `T6` 규제 여부에 따른 운영 관문 (P0)
- `T23` 초기 인프라 세팅 (계정 · 권한) (P0)
- `T22` 템플릿 버전 업데이트 흐름 (P1)
- `T2` 도메인과 HTTPS (P0)
- `T26` Slack 버튼으로 머지 · 승인 · 승격 (P1). 담당 필요
- `T38` gcp 승인자용 green 미리보기 (P2)
- `T39` 여러 배포 대상 동시 배포 (P2)

**김형래** · 에이전트 스킬 (4개, P0 3개)
- `T14` yolo 자동 수정 루프 (P0)
- `T15` 브리프 질문 UX (P0)
- `T24` AWS 구현체 (P0)
- `T17` Grafana 통합 (P1)

**배준범** · 배포 대상 · 데모 앱 (3개, P0 2개)
- `T25` 데모 앱 개발 (P0)
- `T11` 검사 3종 추가 (P1)
- `T9` 배포 시간 2분대 단축 (P0)

**배규태** · AI 판단 · 리포트 (5개, P0 1개)
- `T7` AI 승격 · 롤백 판단 (P0)
- `T4` GCP 구현체 (P1)
- `T10` yolo 배포 리포트 (P1)
- `T16` 비용 추정 (예산 분석기) (P1)
- `T12` 배포 실패 AI 원인 진단 (P2)

**전원** · 문서
- `T18` ADR · 용어집 · 문서 갱신 (P1). 영역별 ADR은 각자 작성

**미정**
- `T19` 3분 데모 리허설 (P1). 담당 필요

가장 긴 경로(여기가 밀리면 전체가 밀림): `T23` → `T1` → `T20` → `T24` → `T21` → `T5` → `T7` → `T8` → `T10`

---

## 0단계: 작업 전에 정할 것

| 정할 것 | 영향 받는 작업 | 현재 가정 |
|---|---|---|
| 도메인 이름과 DNS 관리 위치 | T2 | **결정**: 운영 `onetatchi.soulee.dev` / 테스트 `yolo.onetatchi.soulee.dev`. `soulee.dev`(Cloudflare)에서 Route53으로 위임 |
| 온프레미스 데모 머신 | T3 | **결정: 원가연 맥북 (M2 · 16GB, k3d).** 시간이 남으면 리눅스 머신 |
| 두 번째 클라우드 | T4 | GCP |
| yolo의 main PR 생성 · 자동 머지 주체 | T8 | GitHub Actions (ADR 0010) |
| AI 승격 판단 기준값과 관찰 시간 | T7 | 에러율 0%, p95 기준값, 60초 관찰 |
| 규제 대상 판정 기준 | T6, T15 | 개인정보 · 결제 · 금융 데이터를 다루면 `regulated` |
| `yolo-debt` 이슈 처리 기한과 담당 | T10 | 다음 janto 배포 전까지 해소 |
| Grafana 위치 | T17 | AWS 클러스터에 중앙 1개 |
| T19 3분 데모 리허설 담당 | T19 | 미정 |
| ~~레포 공개 여부~~ | T1 | **결정: 두 레포 public** (완료) |

---

## 1단계

선행 작업이 없어 바로 시작할 수 있다.

### [T15] 브리프 질문 UX

**어디에 필요** 스킬이 처음 묻는 질문. 이 답(특히 규제 여부)이 인프라 추천과 운영 승인 여부를 정한다.

**만들 것** 스킬의 질문 단계. 질문 3~5개의 목록과 문구(`references/brief-format.md` 갱신), 답을 `.deploy/brief.md`와 `config.yaml`의 `compliance`로 저장하는 단계, 규제 판정 규칙(어떤 답이면 `regulated`인지).

- **우선순위** P0 · **영역** 스킬 · **담당** 김형래
- **선행** 없음 · **후속** `T16` · **설계 문서** FR-1

**목표** 질문 3~5개로 코드에서 알 수 없는 정보를 받는다.

**할 일**
- [x] 질문 확정: 예상 사용자 수, 월 예산, 규제 여부(개인정보·결제·금융), 배포 대상 선호, 가용성
- [x] 기본값과 건너뛰기
- [x] 답변 → `.deploy/brief.md`, 규제 답변 → `compliance`

**완료 기준** 질문에 답하면 브리프와 compliance 값이 만들어진다.

### [T23] 초기 인프라 세팅 (계정 · 권한)

**어디에 필요** 팀원 각자가 AWS · GCP를 안전하게 쓸 계정과 권한. 모든 클라우드 작업의 출발점.

**만들 것** 팀원별 AWS 계정(IAM Identity Center 또는 IAM 사용자)과 권한 세트, AWS Budgets 경보, GCP 프로젝트와 팀원 IAM 권한, 계정 현황 문서.

- **우선순위** P0 · **영역** 레포 · 인프라 · **담당** 이소울
- **선행** 없음 · **후속** `T1`, `T4` · **설계 문서** 6.6

**목표** 팀이 AWS · GCP를 안전하게 쓸 수 있도록 계정과 권한을 준비한다.

**할 일**
- [x] AWS 루트 계정 정리: MFA 설정, 루트 액세스 키 삭제
- [x] 팀원별 IAM Identity Center 계정 발급: 멤버 계정 `one-tatchi`, 권한 세트 `AdministratorAccess` 4명 · `ReadOnlyAccess` 1명, SCP 가드레일 (`org/`, ADR 0001)
- [x] AWS Budgets로 예산 경보 설정 (월 $200, 크레딧 제외)
- [ ] GCP 프로젝트 생성, 결제 연결, 팀원 IAM 권한 부여 → T4 시작 시로 보류
- [x] 자격증명 공유 규칙: 키 공유 금지, 각자 자기 계정으로 로그인 (`docs/aws-setup.md`)
- [x] 계정 · 권한 현황 문서화 (`docs/aws-setup.md`, `org/README.md`)
- [ ] 팀원 5명 `aws sts get-caller-identity --profile onetatchi` 확인

**완료 기준** 팀원 각자 자기 계정으로 AWS · GCP CLI를 쓸 수 있고, 루트 액세스 키가 없다.

### [T25] 데모 앱 개발

**어디에 필요** 배포할 대상 앱. 에이전트가 분석하고 파이프라인이 배포하는 재료.

**만들 것** demo-app 레포의 앱 코드(`be/`, `fe/`, `db/`, `compose.yaml`)와 테스트 · 린트 설정.

- **우선순위** P0 · **영역** 관측 · 문서 · 데모 · **담당** 배준범
- **선행** 없음 · **후속** `T13` · **설계 문서** 2.1, 10장

**목표** 배포 대상이 될 데모 앱을 demo-app 레포에 둔다.

**할 일**
- [ ] 게시판 CRUD(Next.js + FastAPI + Postgres)를 demo-app 레포에 정리
- [ ] 로컬 실행(docker compose), 테스트 · 린트 통과
- [ ] 헬스체크 엔드포인트(`/health`) 유지
- [ ] 데모 때 바꿀 화면 요소(예: 버전 배지) 준비
- [ ] 배포 산출물(Dockerfile 등)은 넣지 않는다 (에이전트가 만들 몫)

**완료 기준** demo-app에서 로컬로 앱이 뜨고 테스트 · 린트가 통과한다.

### [T18] ADR · 용어집 · 문서 갱신

**어디에 필요** 설계 문서화(심사 20점). 왜 이렇게 정했는지를 남긴다.

**만들 것** `docs/adr/`의 ADR 문서(레포 분리, janto/yolo, 운영 관문, 자동 수정, 온프레미스), `CONTEXT.md` 용어 갱신.

- **우선순위** P1 · **영역** 관측 · 문서 · 데모 · **담당** 전원
- **선행** 없음 · **후속** 없음 · **설계 문서** 팀 개발

**목표** 결정 사항이 문서로 남는다.

**할 일**
- [ ] ADR: 레포 분리와 태그 참조, janto/yolo 경로, 규제 여부 운영 관문, 자동 수정 루프, 온프레미스 정의
- [ ] `CONTEXT.md` 용어 갱신(template_version, platform 레포 등)
- [ ] 본 문서 · 한 페이지 요약 · 아키텍처 그림을 두 레포 구조로 갱신

**완료 기준** 새 결정마다 ADR이 있다.

---

## 2단계

앞 단계의 선행 작업이 끝나면 아래 작업을 동시에 진행한다.

### [T1] 레포 두 개와 bootstrap

**어디에 필요** GitHub Actions가 AWS에 들어갈 권한(OIDC)과 Terraform 상태 저장소를 만든다. 이게 없으면 어떤 배포도 시작할 수 없다.

**만들 것** `bootstrap/` Terraform 실행 결과(S3 state 버킷, 감사 로그 버킷, GitHub OIDC 역할 2개), demo-app 레포 설정(Variables 5개, `prod` environment, 브랜치 보호).

- **우선순위** P0 · **영역** 레포 · 인프라 · **담당** 원가연
- **선행** `T23` · **후속** `T20`, `T21` · **설계 문서** 6.1, 6.6

**목표** one-tatchi-platform와 demo-app 레포가 준비되고, demo-app에서 GHA가 장기 키 없이 AWS에 접근한다.

**할 일**
- [x] `one-tatchi-platform` · `demo-app` 레포 생성, public 전환, 팀원 admin 권한 부여
- [x] Actions 설정: 외부 fork PR 워크플로는 승인 필수, self-hosted runner는 PR job에 쓰지 않음 (두 레포 `all_external_contributors`. 재사용 워크플로는 모두 `ubuntu-latest`, `onprem` 라벨 runner는 push job에서만 쓴다)
- [x] demo-app의 OIDC sub 접두사 조회(`gh api repos/<owner>/demo-app/actions/oidc/customization/sub`) → bootstrap 변수 (`repo:SoftBank-Hackathon-2026-Team-Amethyst@338407242/demo-app@1408704749`, bootstrap 기본값과 일치)
- [x] 로컬에서 `bootstrap` apply(state 버킷, 감사 로그, OIDC 역할) → state를 S3로 이전 (`one-tatchi-993371732872-tfstate/bootstrap.tfstate`, 이전 후 plan 변경 없음)
- [x] OIDC 역할 신뢰 조건에 `job_workflow_ref`(platform 재사용 워크플로만 허용) 추가 검토 (`modules/ci_identity/aws`에 `allowed_workflow_refs` 추가(기본 빈 목록 = 제한 없음), bootstrap에서 platform 워크플로 `@refs/tags/v*` · `@refs/heads/main`만 허용. 적용 후 demo-app plan · apply 통과)
- [x] demo-app에 GitHub Variables 등록, environment `prod`(required reviewers) 생성 (Variables 5개 등록. environment `test` · `prod`(팀원 5명 중 1명 승인, `main`만 배포) · `destroy`)
- [x] 브랜치 보호: `main`은 PR 필수 · auto-merge 허용 (demo-app ruleset `main`: PR 필수 · 삭제 · force push 금지, auto-merge · 머지 후 브랜치 삭제 허용. 필수 검사 지정은 T11로 넘김)

**완료 기준** demo-app의 PR에서 plan이, main 머지에서 apply가 돈다.

### [T16] 비용 추정 (예산 분석기)

**어디에 필요** 분석 보고서에 "이 구성이면 월 얼마"를 붙인다. 추천 인프라를 고를 때와 비용 효율성 심사에 쓴다.

**만들 것** 가격 조회 스크립트(`skills/deploy-analyze/scripts/price.py`), 비용 계산 규칙, `references/analyzers/budget.md` 수정, 분석 보고서의 비용 표.

- **우선순위** P1 · **영역** 스킬 · **담당** 배규태
- **선행** `T15` · **후속** 없음 · **설계 문서** FR-1

**목표** 분석 보고서에 구성별 월 비용이 나온다.

**할 일**
- [x] 가격 조회 스크립트(예: `skills/deploy-analyze/scripts/price.py`): AWS Pricing API · GCP Cloud Billing Catalog API로 리전별 단가 조회 → JSON
- [x] 계산 규칙: 추천 구성(트래픽 분석기 결과)을 템플릿 자원 목록으로 바꿔 `단가 × 730시간`, 고정비와 변동비 구분
- [x] `references/analyzers/budget.md` 수정: "알고 있는 가격으로 추정" 대신 조회 도구 사용, 단일 배포 대상별(aws / gcp / onprem) 비교 표, 예산 초과 시 절감안
- [x] 분석 보고서 요약에 월 예상 비용 연결 (janto 리뷰 지점 1에서 표시)

**완료 기준** demo-app 분석 보고서에 API로 조회한 단가 기반 비용 표(조회 시각 포함)가 나오고, 예산을 넘으면 경고와 절감안이 뜬다.

---

## 3단계

앞 단계의 선행 작업이 끝나면 아래 작업을 동시에 진행한다.

### [T20] 템플릿 레포 구성과 릴리스

**어디에 필요** Terraform 모듈 · App Chart · 공통 워크플로를 한곳에 두고 태그로 배포한다. demo-app이 참조할 원본.

**만들 것** `one-tatchi-platform`의 모듈 계약(`variables.tf` · `outputs.tf`), App Chart, 재사용 워크플로 `checks.yml` · `infra.yml` · `deploy.yml`, 태그 시 차트를 GHCR에 올리는 릴리스 워크플로, 첫 태그 `v1.0.0`. `report.yml`은 T10, 배포 스킬은 T13에서 만든다.

- **우선순위** P0 · **영역** 레포 · 인프라 · **담당** 원가연
- **선행** `T1` · **후속** `T3`, `T4`, `T11`, `T21`, `T24` · **설계 문서** 6.1

**목표** one-tatchi-platform에 기본 템플릿이 모이고, 태그 하나로 세 가지 참조 대상이 함께 배포된다.

**할 일**
- [x] `modules/`: 기능 8개(secret 포함) 이동, aws는 사전 검증한 코드. 계약 정리 · 다듬기는 T24
- [x] `charts/`: App Chart · service-base · platform-config, 태그 시 `helm push`로 `oci://ghcr.io/<org>/charts`에 배포(`release.yml`)
- [x] 첫 태그 `v1.0.0` 달기 (`release.yml` 성공, 차트 3개 GHCR에 올라감)
- [x] GHCR 차트 패키지 3개 public 전환 (org 설정에서 public 패키지 허용 후 웹 UI로 전환, 로그인 없이 `helm pull` 확인)
- [x] `.github/workflows/`: 재사용 워크플로 `checks.yml` · `infra.yml` · `deploy.yml`(`on: workflow_call`), 레포 자체 `ci.yml` · `release.yml` (`deploy.yml`은 AWS 전용으로 옮겼다. 대상 입력은 T5에서 추가)
- [x] `bootstrap/` 이동
- [x] 릴리스 규칙: 시맨틱 버전 태그(v1.2.0), 변경 기록(`CHANGELOG.md`)
- [x] 태그 보호: `v*.*.*` 생성 · 수정 · 삭제는 관리자만 (룰셋 `release-tags`)
- [x] main 보호: PR 필수 · 필수 검사(`terraform` · `charts` · `iac-scan`), 리뷰 승인 0명 (룰셋 `main`)

**완료 기준** v1.0.0 태그를 달면 차트가 GHCR에 올라가고, 재사용 워크플로를 외부 레포에서 호출할 수 있다.


---

## 4단계

앞 단계의 선행 작업이 끝나면 아래 작업을 동시에 진행한다.

### [T3] 온프레미스 구현체 (로컬 맥북)

**어디에 필요** 테마의 "온프레미스(로컬)". 같은 앱이 내 노트북에서도 뜬다는 이식성 장면에 쓴다.

**만들 것** 맥북(M2 · 16GB)에 k3d(k3s) · Cloudflare Tunnel을 띄우고, 온프레미스 Terraform 모듈과 demo-app의 `infra/envs/onprem` 루트로 test 환경을 구성해 같은 App Chart로 앱을 배포한다. runner를 통한 자동 배포는 T5, 온프레미스 관측은 T17에서 다룬다.

- **우선순위** P0 · **영역** 레포 · 인프라 · **담당** 원가연
- **선행** `T20` · **후속** `T17`, `T19`, `T27`, `T29` · **설계 문서** 6.4

**목표** 같은 App Chart로 로컬 맥북의 게시판이 Cloudflare Quick Tunnel HTTPS 주소에서 동작한다.

**할 일**
- [x] k3d(또는 OrbStack)로 k3s 클러스터 생성, Docker VM 메모리 6~8GB
- [x] k3s 설치, Cloudflare Tunnel → HTTPS 주소 (클러스터 안 cloudflared Quick Tunnel `*.trycloudflare.com`. 고정 도메인은 쓰지 않기로 함, 필요하면 `tunnel.token_secret`으로 Named Tunnel 전환. Traefik 대신 터널이 Service로 바로 연결)
- [x] platform의 온프레미스 cluster · cluster_addons(터널 · secrets) · database · registry 모듈을 demo-app `infra/envs/onprem`에서 태그로 참조해 구성
- [x] App Chart로 demo-app의 be · fe를 맥북 test에 배포하고 터널 HTTPS 주소에서 화면 · 게시판 API · DB 연결 확인

**완료 기준** 맥북 test 환경의 게시판 화면과 API가 Cloudflare Tunnel HTTPS 주소에서 동작하고 DB에 연결된다.


### [T27] 온프레미스 보완 (재부팅 · 이미지 · 비밀값)

**어디에 필요** T3로 맥북 데모는 뜨지만, 재부팅하면 사람이 손대야 하고 일부 단계가 실패를 숨긴다. 데모 당일 맥북 하나로 test · prod를 안정적으로 보여 주려면 필요하다.

**만들 것** 맥북 자동 시작 설정(Docker Desktop · runner · k3d), 재부팅 복구 절차, onprem 배포 실패 처리, 멀티 아키텍처 이미지, 로컬 state의 비밀값 정리.

- **우선순위** P1 · **영역** 레포 · 인프라 · **담당** 김형래
- **선행** `T3` · **후속** `T19`, `T33` · **설계 문서** 6.4

**목표** 전원·네트워크 연결과 열린 덮개 상태에서 화면 잠금·꺼짐 중에도 test · prod가 계속 동작한다. 재부팅 뒤 로그인 1회 후 자동 복구하며, onprem 배포가 실패를 숨기지 않는다.

**할 일**
- [x] launchd `caffeinate -s`로 AC 전원에서 잠금 중 연속 실행. Docker 로그인 시작, 기기별 runner·클러스터·state 분리와 현재 secondary 맥북의 10분 잠금 검증 (다른 맥북 검증은 후속 범위)
- [x] 재부팅·로그인 후 추가 명령 없이 10분 내 자동 복구와 데이터 보존 확인: k3d 노드 · self-hosted runner(launchd) · cloudflared가 다시 뜨고, 바뀐 터널 주소를 확인하는 방법을 README에
- [x] 공개 서비스와 환경별 현재 터널을 대조하고 없음·대상 불일치·조회 오류·URL 누락 시 배포 실패. 내부 BE는 외부 주소가 없어도 정상
- [x] checks에서 `linux/amd64` + `linux/arm64`를 한 번 빌드·각각 검사. 같은 run의 OCI artifact와 digest로 배포하고 test에서 승격한 동일 digest만 prod에 반영
- [ ] ephemeral 입력·write-only Secret·exec 인증으로 DB 비밀번호와 k3d 관리자 인증정보의 state 저장 제거. 기존 비밀번호·데이터를 보존하며 암호화 복구 백업 후 state·plan·backup 이전 검증 (NFR-2)
- [x] database: 기존 StatefulSet·PVC·접속 규격 유지, Helm Postgres로 교체하지 않는 결정과 이유를 ADR에 기록
- [ ] (시간이 남으면) 리눅스 머신에서 같은 절차 확인

**완료 기준** 현재 secondary 맥북의 승인된 10분 잠금 검증에서 test · prod와 runner가 중단·재시작 없이 동작한다. 별도 재부팅·로그인 뒤 추가 명령 없이 10분 내 복구되고 이후 5분 안정 상태와 SQL·외부 API의 실제 데이터 보존을 확인한다. runner online과 검증된 최신 터널 URL의 외부 접속을 모두 요구한다. 터널이 없을 때 배포가 실패한다. 다른 맥북·Linux 실기 검증은 후속 범위다.
### [T24] AWS 구현체

**어디에 필요** AWS에 실제로 VPC · EKS · RDS 등을 만드는 Terraform 코드. 첫 배포 대상(Happy Path).

**만들 것** `modules/*/aws` Terraform 구현체 7개(사전 검증 코드 이식 + 해결한 문제 반영)와 demo-app용 `infra/envs/aws` 예시 루트.

- **우선순위** P0 · **영역** 레포 · 인프라 · **담당** 김형래
- **선행** `T20` · **후속** `T21`, `T28`, `T29` · **설계 문서** 6.4

**목표** one-tatchi-platform의 `modules/*/aws`를 사전 검증한 코드 기준으로 완성한다.

**할 일**
- [x] network · cluster · cluster_addons · registry · database · observability · ci_identity의 aws 구현 이식
- [x] 사전 검증에서 해결한 문제 반영: 애드온 설치 순서, LB Controller Service webhook 끄기, Helm `replace`, DB 보안 그룹 `count`, OIDC immutable subject
- [x] 출력값 이름이 벤더 중립인지 확인 (계약 준수)
- [x] demo-app용 `infra/envs/aws` 루트 예시 작성
- [x] `terraform validate`, Trivy IaC 검사 통과

**완료 기준** demo-app의 `infra/envs/aws`에서 원격 모듈로 plan · apply가 성공한다.

### [T4] GCP 구현체

**어디에 필요** 테마의 "Google Cloud, AWS". AWS 말고 다른 클라우드로도 같은 방식으로 배포된다는 증거.

**만들 것** `modules/*/gcp` Terraform 구현체(GKE, Cloud SQL, Artifact Registry, Workload Identity Federation)와 demo-app의 `infra/envs/gcp` 루트.

- **우선순위** P1 · **영역** 레포 · 인프라 · **담당** 배규태
- **선행** `T20`, `T23` · **후속** 없음 · **설계 문서** 6.4

**목표** `envs/gcp` 루트로 같은 App Chart가 GCP에서 뜬다.

**할 일**
- [x] GCP 프로젝트와 결제 연결
- [x] platform의 `ci_identity/gcp`(Workload Identity Federation, demo-app 신뢰)
- [x] network · cluster(GKE) · registry(Artifact Registry) · database(Cloud SQL) · secrets · observability 구현
- [x] 출력값 이름이 aws 구현체와 같은지 확인
- [x] demo-app에 `infra/envs/gcp` 루트 추가, 배포 확인

**완료 기준** AWS와 같은 App Chart · 같은 값 파일로 GCP 배포가 성공한다.

### [T11] 검사 3종 추가

**어디에 필요** 기본 검사에 더해 이미지 취약점 · 시크릿 유출 · 라이선스를 막는다. 컴플라이언스 점수용.

**만들 것** `checks.yml`에 이미지 Trivy · gitleaks · 라이선스 검사 step 추가, 예외 사유를 적는 파일.

- **우선순위** P1 · **영역** 파이프라인 (platform 재사용 워크플로) · **담당** 배준범
- **선행** `T20` · **후속** 없음 · **설계 문서** FR-3

**목표** 이미지 취약점, 시크릿 유출, 라이선스를 검사한다.

**할 일**
- [x] 재사용 `checks.yml`에 이미지 Trivy, gitleaks, 라이선스 검사 추가
- [x] 차단 기준: HIGH 이상 차단, 나머지는 리포트로. 예외는 사유와 함께 파일로
- [ ] demo-app `main` ruleset에 필수 검사 지정: 매 PR마다 도는 검사(`checks.yml` 호출 job)를 required status check로 건다. `infra`는 infra 경로 변경에만 돌아 필수로 걸면 다른 PR이 막힌다 (T1에서 넘어옴)

**완료 기준** 시크릿을 커밋하면 검사가 실패한다.

---

## 5단계

앞 단계의 선행 작업이 끝나면 아래 작업을 동시에 진행한다.

### [T21] 레포 간 참조 검증

**어디에 필요** 레포를 나눈 구조가 실제로 동작하는지 작은 예제로 먼저 확인한다. 막히면 뒤 작업이 전부 막힌다.

**만들 것** demo-app에 세 가지 참조(워크플로 `uses@`, 모듈 `source ?ref=`, OCI 차트)만 쓰는 hello 배포 설정과, 동작 결과 · 함정을 적은 기록.

- **우선순위** P0 · **영역** 레포 · 인프라 · **담당** 원가연
- **선행** `T1`, `T20`, `T24` · **후속** `T5`, `T13`, `T22` · **설계 문서** 6.1

**목표** 세 가지 참조가 실제로 동작하는지 작은 예제로 먼저 확인한다.

**할 일**
- [x] demo-app에서 `uses: <org>/one-tatchi-platform/.github/workflows/deploy.yml@v1.0.0` 호출 (진행 중: 재사용 워크플로 호출은 `infra.yml@v1`로 확인(PR plan · main apply). `deploy.yml`은 EKS 클러스터가 있어야 해서 T24 이후, 또는 맥북 self-hosted runner(T3)로 onprem 배포 경로를 만든 뒤)
- [x] Terraform `source = "git::…?ref=v1.0.0"`로 원격 모듈 `init` · `plan` 성공 (`v1.1.0`, demo-app `infra/envs/onprem`. 맥북 state를 옮긴 뒤 plan 변경 없음)
- [x] `helm upgrade … oci://ghcr.io/<org>/charts/app --version 1.0.0` 로 hello 앱 배포 (`1.1.0`, 로그인 없이 pull, 맥북 test에 demo-app be · fe)
- [x] 확인할 함정: GHCR 패키지 공개 여부, 재사용 워크플로 안에서 템플릿 파일 checkout, OIDC가 demo-app 기준으로 발급되는지 (+ Helm 4 server-side apply · `--wait` 문제를 찾아 `deploy.yml`에 `--server-side=false`, Helm 버전 고정)
- [x] 결과와 함정을 6.1 표에 기록

**완료 기준** demo-app 레포에서 세 참조만으로 hello 앱이 test에 배포된다.

### [T17] Grafana 통합

**어디에 필요** AWS · 온프레미스 · GCP 지표를 한 화면에서 본다. AI 판단의 입력이자 데모 화면.

**만들 것** Grafana 데이터 소스 설정(CloudWatch, Prometheus, Cloud Monitoring)과 "Deploy Overview" 대시보드 JSON.

- **우선순위** P1 · **영역** 관측 · 문서 · 데모 · **담당** 김형래
- **선행** `T3` · **후속** 없음 · **설계 문서** 5.2

**목표** 배포 대상별 지표를 Grafana 한 곳에서 본다.

**할 일**
- [x] 중앙 Grafana에 CloudWatch, Prometheus(온프레미스), Cloud Monitoring 연결
- [x] 대시보드: 서비스별 요청 · 에러율 · 응답시간 · 리소스
- [x] AI 판단 job의 원본 metrics.json · 관찰 창 · 실행 정보를 그대로 표시하고 실제 사용자 트래픽과 구분

**완료 기준** 한 대시보드에서 AWS와 온프레미스 지표가 함께 보인다.

---

## 6단계

앞 단계의 선행 작업이 끝나면 아래 작업을 동시에 진행한다.

### [T5] test / prod 분리와 브랜치 흐름

**어디에 필요** yolo는 test로, janto·운영은 prod로 가는 배포 흐름의 뼈대. 원터치(테스트)와 투터치(운영)를 나누는 곳.

**만들 것** 재사용 워크플로 `deploy.yml`(대상 · 환경 입력, prod environment 연결), test · prod 네임스페이스, demo-app 호출부 트리거(`yolo/**` → test, `main` → test 후 prod).

- **우선순위** P0 · **영역** 파이프라인 (platform 재사용 워크플로) · **담당** 원가연
- **선행** `T21` · **후속** `T2`, `T6`, `T7`, `T9`, `T26` · **설계 문서** 6.2, FR-4·5

**목표** `yolo/*` push는 test로, `main` 머지는 test → prod로 간다.

**할 일**
- [x] 네임스페이스 `test`, `prod` (service-base 차트 확장)
- [x] demo-app 호출부 트리거: `push: yolo/**` → test, `push: main` → test 후 prod, `pull_request` → 검사·plan
- [x] 재사용 `deploy.yml`에 대상 · 환경 입력, prod job에 environment 연결
- [x] test에서 검증한 같은 이미지를 prod에 사용(rebase 머지 또는 PR head SHA 조회)
- [x] 환경별 `concurrency`, 테스트 슬롯 1개
- [x] 온프레미스 runner에서 GHCR 차트·이미지를 받아 test 배포하는 경로 확인

**완료 기준** yolo push는 test만, main 머지는 test → prod로 간다.

### [T13] janto / yolo 두 경로로 스킬 정리

**어디에 필요** 사용자가 실제로 실행하는 진입점(`/janto-deploy`, `/yolo-deploy`). 앱을 분석해 배포 파일을 만든다.

**만들 것** `skills/`의 `/janto-deploy` · `/yolo-deploy` 스킬 문서(SKILL.md)와 산출물 생성 규칙(Dockerfile, values, tfvars, `config.yaml`, `smoke.yaml`, 워크플로 호출부).

- **우선순위** P0 · **영역** 스킬 · **담당** 원가연
- **선행** `T21`, `T25` · **후속** `T14` · **설계 문서** 6.1, 6.3

**목표** 두 스킬이 demo-app에 PR 또는 `yolo/*` 브랜치를 만든다. 스킬은 직접 apply하지 않는다.

**할 일**
- [x] 기존 배포 스킬을 platform의 `skills/`로 이동 (사전 검증 레포의 7개 중 6개. `deploy-relocate`는 비목표라 제외. `deploy-analyze`는 T15 브리프 스킬 위에 분석기를 더함)
- [x] platform의 `skills/`를 새 계약에 맞게 수정: 로컬 자격증명으로 apply하는 단계 제거 (release · rollback은 `rollout.yml` 요청으로 대체)
- [x] `/janto-deploy`: 리뷰 지점 1 → 기능 브랜치 + main PR
- [x] `/yolo-deploy`: `yolo/<기능>` push
- [x] 산출물 생성(6.3 표): Dockerfile, 값 파일, `infra/envs/<대상>`(원격 모듈 참조 + tfvars), `.deploy/config.yaml`(`template_version` 포함), `.deploy/smoke.yaml`(API 분석으로 smoke 요청 목록), 재사용 워크플로 호출부
- [x] `.deploy/`에 배포 기록 (`.deploy/log/<시각>-<스킬>.md`, 브리프 · 분석 · 보고서도 커밋)

**완료 기준** demo-app에 두 스킬을 실행하면 PR과 `yolo/*` 브랜치가 생기고, 템플릿은 태그로 참조된다.

### [T22] 템플릿 버전 업데이트 흐름

**어디에 필요** 템플릿이 바뀌면 demo-app이 새 버전을 쓰도록 PR을 자동으로 올린다.

**만들 것** 템플릿에 새 태그가 생기면 demo-app에 버전 업데이트 PR을 여는 설정(Renovate 또는 릴리스 워크플로).

- **우선순위** P1 · **영역** 파이프라인 (platform 재사용 워크플로) · **담당** 이소울
- **선행** `T21` · **후속** 없음 · **설계 문서** 6.1

**목표** platform에 새 태그가 생기면 demo-app에 버전을 올리는 PR이 자동으로 열린다.

**할 일**
- [x] Renovate 또는 platform 릴리스 워크플로로 demo-app에 PR 생성 → 재사용 `template-update.yml` + `release.yml` 알림으로 구현, GitHub App 설정 후 v1.2.0으로 확인 필요
- [x] `template_version`, 모듈 `ref`, `uses@`, 차트 버전을 한 번에 갱신 (`scripts/bump-template-version.sh`, 테스트 `scripts/tests/run.sh`)
- [x] PR은 janto 경로로 리뷰(템플릿 변경 내역 첨부)

**완료 기준** v1.2.0 태그 후 demo-app에 버전 업데이트 PR이 자동으로 생긴다. (v1.1.0은 이 흐름이 들어가기 전에 나갔다)

---

## 7단계

앞 단계의 선행 작업이 끝나면 아래 작업을 동시에 진행한다.

### [T2] 도메인과 HTTPS

**어디에 필요** 심사 기준 "누구나 접근". 데모에서 고정 주소(`https://도메인`, `https://yolo.도메인`)로 서비스를 보여 줄 때 필요하다.

**만들 것** 도메인 1개, DNS 호스티드 존, 와일드카드 인증서(ACM), App Chart Ingress의 `host` 값, ALB HTTPS 리스너.

- **우선순위** P0 · **영역** 레포 · 인프라 · **담당** 이소울
- **선행** `T5` · **후속** `T19` · **설계 문서** FR-10, 6.2

**목표** 운영은 `https://<도메인>`, 테스트는 `https://yolo.<도메인>`으로 누구나 접속한다.

**할 일**
- [x] 도메인 구매, DNS 관리 위치 결정(Route53 또는 외부) → 구매 없이 `soulee.dev`(Cloudflare)의 하위 도메인 `onetatchi.soulee.dev`를 Route53 존으로 위임 (`bootstrap/dns.tf`, `modules/dns/aws`)
- [x] 와일드카드 인증서(ACM `*.<도메인>`) → `onetatchi.soulee.dev` + `*.onetatchi.soulee.dev`, 서울 리전, DNS 검증 완료
- [x] App Chart(platform) Ingress에 `host` 값 추가 (`ingress.host`, 비우면 기존 HTTP 동작 그대로)
- [x] ALB HTTPS 리스너와 HTTP → HTTPS 리다이렉트 (진행 중: 차트 annotation 반영, 실제 ALB 확인은 클러스터(T24) · T5 이후)
- [x] (선택) external-dns 애드온으로 DNS 레코드 자동 생성 (진행 중: `cluster_addons/aws`에 추가, `infra/envs/aws`에서 `dns_zone_id` 연결은 T24와 조율)
- [x] `deploy.yml`에 환경별 `host` 입력(`--set ingress.host`) 추가 — T5(원가연)와 조율

**완료 기준** 두 주소가 HTTPS로 열리고 각각 test · prod로 연결된다.

### [T6] 규제 여부에 따른 운영 관문

**어디에 필요** 금융 스토리의 핵심. 규제 대상이면 yolo여도 운영 앞에서 사람 승인을 강제한다.

**만들 것** `.deploy/config.yaml`의 `compliance` 스키마, 재사용 워크플로의 운영 승인 분기, config를 보호하는 CODEOWNERS와 경로 검사.

- **우선순위** P0 · **영역** 파이프라인 (platform 재사용 워크플로) · **담당** 이소울
- **선행** `T5` · **후속** `T26` · **설계 문서** 6.6, FR-5

**목표** 같은 yolo 배포가 `compliance` 값에 따라 승인 대기 또는 자동 반영으로 갈린다.

**할 일**
- [x] `.deploy/config.yaml` 스키마(`compliance: regulated | none`, `template_version`)
- [x] 재사용 워크플로가 config를 읽어 승인 environment 분기
- [x] demo-app에서 config 보호: CODEOWNERS, AI 커밋이 바꾸면 검사 실패
- [x] 값을 바꾸는 PR은 사람 리뷰 필수

**완료 기준** regulated면 승인 버튼이 뜨고, none이면 자동으로 prod까지 간다.

### [T7] AI 승격 · 롤백 판단

**어디에 필요** 배포 후 지표를 보고 넘길지 되돌릴지 AI가 정한다. "배포 후 모니터링까지 원터치"가 되는 부분.

**만들 것** 재사용 워크플로의 승격 판단 job: smoke 요청 실행 → 지표 조회 → Claude API 호출(`{decision, reason}`) → `kubectl argo rollouts promote` 또는 `abort`.

- **우선순위** P0 · **영역** 파이프라인 (platform 재사용 워크플로) · **담당** 배규태
- **선행** `T5` · **후속** `T8`, `T12`, `T28` · **설계 문서** 6.5, FR-7

**목표** green의 지표를 보고 promote 또는 abort를 정하고 근거를 남긴다.

**할 일**
- [x] 관찰 창 동안 preview Service에 port-forward로 smoke 요청 실행 (`.deploy/smoke.json` + GET 반복, ADR 0003). green은 승격 전 사용자 트래픽이 없으므로 이게 판단 근거가 된다
- [x] 관찰 창(기본 30초, 입력 `window-seconds`) 동안 smoke 결과 · 에러율 · p95 · 재시작 · 헬스체크 조회
- [x] 판단 기준값 정의(12장 미결정 2번). 기본값과 근거는 `.github/actions/promote-judge/README.md`
- [x] LLM 호출(Claude API, 모델 `claude-sonnet-5-5`) → `{decision, reason}` JSON, API 키는 demo-app Secret → `secrets: inherit`
- [x] `kubectl argo rollouts promote / abort`. yolo는 자동, janto는 AI 판단을 알림에 남기고 사람이 Slack 버튼(`rollout.yml`)으로 실행
- [x] 호출 실패 시 안전한 기본값(abort), 규칙 판정에 거부권(ADR 0004)

**완료 기준** 정상 버전은 promote, 일부러 500을 내는 버전은 abort된다.

### [T9] 배포 시간 2분대 단축

**어디에 필요** 데모가 3분이다. 배포가 그 안에 끝나야 라이브로 보여 줄 수 있다.

**만들 것** 워크플로 최적화: BE · FE 병렬 matrix, buildx GHA 캐시, 의존성 캐시. 단계별 소요 시간 측정 기록.

- **우선순위** P0 · **영역** 파이프라인 (platform 재사용 워크플로) · **담당** 배준범, 원가연
- **선행** `T5` · **후속** `T19` · **설계 문서** NFR-1

**목표** yolo push부터 test 반영까지 2분대.

**할 일**
- [x] 단계별 소요 시간 측정
- [ ] BE · FE 병렬(matrix), 검사 job 병렬
- [x] `docker buildx` + GHA 캐시, 베이스 이미지 미리 빌드, pnpm · uv 캐시
- [ ] 원격 모듈 · OCI 차트 다운로드 시간 확인(캐시)

**완료 기준** yolo push → test 반영이 2분대로 측정된다.

### [T14] yolo 자동 수정 루프

**어디에 필요** yolo에서 검사가 실패해도 사람 없이 AI가 고쳐서 다시 올린다.

**만들 것** `/yolo-deploy`의 수정 루프: `gh run watch`로 대기 → 실패 로그 수집 → 허용 경로만 수정 → 재push(최대 3회) → 실패하면 보고.

- **우선순위** P0 · **영역** 스킬 · **담당** 김형래
- **선행** `T13` · **후속** 없음 · **설계 문서** 6.3, FR-11

**목표** 검사 실패를 AI가 최대 3회까지 고쳐 통과시킨다.

**할 일**
- [x] `gh run watch`로 대기, `gh run view --log-failed`로 실패 로그 수집
- [x] 수정 허용: 앱 코드, Dockerfile, 값 파일. 템플릿은 다른 레포라 애초에 수정 불가
- [x] demo-app 안의 금지 경로(테스트, 워크플로 호출부, config의 compliance)를 건드리면 중단
- [x] 최대 3회, 실패 시 정리해 보고

**완료 기준** 일부러 깨뜨린 린트 · 테스트를 AI가 고쳐 통과시킨다.

---

## 8단계

앞 단계의 선행 작업이 끝나면 아래 작업을 동시에 진행한다.

### [T8] yolo main PR 자동 생성 · 자동 머지

**어디에 필요** yolo가 test 검증 후 사람 손 없이 main까지 가게 한다. yolo가 진짜 yolo가 되는 부분.

**만들 것** yolo가 test 승격 후 `main` PR을 만들고 auto-merge를 거는 단계(GHA job 또는 스킬)와 GitHub App 토큰.

- **우선순위** P0 · **영역** 파이프라인 (platform 재사용 워크플로) · **담당** 원가연
- **선행** `T7` · **후속** `T10` · **설계 문서** 6.1

**목표** test 승격 후 사람 개입 없이 `main`에 머지된다.

**할 일**
- [x] GitHub Actions가 test 실제 승격 확인 뒤 main PR을 생성한다 (ADR 0010)
- [x] GHA라면 GitHub App 토큰(기본 토큰으로 만든 PR은 워크플로를 실행하지 않음)
- [x] `gh pr create` + `gh pr merge --auto --rebase`
- [x] PR 본문에 yolo 배포 리포트, 라벨 `yolo`

**완료 기준** yolo 배포가 test 승격 후 자동으로 main에 머지된다.

### [T19] 3분 데모 리허설

**어디에 필요** 3분 라이브 데모를 실패 없이 끝내기 위한 연습.

**만들 것** 데모 사전 점검 체크리스트 문서와 리허설 2회 기록(걸린 시간, 문제점).

- **우선순위** P1 · **영역** 관측 · 문서 · 데모 · **담당** 미정
- **선행** `T2`, `T3`, `T9`, `T26`, `T28` · **후속** 없음 · **설계 문서** 10장

**목표** 3분 안에 라이브 데모가 끝난다.

**할 일**
- [ ] 사전 점검: 클러스터, 도메인, 맥북 k3d, 터널 주소, runner, GHCR 접근
- [ ] 데모용 HTML 변경 준비
- [ ] 3분 타이머로 2회 이상
- [ ] 실패 대비: 직전 상태로 되돌리는 방법

**완료 기준** 리허설 2회 연속 3분 안에 성공한다.

### [T12] 배포 실패 AI 원인 진단

**어디에 필요** 배포가 실패하면 AI가 원인을 요약해 준다. 있으면 좋은 부가 기능.

**만들 것** 배포가 실패하면 실패 로그를 Claude API로 요약해 PR 코멘트로 다는 job.

- **우선순위** P2 · **영역** 파이프라인 (platform 재사용 워크플로) · **담당** 배규태
- **선행** `T7` · **후속** 없음 · **설계 문서** -

**목표** 배포 단계가 실패하면 AI가 원인을 요약한다.

**할 일**
- [x] 실패 로그 수집 → LLM 원인 요약 → PR 코멘트 또는 이슈
- [x] (선택) 수정 PR 제안 — 하지 않기로 함: 요약의 확인 · 조치에 고칠 곳만 적고, 코드 수정은 T14 수정 루프와 사람 리뷰가 맡는다

**완료 기준** 배포 실패 시 원인 요약이 자동으로 달린다.

### [T26] Slack 버튼으로 머지 · 승인 · 승격

**어디에 필요** 승인자가 GitHub에 들어가지 않고 Slack 알림의 버튼만 눌러 PR 머지 → 테스트 배포 → 승격 → 운영 승인까지 진행한다. "투터치"를 데모에서 보여 주는 부분.

**만들 것** platform 레포의 `slack-bot/`(기존 봇 이식), PR 머지 버튼, 운영 승인 · 거절 버튼(GitHub App 승인 규칙), 단계별 알림 메시지.

- **우선순위** P1 · **영역** 파이프라인 (platform 재사용 워크플로) · **담당** 이소울
- **선행** `T5`, `T6` · **후속** `T19` · **설계 문서** 6.2, 6.6

**목표** janto 배포의 사람 조작(머지 · 승격 · 운영 승인)이 전부 Slack 버튼으로 끝나고, 누가 눌렀는지 감사 로그에 남는다.

**할 일**
- [x] 기존 봇(알림 + promote · abort · undo 버튼, Socket Mode)을 platform `slack-bot/`으로 이식, 대상 레포 · 워크플로 이름을 설정값으로
- [x] PR 머지 버튼: janto PR의 검사 통과 · plan 결과를 알리고, 버튼을 누르면 봇이 머지 API 호출. 누른 사람을 PR 코멘트로 남김
- [x] 운영 승인 · 거절 버튼: 봇을 GitHub App으로 만들고 demo-app `prod` environment의 승인 규칙(custom deployment protection rule)으로 등록, 버튼으로 승인 · 거절
- [ ] 누를 수 있는 사람 제한(`ALLOWED_USER_IDS`), 요청자를 감사 로그 `requested_by`에 기록
- [ ] 알림 흐름 정리: PR 준비 → 테스트 배포 완료(승격 · 취소) → 운영 승인 대기(승인 · 거절) → 운영 반영 결과(되돌리기)

**완료 기준** demo-app janto 배포 한 번을 GitHub 화면 없이 Slack 버튼만으로 prod까지 반영하고, 버튼을 누른 사람이 감사 로그에 남는다.

---

### [T28] 클라우드 DB 연결 복구와 DB 상태 검증

**어디에 필요** AWS test(`yolo.<도메인>`) · prod(`<도메인>`)의 BE가 RDS에 붙지 못해 메모리 모드로 돌고 있다(`/api/info`의 `dbConnected: false`, 화면에 "메모리 모드"). 방명록 · 투표가 재배포마다 사라지므로 데모 시나리오 1:45 · 2:10 장면이 깨진다. 온프레미스는 정상이다.

**만들 것** AWS BE의 DB TLS 접속 설정, service-base가 만드는 접속 문자열 정리, 스킬 템플릿의 기본값, 그리고 DB가 안 붙은 green을 승격하지 않는 smoke 검사.

- **우선순위** P0 · **영역** 레포 · 인프라 · **담당** 원가연
- **선행** `T24`, `T7` · **후속** `T19`, `T33` · **설계 문서** 6.4, FR-9

**목표** 세 배포 대상 모두 같은 값 파일로 BE가 DB에 붙고, DB가 안 붙은 상태는 파이프라인이 잡아낸다.

**원인(확인한 것)** RDS Postgres 17은 TLS 없는 접속을 거부한다. BE(Node `postgres`)는 Secret의 `DATABASE_URL`(`postgresql+psycopg://…`, `sslmode` 없음)로 TLS 없이 붙어 실패하고 메모리 폴백으로 넘어간다. GCP 값(`deploy/gcp/values.yaml`)에는 `PGSSL: require`가 있어 붙지만 AWS 값에는 없다. 온프레미스 Postgres는 TLS를 강제하지 않아 붙는다. 마이그레이션 Job은 `PG_URL`(`sslmode=require`)을 써서 성공하므로 네트워크 · 자격증명은 문제가 없다. `/health`는 DB가 끊겨도 200이라 smoke · AI 판단이 통과한다.

**할 일**
- [x] demo-app `deploy/aws/values.yaml`에 `env.PGSSL: require`(GCP와 동일)를 넣어 test · prod 재배포, `/api/info`가 `dbConnected: true`인지 확인
- [x] service-base `DATABASE_URL`을 Node · Python이 모두 읽는 형식(`postgresql://…?sslmode=require`)으로 바꾸고, SQLAlchemy 접두(`+psycopg`)가 필요하면 별도 키로 둔다. 세 대상에서 같은 키로 붙는지 확인
- [x] deploy-provision 템플릿: `database: true`인 서비스는 클라우드 대상(aws · gcp)에 DB TLS 설정을 기본으로 넣고 `check-artifacts.sh`가 빠졌는지 검사
- [x] promote-judge smoke에 응답 본문 조건(예: `expect_body: {"database": "connected"}`)을 추가하고 demo-app `smoke.json`의 `/health`에 적용. DB가 안 붙은 green은 abort
- [x] ADR: 클라우드 DB는 TLS 필수, 메모리 폴백은 데모 안전장치이지 정상 상태가 아님. 운영 문서에 `dbConnected` 확인 절차

**완료 기준** AWS test · prod와 온프레미스 모두 `/api/info`가 `dbConnected: true`를 돌려주고, 방명록 글이 재배포 뒤에도 남는다. DB를 끊은 상태로 배포하면 smoke가 실패해 승격되지 않는다.

### [T29] 서비스 이중화 (앱 복제 · DB 다중화)

**어디에 필요** 브리프 가용성 답이 "일반 운영"(`standard`)인데 실제로는 모든 대상이 파드 1개다(`deploy/aws/values.yaml` · `deploy/onprem/values.yaml` `replicas: 1`). App Chart에 PodDisruptionBudget · 분산 배치가 없고, RDS는 `multi_az = false`, 온프레미스 Postgres는 단일 StatefulSet이다. 파드 하나가 죽으면 서비스가 멈추므로 Blue-Green 무중단(FR-6)과 "클라우드 활용" 심사 항목에 맞지 않는다.

**만들 것** App Chart의 이중화 템플릿(PDB · topologySpread · 선택적 HPA), 가용성 답변 → `replicas` · `multi_az` 매핑(스킬), AWS 노드 용량 재산정, demo-app 값 갱신, DB 다중화 결정.

- **우선순위** P1 · **영역** 레포 · 인프라 · **담당** 배준범
- **선행** `T24`, `T3` · **후속** `T19` · **설계 문서** 6.4, FR-6

**목표** 가용성 답변대로 파드가 2개 이상 서로 다른 노드에 떠 있고, 파드 하나가 죽어도 요청이 실패하지 않는다.

**할 일**
- [ ] App Chart: `replicas`가 2 이상이면 PodDisruptionBudget(`minAvailable: 1`)과 `topologySpreadConstraints`(노드 분산)를 만든다. `helm lint` · 템플릿 테스트
- [ ] 가용성 답변 → 값 매핑을 스킬에 고정: `demo` 1 / `standard` 2 / `high` 3 이상 + `multi_az`. deploy-analyze 서비스 분석기와 deploy-provision 템플릿에 반영 (지금은 standard인데 aws · onprem 1)
- [ ] AWS 노드 용량 재산정: test · prod × 서비스 2개 × Blue-Green(2배) × replicas 2 + 시스템 파드가 들어가도록 노드 타입 · 수(`infra/envs/aws` `node_count`, `node_instance_types`) 조정, 비용 분석기 추정에 반영 (t3.medium은 노드당 파드 17개)
- [ ] demo-app aws · onprem 값을 `replicas: 2`로 올려 test · prod 재배포. 파드 하나를 지워도 외부 주소 요청 실패 0인지 확인
- [ ] DB: AWS `multi_az`를 가용성 답변에 연결(standard 이상 true, 비용 표기). 온프레미스 Postgres는 단일 유지 여부와 이유를 ADR에 (T27 결정과 맞춤)

**완료 기준** test · prod 각 서비스가 파드 2개 이상 · 서로 다른 노드에 떠 있고, 파드 하나를 지워도 smoke 에러율 0이다. RDS가 multi-AZ이거나 미루는 결정과 비용 근거가 ADR에 있다.

### [T30] Green 공개 경로 제거와 검증 접근 격리

**어디에 필요** 승격 전 Green이 공개 preview Ingress로 노출되는 문제를 차단한다.

**만들 것** 내부 preview Service, localhost 검증 경로, 접근 격리와 마이그레이션 검증.

- **우선순위** P0 · **영역** 레포 · 인프라 · **담당** 이소울, 원가연
- **선행** `T3`, `T5`, `T7` · **후속** `T19` · **설계 문서** FR-6, FR-7

**목표**
승격 전 Green을 인터넷에 공개하지 않고, 검증은 인증된 배포 파이프라인의 localhost port-forward로 수행한다. 클러스터 내부 접근과 관리자 접근은 별도 경계로 검증한다.

**할 일**
- [x] 차트의 공개 preview Ingress 제거, preview Service ClusterIP 고정, 배포 알림의 공개 preview URL 제거
- [x] smoke port-forward를 127.0.0.1로 명시하고 회귀 검사 추가
- [x] 접근 경계·마이그레이션·잔여 위험 ADR 및 검증 절차 작성
- [ ] CNI 지원·다른 허용 정책을 확인해 승격 전 내부 Green 격리와 pipeline RBAC 최소 권한 설계·적용·검증
- [ ] 새 버전 릴리스와 demo-app 적용 후 기존 preview Ingress/LB listener 제거 및 active 정상·인증된 smoke 정상 확인

**완료 기준**
AWS/GCP/onprem에서 승격 전 공개 preview 경로 없음. 인증된 pipeline smoke 성공, 비인가 내부 워크로드 접근 차단, 승격 후 active 정상. 관리자·노드 권한은 신뢰 경계 예외임을 명시. 기존 설치의 마이그레이션까지 확인하고 완료 처리한다.


### [T33] 온프레미스 DB 비공개 연결 통로와 자격증명

**어디에 필요** T32(AWS 앱 · 온프레미스 DB)의 기술적으로 가장 불확실한 부분. EKS 파드가 맥북 k3d의 Postgres에 인터넷 노출 없이 붙어야 하고, 그 접속 정보가 AWS 쪽 Secret으로 흘러야 계층별 배포가 성립한다. 통로가 붙기 전에는 T32의 자동화를 실제로 검증할 수 없다.

**만들 것** AWS BE → 온프레미스 PostgreSQL 비공개 연결(Cloudflare Tunnel TCP + Access 또는 Tailscale subnet router · operator 중 선택)과 그 ADR, 주소 유지 · DNS · TLS · 접근 제한, 온프레미스 DB 자격증명을 AWS Secrets Manager → External Secrets로 전달하는 경로, 끊김 · 재연결 · 무단 접근 검증과 한계 문서. **T32와의 접점**: AWS 클러스터의 `<앱>-db` Secret에 `DATABASE_URL` · `PG_URL`(`sslmode=require`)이 들어오면 앱 · 차트 · 워크플로는 아무것도 몰라도 된다.

- **우선순위** P1 · **영역** 레포 · 인프라 · **담당** 원가연
- **선행** `T3`, `T27`, `T28` · **후속** `T32` · **설계 문서** 6.4, FR-9, NFR-2

**목표** EKS test 네임스페이스의 BE가 맥북 Postgres에 TLS로 붙고, DB 포트는 인터넷에 열리지 않으며, 접속 정보는 AWS Secret으로만 전달된다.

**할 일**
- [x] AWS BE → 온프레미스 DB의 VPN 등 비공개 연결 방식, 주소 유지, 라우팅, DNS, 암호화와 접근 제한을 설계하고 테스트 환경에서 검증한다. DB 포트를 인터넷에 공개하지 않는다. 후보 비교(Cloudflare Tunnel TCP · Tailscale)와 결정을 ADR에
- [ ] 맥북 재부팅 · 잠금 뒤에도 통로가 다시 서고 주소가 유지되는지 확인한다 (T27 자동 복구와 맞춤). 안 되면 복구 절차를 README에
- [ ] k3d 쪽 publish를 임시 루트가 아니라 demo-app `infra/envs/onprem` 루트(`module "db_link"`)에 넣고 T27의 onpremctl(ephemeral 입력 · 로컬 state)로 plan · apply한다. 이때 T27이 요청한 "가연 맥북에서의 Terraform state 검증"(기존 비밀번호 · 데이터 보존, state에 평문 없음)을 같이 확인하고 결과를 T27 #82에 남긴다
- [x] 온프레미스 PostgreSQL의 데이터·자격증명을 유지하며 AWS 앱에서 사용할 접속 Secret을 구성한다. 비밀번호를 Git·Terraform state·로그에 평문으로 기록하지 않고 test·prod의 DB 데이터와 자격증명을 분리한다. `DATABASE_URL` · `PG_URL` 키와 `sslmode=require`는 service-base와 같게
- [ ] BE 파드만 DB에 닿도록 제한한다 (보안 그룹 · NetworkPolicy · Access 정책 중 통로에 맞는 것). 다른 네임스페이스 · 외부에서의 접속이 거부되는지 확인
- [ ] (T32에서 이관) demo-app test에서 클라우드 FE·BE와 온프레미스 DB의 게시글 생성·조회·수정·삭제, 마이그레이션 실행, BE 재배포 후 데이터 보존을 검증한다. DB 연결 실패 시 승격 차단과 기존 버전의 영향을 확인하고 결과를 기록한다
- [ ] 연결 끊김·재연결, 권한 없는 접근 차단, 비밀값 노출 여부를 검증한다. 끊긴 동안 BE가 메모리 폴백으로 조용히 넘어가지 않고 `/health`가 503을 내는지 확인. 연결·배포·정리 절차, 지원 조합, 온프레미스 DB 장애가 기존 앱에도 영향을 준다는 한계를 문서화하고 관련 Terraform·Helm·워크플로 검사를 통과한다

**완료 기준** EKS test의 BE 파드가 맥북 Postgres에 TLS로 붙어 `/api/info`가 `dbConnected: true`를 돌려주고, DB 포트는 외부에서 닿지 않는다. 접속 정보는 AWS Secret으로만 들어오고 Git · state · 로그에 평문이 없다. 통로를 끊으면 `/health`가 503이 되고 다시 이으면 복구된다. test에서 CRUD · 마이그레이션 · BE 재배포 뒤 데이터 보존이 확인되고(T32에서 이관), 통로가 demo-app 온프레미스 루트로 관리돼 맥북 재부팅 뒤에도 다시 선다.

### [T32] 계층별 배포 위치 분리 (AWS 앱 · 온프레미스 DB)

**어디에 필요** 현재 배포 대상 단위의 구성을 FE·BE·DB 계층별 배포 위치 선택으로 확장한다. 같은 앱 정의로 클라우드 앱이 온프레미스 DB를 사용하게 해 대회 주제의 이식성을 검증한다. 연결 통로와 자격증명은 `T33`이 만든다.

**만들 것** 계층별 대상 설정 계약, 분석·산출물 생성·워크플로 연결, demo-app의 통합 검증 기록과 ADR. 첫 지원 조합은 FE·BE=AWS / DB=onprem이다. FE=GCP / BE=AWS / DB=onprem과 다른 조합은 후속 확장으로 두며 이번 완료 조건에 포함하지 않는다. **T33과의 접점**: AWS 클러스터의 `<앱>-db` Secret에 `DATABASE_URL` · `PG_URL`이 들어온다고 전제하고, 통로가 붙기 전에는 계약 · 검사 · 템플릿 뼈대를 먼저 만든다.

- **우선순위** P1 · **영역** 레포 · 인프라 · **담당** 배규태
- **선행** `T3`, `T24`, `T28`, `T13`, `T33` · **후속** 없음 · **설계 문서** 6.3, 6.4, FR-9

**목표** 계층별 배포 위치를 명시하고, FE·BE는 AWS에, DB는 온프레미스에 배포한다. 클라우드 앱에서 작성한 게시글이 온프레미스 DB에 저장되고 다시 조회된다.

**할 일**
- [x] 배포 설정의 FE·BE·DB 대상 계약과 기존 단일 target의 호환 규칙을 정의한다. 첫 지원 조합만 허용하고 미지원 조합은 인프라 변경 전에 명확한 오류로 중단한다(`check-artifacts.sh`). 후속 확장 범위를 ADR에 기록한다
- [x] deploy-analyze·deploy-provision과 재사용 워크플로를 계층별 대상에 연결한다. 온프레미스 DB를 선택하면 AWS RDS를 새로 생성하지 않고(`infra/envs/aws`에서 `module.database` 대신 외부 DB 입력) 기존 리소스 삭제·데이터 이전은 명시적인 절차로 분리한다. 기존 단일 대상 호출의 동작을 유지한다(`tests/run.sh`)

**완료 기준** 지원 조합을 설정하면 수작업으로 앱 접속 정보를 고치지 않고 AWS FE·BE가 온프레미스 DB에 연결된다(계약 · 스킬 · 워크플로 연결과 로컬 검증). 기존 단일 대상 배포의 회귀가 없다. demo-app test에서의 CRUD · 데이터 보존 · 승격 차단 검증과 DB의 비공개 노출 · 접근 제한은 맥북 DB · 통로가 필요해 `T33`의 완료 기준으로 옮겼다(2026-10-11, 배규태 · 원가연 합의). 운영 데이터의 무중단 이전·DB 이중화·모든 배포 조합 자동 지원은 별도 작업이다.

### [T34] test · prod DB와 계정 분리

**어디에 필요** AWS · GCP는 test와 prod가 같은 DB 인스턴스 · 같은 DB · 같은 Secret을 쓴다(demo-app `infra/envs/aws/main.tf`, `infra/envs/gcp/main.tf`). AWS는 그 Secret이 RDS 마스터 계정이다. 그래서 승인 없이 도는 yolo test 배포의 마이그레이션(`db/init.sql`)이 prod 데이터에 닿고, 장애 훈련(T36)을 test에서 해도 prod 데이터가 영향을 받는다. 온프레미스는 이미 환경별로 DB가 따로다.

**만들 것** 같은 인스턴스 안에서 환경별 DB와 앱 전용 계정, 환경별 `<앱>-db` Secret, 마스터 계정을 앱 경로에서 빼기.

- **우선순위** P1 · **영역** 레포 · 인프라 · **담당** 원가연
- **선행** `T28` · **후속** `T36` · **설계 문서** 6.4, `docs/chaos-drill.md`

**목표** test 계정으로는 prod DB에 아무것도 할 수 없고, 앱 · 마이그레이션은 마스터 계정을 쓰지 않는다.

**할 일**
- [ ] database 모듈(aws · gcp)에 환경별 DB · 앱 계정 입력 추가. 비밀번호는 Secrets Manager · Secret Manager에만 두고 state · 로그에 평문을 남기지 않는다
- [ ] service-base가 환경별 Secret을 만들고, demo-app `infra/envs/aws` · `gcp`가 test · prod에 서로 다른 Secret을 넘긴다
- [ ] 기존 데이터 이전 절차(prod 데이터는 prod DB로, test는 새로 시드)를 README에 적고 aws · gcp에 적용
- [ ] 확인: test 계정으로 prod DB 접속 · 조회가 거부되고, 두 환경 모두 `/api/info`의 `dbConnected: true`

**완료 기준** aws · gcp에서 test · prod가 서로 다른 DB와 계정을 쓰고, test 계정으로 prod DB에 접근이 거부된다. 앱 경로의 Secret에 마스터 계정이 없다.

### [T35] 환경별 값 파일과 prod 장애 주입 차단

**어디에 필요** demo-app의 `POST /api/chaos`(인증 없는 장애 주입)는 `CHAOS_ENABLED=true`일 때만 열리지만, test와 prod가 같은 `deploy/values-be.yaml`을 써서 prod에서도 열려 있다. 누구나 운영 앱의 에러율을 100%로 만들 수 있다. 지금 구조로는 환경마다 값을 다르게 줄 방법이 없다.

**만들 것** 재사용 `deploy.yml`의 환경별 덧붙임 값 파일, demo-app의 test 전용 값 파일, 스킬 · 산출물 검사.

- **우선순위** P0 · **영역** 파이프라인 (platform 재사용 워크플로) · **담당** 원가연
- **선행** `T5`, `T13` · **후속** `T36` · **설계 문서** 6.3, `docs/chaos-drill.md`

**목표** prod에는 장애 주입 변경 경로가 없고, 대상 레포가 환경별로 값을 다르게 줄 수 있다.

**할 일**
- [x] `deploy.yml`: 서비스 값 파일이 `deploy/values-be.yaml`이면 `deploy/values-be.<environment>.yaml`이 있을 때 뒤에 덧붙인다(`deploy/<target>/values.yaml` 덧붙임과 같은 방식). 덧붙임 순서를 문서와 테스트로 고정
- [x] demo-app: `deploy/values-be.yaml`에서 `CHAOS_ENABLED`를 빼고 `deploy/values-be.test.yaml`에만 둔다
- [x] deploy-provision 템플릿 · `check-artifacts.sh`: 장애 주입 · 디버그 플래그는 기본 값 파일에 두지 못하고 test 덧붙임 파일에만 허용
- [x] 릴리스 후 demo-app 적용: prod `POST /api/chaos` → 404, test는 그대로 동작

**완료 기준** aws · gcp · onprem prod에서 `POST /api/chaos`가 404이고 test에서는 동작한다. 덧붙임 파일이 없는 기존 대상 레포는 동작이 바뀌지 않는다.


## 9단계

앞 단계의 선행 작업이 끝나면 아래 작업을 동시에 진행한다.

### [T10] yolo 배포 리포트

**어디에 필요** yolo는 리뷰가 없으니, 무엇을 안고 배포했는지 기록과 책임 소재를 남긴다.

**만들 것** 공통 액션 `yolo-report`(재사용 `deploy.yml`의 `yolo-report` job에서 호출): 리포트 JSON 생성 → S3 감사 로그 저장 → 문제가 있으면 `yolo-debt` 이슈 생성.

- **우선순위** P1 · **영역** 파이프라인 (platform 재사용 워크플로) · **담당** 배규태
- **선행** `T8` · **후속** 없음 · **설계 문서** 6.3, FR-12

**목표** yolo 배포마다 누가·언제·어떤 문제를 안고 배포했는지 남고, 문제가 있으면 이슈가 열린다.

**할 일**
- [x] 리포트 JSON 스키마, 공통 액션 `yolo-report` · `deploy.yml` 연결
- [x] 수집: 실행자, 시각, SHA, 대상, compliance, template_version, 자동 수정 이력, 비차단 경고, AI 판단 근거, 승인 생략 여부
- [x] 저장: 감사 로그(S3), 실행 요약. 문제가 있으면 demo-app에 `yolo-debt` 이슈

**완료 기준** 경고가 있는 yolo 배포 후 `yolo-debt` 이슈가 열린다.

### [T31] 승인자용 green 미리보기 (Identity Center SSO)

**어디에 필요** regulated 대상은 사람이 승격하는데, T30 이후 승인자가 green을 열어 볼 방법이 없다. 설계 문서 FR-6(승격 전 미리보기 주소)을 인증된 경로로 되살린다.

**만들 것** Identity Center(SAML) → Cognito(OIDC) → 차트 안 oauth2-proxy로 인증을 강제하는 `green.<host>` 미리보기, 배포 알림의 green 링크 (ADR 0015).

- **우선순위** P1 · **영역** 레포 · 인프라 · **담당** 이소울
- **선행** `T2`, `T23`, `T30` · **후속** `T38` · **설계 문서** FR-6

**목표** 승인자가 Slack 알림의 링크로 green을 열고, Identity Center 승인자 그룹이 아닌 사람과 인증되지 않은 요청은 green에 닿지 않는다.

**할 일**
- [x] ADR 0015 합의(T30 담당자), 합의되면 ADR 0011(private-green-access)에 보완 문단 추가
- [x] `modules/preview_auth/aws`: Cognito User Pool · 도메인 · 앱 클라이언트 · SAML IdP. `terraform validate` · 테스트
- [x] `org/`: Identity Center 고객 관리형 SAML 앱과 승인자 그룹 할당. API로 안 되는 설정은 `org/README.md` 콘솔 설정 표에 기록
- [x] App Chart: `preview.auth` 입력과 oauth2-proxy Deployment · Service · Ingress. 인증 설정 없이는 preview Ingress를 렌더하지 않는 T30 회귀 테스트 유지, 인증 조합 테스트 추가
- [x] `deploy.yml`: preview 인증을 켠 릴리스는 Slack 알림 · 실행 요약에 green 링크 표시, `previewAuth.routes`가 없으면 green 화면의 API가 active BE로 간다는 한계 문구 포함
- [x] demo-app aws 적용: green 호스트 DNS · 인증서 · 시크릿 주입. 승인자 로그인 성공, 비할당 사용자 · 비인증 요청 차단 확인
- [ ] onprem 적용: green 전용 Named Tunnel(Public Hostname → `<release>-preview-auth`), `platform` 네임스페이스 시크릿, Cognito 콜백 추가. aws와 같은 확인. gcp는 `T38`

**완료 기준** aws · onprem에서 regulated 배포 알림의 green 링크를 승인자가 SSO로 열 수 있고, 비인증 요청은 green에 닿지 않는다. promote-judge smoke는 지금처럼 port-forward로 성공한다.

### [T38] gcp 승인자용 green 미리보기

**어디에 필요** `T31`은 aws · onprem에서 SSO로 green을 연다. gcp는 green 호스트에 붙일 HTTPS · DNS가 없고 비밀값 저장소가 달라 따로 다룬다.

**만들 것** App Chart preview Ingress 전용 TLS · 어노테이션 입력, demo-app gcp의 시크릿 · 고정 IP · DNS · Cognito 콜백.

- **우선순위** P2 · **영역** 레포 · 인프라 · **담당** 이소울
- **선행** `T31` · **후속** 없음 · **설계 문서** FR-6

**목표** gcp 대상에서도 승인자가 Slack 알림의 green 링크를 SSO로 열고, 인증되지 않은 요청은 green에 닿지 않는다.

**할 일**
- [ ] App Chart: preview Ingress에만 붙는 TLS(GKE ManagedCertificate 또는 미리 올린 인증서) · 고정 IP 어노테이션 입력. active Ingress와 충돌하지 않는지 테스트
- [ ] demo-app `infra/envs/gcp`: oauth2-proxy 시크릿(GCP Secret Manager) · `readable_secret_ids` · 고정 IP, `infra/envs/aws`: Route53 레코드 · Cognito 콜백. `deploy.yml` 대상별 `preview-host`
- [ ] gcp test · prod 적용과 확인: 승인자 로그인 성공, 비할당 사용자 · 비인증 요청 차단, promote-judge smoke 정상

**완료 기준** gcp에서 regulated 배포 알림의 green 링크를 승인자가 SSO로 열 수 있고, 비인증 요청은 green에 닿지 않는다.

### [T39] 여러 배포 대상 동시 배포

**어디에 필요** 지금은 실행 한 번에 대상 하나(`DEPLOY_TARGET`)에만 배포한다. 같은 배포 정의로 aws · gcp · onprem에 한 번에 같은 버전을 올린다.

**만들 것** `deploy-provision` 호출부 템플릿(`deploy.yml.tmpl`)의 대상 목록 변수 `DEPLOY_TARGETS`, 이번에 배포할 대상을 고르는 `targets` job, `test` · `prod` job의 대상별 matrix. platform 재사용 워크플로는 대상 하나를 받는 지금 구조를 유지한다.

- **우선순위** P2 · **영역** 파이프라인 (platform 재사용 워크플로) · **담당** 이소울
- **선행** `T3`, `T4`, `T24`, `T6`, `T8` · **후속** 없음 · **설계 문서** 3장(같은 배포 정의로 AWS, GCP, 온프레미스에 배포)

**목표** push 한 번으로 고른 대상 모두에 test가 병렬로 돌고, 모든 대상의 test가 통과했을 때만 모든 대상의 prod로 넘어간다. 한 대상이라도 실패하면 어느 대상도 prod로 가지 않는다.

**할 일**
- [ ] `deploy.yml.tmpl`: 레포 변수 `DEPLOY_TARGETS`(쉼표 구분, 없으면 `DEPLOY_TARGET`, 그것도 없으면 `aws`), 수동 실행 `target`에 `all` 추가. `targets` job이 대상 목록과 `changes` 결과로 matrix JSON을 만든다(job `if`에서는 `matrix`를 쓸 수 없다)
- [ ] `test` · `prod`: `strategy.matrix.include`로 대상별 `target` · `target-label` · `onprem-runner-label` · `cluster` · `host` · `preview-host`, `fail-fast: false`. `prod`는 모든 대상의 `test` 성공 후에만 진행
- [ ] onprem 대상은 runner가 꺼져 있으면 `targets` 단계에서 실패로 알린다(`scripts/onprem/target.py` 재사용). 대기 상태로 prod 전체를 붙잡지 않는다
- [ ] yolo 리포트 · 자동 머지 PR이 대상 수만큼 생기지 않게 기준 대상 하나에만 `yolo-auto-merge`를 켠다
- [ ] Slack 승인 버튼(`<run_id>@prod`) 한 번으로 모든 대상의 prod 승인이 처리되는지 확인. 안 되면 slack-bot이 같은 실행의 대기 중인 승인을 모두 처리하게 고친다
- [ ] 문서: `deploy-provision` 스킬 · `references/artifacts.md` · `docs/gcp-deploy.md`의 `DEPLOY_TARGET` 설명, ADR(전부 통과해야 prod로 가는 이유)
- [ ] demo-app 적용: `DEPLOY_TARGETS=aws,gcp`로 확인한 뒤 onprem 추가

**완료 기준** demo-app main push 한 번으로 aws · gcp · onprem test가 병렬로 돌고, Slack 승인 한 번 뒤 세 대상 prod에 같은 이미지 digest가 올라간다. 한 대상의 test를 실패시키면 세 대상 모두 prod로 가지 않는다.

### [T36] 장애 훈련 워크플로 (green 확인 · 주입 · 채점)

**어디에 필요** AI 승격 판단 · 규칙 거부권 · Blue-Green은 "문제가 생기면 막는" 장치인데, 평소 배포는 대부분 성공해서 막는 장면을 확인할 일이 없다. test에 일부러 장애를 내고 가드레일이 실제로 막는지 매번 확인한다.

**만들 것** platform 재사용 워크플로 `chaos.yml`과 시나리오 목록, demo-app 호출부. 단계: green 확인 → green 준비 → 장애 주입 → promote-judge(manual) → blue 확인 → 정리(항상) → 채점. 설계는 `docs/chaos-drill.md`.

- **우선순위** P1 · **영역** 파이프라인 (platform 재사용 워크플로) · **담당** 원가연
- **선행** `T7`, `T30`, `T34`, `T35` · **후속** `T37`, `T19` · **설계 문서** FR-6, FR-7, `docs/chaos-drill.md`

**목표** 명령 하나로 test의 green에 장애를 넣고, 기대한 판단(대부분 abort)이 나오는지, blue가 멀쩡한지 확인한 뒤 원래 상태로 돌려놓는다.

**할 일**
- [x] green 확인: Rollout `phase` · `pauseConditions` · `activeSelector` · `previewSelector`로 대기 중인 green이 있는지 판단. 없으면 거절(`new-green`이면 훈련용 green), 배포 진행 중 · `Degraded`면 거절하고 이유를 남긴다. 서비스 묶음 단위, 확인한 preview 해시를 주입 · 정리 직전에 다시 비교
- [x] green 준비 · 주입: 훈련용 green은 파드 템플릿 annotation으로 revision만 바꿔 띄운다. 앱 장애는 green **파드마다** port-forward로 `POST /api/chaos`, 파드 장애는 green 파드 삭제. blue에는 경로가 없다
- [x] 판단 · 확인: 기존 `promote-judge`를 `mode: manual`로 호출, active 서비스에도 smoke를 보내 blue 에러율을 남긴다
- [x] 정리(`if: always()`): 장애 해제와 해제 확인, 훈련용 green이면 abort · annotation 복구 · `Healthy` 확인, 대기 중이던 green은 `Paused`로 남긴다. 해제를 확인하지 못하면 실패로 남긴다
- [x] 시나리오 목록(`error-burst` · `slow-response` · `db-down` · `flaky`)과 기대 결과로 채점. namespace는 `test` 고정(입력 없음), test 배포 · `rollout.yml`과 같은 concurrency group, `timeout-minutes`
- [ ] 감사 로그(`audit-log`)에 시나리오 · 기대 · 실제 · 요청자. 워크플로 테스트(가짜 kubectl)와 demo-app `chaos.yml` 호출부, aws · onprem에서 시나리오 4개 통과 확인

**완료 기준** aws · onprem test에서 시나리오 4개가 모두 기대대로(abort) 채점되고, 훈련 중 blue 에러율이 0%이며, 끝난 뒤 Rollout이 원래 상태(`Healthy` 또는 `Paused`)로 돌아온다. green이 없거나 배포 중이면 아무것도 바꾸지 않고 거절한다.

### [T37] 장애 훈련 Slack 명령과 Grafana 기록

**어디에 필요** 장애 훈련(T36)을 원터치로 시작하고, 결과를 팀과 심사위원이 보는 곳(Slack · Grafana)에 남긴다.

**만들 것** Slack `/chaos` 명령과 janto 승격 대기 알림의 `[🧪 장애 훈련]` 버튼, 훈련 결과 메시지, `publish-metrics`의 훈련 기록과 `deploy-overview` 대시보드 패널.

- **우선순위** P1 · **영역** 파이프라인 (platform 재사용 워크플로) · **담당** 원가연
- **선행** `T36`, `T26`, `T17` · **후속** `T19` · **설계 문서** FR-12, `docs/chaos-drill.md`

**목표** Slack에서 한 번에 훈련을 시작하고, 통과 · 실패와 근거가 Slack 메시지와 Grafana에 남는다.

**할 일**
- [ ] slack-bot: `/chaos <시나리오> <대상> [new-green]`, `/chaos list`. `/rollout`과 같은 구조로 `ALLOWED_USER_IDS` 확인 후 `workflow_dispatch`. 환경 입력은 받지 않는다(test 고정). 테스트 추가
- [ ] janto 승격 대기 알림(`slack-notify`)에 `[🧪 장애 훈련]` 버튼과 시나리오 선택. 누르면 그 대상 · 환경으로 dispatch
- [ ] 시작 · 거절 · 결과 메시지: 기대 vs 실제 판단, AI 근거, blue 수치, 정리 결과, 실행 · Grafana 링크. 해제를 확인하지 못했으면 승격 금지 경고와 abort 버튼
- [ ] `publish-metrics`에 `kind: drill` 레코드, `deploy-overview`에 훈련 목록 · 시나리오별 통과율 · 마지막 훈련 시각 패널

**완료 기준** Slack `/chaos error-burst aws new-green` 한 번으로 훈련이 돌고, 결과 메시지와 Grafana 패널에 같은 실행이 보인다. 허용되지 않은 사용자의 요청은 거절된다.

---

## GitHub Project 등록 현황

- 이슈는 `one-tatchi-platform` 레포, 보드는 조직 프로젝트 **Softbank 2026 project**
- 등록된 이슈: T1~T25 (#1~#25), T26 (#35), T27 (#82), T28 (#130), T29 (#131), T32 (#155)
- 라벨: `P0`/`P1`/`P2`, `area:infra`/`area:pipeline`/`area:skill`/`area:docs`, `stage:N`
