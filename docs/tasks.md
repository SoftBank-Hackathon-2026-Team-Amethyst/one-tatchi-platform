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

**원가연** · 플랫폼 코어 (5개, P0 5개)
- `T1` 레포 두 개와 bootstrap (P0)
- `T3` 온프레미스 구현체 (로컬 맥북) (P0)
- `T5` test / prod 분리와 브랜치 흐름 (P0)
- `T20` 템플릿 레포 구성과 릴리스 (P0)
- `T21` 레포 간 참조 검증 (P0)

**이소울** · 파이프라인 (7개, P0 5개)
- `T6` 규제 여부에 따른 운영 관문 (P0)
- `T8` yolo main PR 자동 생성 · 자동 머지 (P0)
- `T9` 배포 시간 2분대 단축 (P0)
- `T23` 초기 인프라 세팅 (계정 · 권한) (P0)
- `T22` 템플릿 버전 업데이트 흐름 (P1)
- `T2` 도메인과 HTTPS (P0)
- `T26` Slack 버튼으로 머지 · 승인 · 승격 (P1). 담당 필요

**김형래** · 에이전트 스킬 (5개, P0 4개)
- `T13` janto / yolo 두 경로로 스킬 정리 (P0)
- `T14` yolo 자동 수정 루프 (P0)
- `T15` 브리프 질문 UX (P0)
- `T24` AWS 구현체 (P0)
- `T17` Grafana 통합 (P1)

**배준범** · 배포 대상 · 데모 앱 (2개, P0 1개)
- `T25` 데모 앱 개발 (P0)
- `T11` 검사 3종 추가 (P1)

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
| yolo의 main PR 생성 · 자동 머지 주체 | T8 | GHA 또는 에이전트 |
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
- [ ] 가격 조회 스크립트(예: `skills/deploy-analyze/scripts/price.py`): AWS Pricing API · GCP Cloud Billing Catalog API로 리전별 단가 조회 → JSON
- [ ] 계산 규칙: 추천 구성(트래픽 분석기 결과)을 템플릿 자원 목록으로 바꿔 `단가 × 730시간`, 고정비와 변동비 구분
- [ ] `references/analyzers/budget.md` 수정: "알고 있는 가격으로 추정" 대신 조회 도구 사용, 후보별(aws / gcp / onprem / 하이브리드) 비교 표, 예산 초과 시 절감안
- [ ] 분석 보고서 요약에 월 예상 비용 연결 (janto 리뷰 지점 1에서 표시)

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
- **선행** `T20` · **후속** `T17`, `T19` · **설계 문서** 6.4

**목표** 같은 App Chart로 로컬 맥북의 게시판이 Cloudflare Quick Tunnel HTTPS 주소에서 동작한다.

**할 일**
- [x] k3d(또는 OrbStack)로 k3s 클러스터 생성, Docker VM 메모리 6~8GB
- [x] k3s 설치, Cloudflare Tunnel → HTTPS 주소 (클러스터 안 cloudflared Quick Tunnel `*.trycloudflare.com`. 고정 도메인은 쓰지 않기로 함, 필요하면 `tunnel.token_secret`으로 Named Tunnel 전환. Traefik 대신 터널이 Service로 바로 연결)
- [ ] platform의 온프레미스 cluster · cluster_addons(터널 · secrets) · database · registry 모듈을 demo-app `infra/envs/onprem`에서 태그로 참조해 구성
- [ ] App Chart로 demo-app의 be · fe를 맥북 test에 배포하고 터널 HTTPS 주소에서 화면 · 게시판 API · DB 연결 확인

**완료 기준** 맥북 test 환경의 게시판 화면과 API가 Cloudflare Tunnel HTTPS 주소에서 동작하고 DB에 연결된다.

### [T24] AWS 구현체

**어디에 필요** AWS에 실제로 VPC · EKS · RDS 등을 만드는 Terraform 코드. 첫 배포 대상(Happy Path).

**만들 것** `modules/*/aws` Terraform 구현체 7개(사전 검증 코드 이식 + 해결한 문제 반영)와 demo-app용 `infra/envs/aws` 예시 루트.

- **우선순위** P0 · **영역** 레포 · 인프라 · **담당** 김형래
- **선행** `T20` · **후속** `T21` · **설계 문서** 6.4

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
- [ ] GCP 프로젝트와 결제 연결
- [ ] platform의 `ci_identity/gcp`(Workload Identity Federation, demo-app 신뢰)
- [ ] network · cluster(GKE) · registry(Artifact Registry) · database(Cloud SQL) · secrets · observability 구현
- [ ] 출력값 이름이 aws 구현체와 같은지 확인
- [ ] demo-app에 `infra/envs/gcp` 루트 추가, 배포 확인

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
- [ ] demo-app에서 `uses: <org>/one-tatchi-platform/.github/workflows/deploy.yml@v1.0.0` 호출 (진행 중: 재사용 워크플로 호출은 `infra.yml@v1`로 확인(PR plan · main apply). `deploy.yml`은 EKS 클러스터가 있어야 해서 T24 이후, 또는 맥북 self-hosted runner(T3)로 onprem 배포 경로를 만든 뒤)
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
- [ ] 중앙 Grafana에 CloudWatch, Prometheus(온프레미스), Cloud Monitoring 연결
- [ ] 대시보드: 서비스별 요청 · 에러율 · 응답시간 · 리소스
- [ ] AI 판단 job과 같은 쿼리 사용

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
- [ ] 네임스페이스 `test`, `prod` (service-base 차트 확장)
- [ ] demo-app 호출부 트리거: `push: yolo/**` → test, `push: main` → test 후 prod, `pull_request` → 검사·plan
- [ ] 재사용 `deploy.yml`에 대상 · 환경 입력, prod job에 environment 연결
- [ ] test에서 검증한 같은 이미지를 prod에 사용(rebase 머지 또는 PR head SHA 조회)
- [ ] 환경별 `concurrency`, 테스트 슬롯 1개
- [ ] 온프레미스 runner에서 GHCR 차트·이미지를 받아 test 배포하는 경로 확인

**완료 기준** yolo push는 test만, main 머지는 test → prod로 간다.

### [T13] janto / yolo 두 경로로 스킬 정리

**어디에 필요** 사용자가 실제로 실행하는 진입점(`/janto-deploy`, `/yolo-deploy`). 앱을 분석해 배포 파일을 만든다.

**만들 것** `skills/`의 `/janto-deploy` · `/yolo-deploy` 스킬 문서(SKILL.md)와 산출물 생성 규칙(Dockerfile, values, tfvars, `config.yaml`, `smoke.yaml`, 워크플로 호출부).

- **우선순위** P0 · **영역** 스킬 · **담당** 김형래
- **선행** `T21`, `T25` · **후속** `T14` · **설계 문서** 6.1, 6.3

**목표** 두 스킬이 demo-app에 PR 또는 `yolo/*` 브랜치를 만든다. 스킬은 직접 apply하지 않는다.

**할 일**
- [ ] 기존 배포 스킬을 platform의 `skills/`로 이동
- [ ] platform의 `skills/`를 새 계약에 맞게 수정: 로컬 자격증명으로 apply하는 단계 제거
- [ ] `/janto-deploy`: 리뷰 지점 1 → 기능 브랜치 + main PR
- [ ] `/yolo-deploy`: `yolo/<기능>` push
- [ ] 산출물 생성(6.3 표): Dockerfile, 값 파일, `infra/envs/<대상>`(원격 모듈 참조 + tfvars), `.deploy/config.yaml`(`template_version` 포함), `.deploy/smoke.yaml`(API 분석으로 smoke 요청 목록), 재사용 워크플로 호출부
- [ ] `.deploy/`에 배포 기록

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
- [ ] ALB HTTPS 리스너와 HTTP → HTTPS 리다이렉트 (진행 중: 차트 annotation 반영, 실제 ALB 확인은 클러스터(T24) · T5 이후)
- [ ] (선택) external-dns 애드온으로 DNS 레코드 자동 생성 (진행 중: `cluster_addons/aws`에 추가, `infra/envs/aws`에서 `dns_zone_id` 연결은 T24와 조율)
- [ ] `deploy.yml`에 환경별 `host` 입력(`--set ingress.host`) 추가 — T5(원가연)와 조율

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
- **선행** `T5` · **후속** `T8`, `T12` · **설계 문서** 6.5, FR-7

**목표** green의 지표를 보고 promote 또는 abort를 정하고 근거를 남긴다.

**할 일**
- [ ] 관찰 창 동안 preview Service에 port-forward로 smoke 요청 실행 (`.deploy/smoke.json` + GET 반복, ADR 0003). green은 승격 전 사용자 트래픽이 없으므로 이게 판단 근거가 된다
- [ ] 관찰 창(기본 30초, 입력 `window-seconds`) 동안 smoke 결과 · 에러율 · p95 · 재시작 · 헬스체크 조회
- [x] 판단 기준값 정의(12장 미결정 2번). 기본값과 근거는 `.github/actions/promote-judge/README.md`
- [x] LLM 호출(Claude API, 모델 `claude-sonnet-5-5`) → `{decision, reason}` JSON, API 키는 demo-app Secret → `secrets: inherit`
- [ ] `kubectl argo rollouts promote / abort`. yolo는 자동, janto는 AI 판단을 알림에 남기고 사람이 Slack 버튼(`rollout.yml`)으로 실행
- [x] 호출 실패 시 안전한 기본값(abort), 규칙 판정에 거부권(ADR 0004)

**완료 기준** 정상 버전은 promote, 일부러 500을 내는 버전은 abort된다.

### [T9] 배포 시간 2분대 단축

**어디에 필요** 데모가 3분이다. 배포가 그 안에 끝나야 라이브로 보여 줄 수 있다.

**만들 것** 워크플로 최적화: BE · FE 병렬 matrix, buildx GHA 캐시, 의존성 캐시. 단계별 소요 시간 측정 기록.

- **우선순위** P0 · **영역** 파이프라인 (platform 재사용 워크플로) · **담당** 이소울
- **선행** `T5` · **후속** `T19` · **설계 문서** NFR-1

**목표** yolo push부터 test 반영까지 2분대.

**할 일**
- [ ] 단계별 소요 시간 측정
- [ ] BE · FE 병렬(matrix), 검사 job 병렬
- [ ] `docker buildx` + GHA 캐시, 베이스 이미지 미리 빌드, pnpm · uv 캐시
- [ ] 원격 모듈 · OCI 차트 다운로드 시간 확인(캐시)

**완료 기준** yolo push → test 반영이 2분대로 측정된다.

### [T14] yolo 자동 수정 루프

**어디에 필요** yolo에서 검사가 실패해도 사람 없이 AI가 고쳐서 다시 올린다.

**만들 것** `/yolo-deploy`의 수정 루프: `gh run watch`로 대기 → 실패 로그 수집 → 허용 경로만 수정 → 재push(최대 3회) → 실패하면 보고.

- **우선순위** P0 · **영역** 스킬 · **담당** 김형래
- **선행** `T13` · **후속** 없음 · **설계 문서** 6.3, FR-11

**목표** 검사 실패를 AI가 최대 3회까지 고쳐 통과시킨다.

**할 일**
- [ ] `gh run watch`로 대기, `gh run view --log-failed`로 실패 로그 수집
- [ ] 수정 허용: 앱 코드, Dockerfile, 값 파일. 템플릿은 다른 레포라 애초에 수정 불가
- [ ] demo-app 안의 금지 경로(테스트, 워크플로 호출부, config의 compliance)를 건드리면 중단
- [ ] 최대 3회, 실패 시 정리해 보고

**완료 기준** 일부러 깨뜨린 린트 · 테스트를 AI가 고쳐 통과시킨다.

---

## 8단계

앞 단계의 선행 작업이 끝나면 아래 작업을 동시에 진행한다.

### [T8] yolo main PR 자동 생성 · 자동 머지

**어디에 필요** yolo가 test 검증 후 사람 손 없이 main까지 가게 한다. yolo가 진짜 yolo가 되는 부분.

**만들 것** yolo가 test 승격 후 `main` PR을 만들고 auto-merge를 거는 단계(GHA job 또는 스킬)와 GitHub App 토큰.

- **우선순위** P0 · **영역** 파이프라인 (platform 재사용 워크플로) · **담당** 이소울
- **선행** `T7` · **후속** `T10` · **설계 문서** 6.1

**목표** test 승격 후 사람 개입 없이 `main`에 머지된다.

**할 일**
- [ ] 주체 결정: GHA 또는 에이전트(12장 미결정 8번)
- [ ] GHA라면 GitHub App 토큰(기본 토큰으로 만든 PR은 워크플로를 실행하지 않음)
- [ ] `gh pr create` + `gh pr merge --auto --rebase`
- [ ] PR 본문에 yolo 배포 리포트, 라벨 `yolo`

**완료 기준** yolo 배포가 test 승격 후 자동으로 main에 머지된다.

### [T19] 3분 데모 리허설

**어디에 필요** 3분 라이브 데모를 실패 없이 끝내기 위한 연습.

**만들 것** 데모 사전 점검 체크리스트 문서와 리허설 2회 기록(걸린 시간, 문제점).

- **우선순위** P1 · **영역** 관측 · 문서 · 데모 · **담당** 미정
- **선행** `T2`, `T3`, `T9`, `T26` · **후속** 없음 · **설계 문서** 10장

**목표** 3분 안에 라이브 데모가 끝난다.

**할 일**
- [ ] 사전 점검: 클러스터, 도메인, 맥북 k3d, Funnel, runner, GHCR 접근
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
- [ ] 실패 로그 수집 → LLM 원인 요약 → PR 코멘트 또는 이슈
- [ ] (선택) 수정 PR 제안

**완료 기준** 배포 실패 시 원인 요약이 자동으로 달린다.

### [T26] Slack 버튼으로 머지 · 승인 · 승격

**어디에 필요** 승인자가 GitHub에 들어가지 않고 Slack 알림의 버튼만 눌러 PR 머지 → 테스트 배포 → 승격 → 운영 승인까지 진행한다. "투터치"를 데모에서 보여 주는 부분.

**만들 것** platform 레포의 `slack-bot/`(기존 봇 이식), PR 머지 버튼, 운영 승인 · 거절 버튼(GitHub App 승인 규칙), 단계별 알림 메시지.

- **우선순위** P1 · **영역** 파이프라인 (platform 재사용 워크플로) · **담당** 이소울
- **선행** `T5`, `T6` · **후속** `T19` · **설계 문서** 6.2, 6.6

**목표** janto 배포의 사람 조작(머지 · 승격 · 운영 승인)이 전부 Slack 버튼으로 끝나고, 누가 눌렀는지 감사 로그에 남는다.

**할 일**
- [x] 기존 봇(알림 + promote · abort · undo 버튼, Socket Mode)을 platform `slack-bot/`으로 이식, 대상 레포 · 워크플로 이름을 설정값으로
- [ ] PR 머지 버튼: janto PR의 검사 통과 · plan 결과를 알리고, 버튼을 누르면 봇이 머지 API 호출. 누른 사람을 PR 코멘트로 남김
- [ ] 운영 승인 · 거절 버튼: 봇을 GitHub App으로 만들고 demo-app `prod` environment의 승인 규칙(custom deployment protection rule)으로 등록, 버튼으로 승인 · 거절
- [ ] 누를 수 있는 사람 제한(`ALLOWED_USER_IDS`), 요청자를 감사 로그 `requested_by`에 기록
- [ ] 알림 흐름 정리: PR 준비 → 테스트 배포 완료(승격 · 취소) → 운영 승인 대기(승인 · 거절) → 운영 반영 결과(되돌리기)

**완료 기준** demo-app janto 배포 한 번을 GitHub 화면 없이 Slack 버튼만으로 prod까지 반영하고, 버튼을 누른 사람이 감사 로그에 남는다.

---

## 9단계

앞 단계의 선행 작업이 끝나면 아래 작업을 동시에 진행한다.

### [T10] yolo 배포 리포트

**어디에 필요** yolo는 리뷰가 없으니, 무엇을 안고 배포했는지 기록과 책임 소재를 남긴다.

**만들 것** 재사용 워크플로 `report.yml`: 리포트 JSON 생성 → S3 감사 로그 저장 → 문제가 있으면 `yolo-debt` 이슈 생성.

- **우선순위** P1 · **영역** 파이프라인 (platform 재사용 워크플로) · **담당** 배규태
- **선행** `T8` · **후속** 없음 · **설계 문서** 6.3, FR-12

**목표** yolo 배포마다 누가·언제·어떤 문제를 안고 배포했는지 남고, 문제가 있으면 이슈가 열린다.

**할 일**
- [ ] 리포트 JSON 스키마, 재사용 `report.yml`
- [ ] 수집: 실행자, 시각, SHA, 대상, compliance, template_version, 자동 수정 이력, 비차단 경고, AI 판단 근거, 승인 생략 여부
- [ ] 저장: 감사 로그(S3), 실행 요약. 문제가 있으면 demo-app에 `yolo-debt` 이슈

**완료 기준** 경고가 있는 yolo 배포 후 `yolo-debt` 이슈가 열린다.

---

## GitHub Project 등록 현황

- 이슈는 `one-tatchi-platform` 레포, 보드는 조직 프로젝트 **Softbank 2026 project**
- 등록된 이슈: T1~T25 (#1~#25), T26 (#35)
- 라벨: `P0`/`P1`/`P2`, `area:infra`/`area:pipeline`/`area:skill`/`area:docs`, `stage:N`
