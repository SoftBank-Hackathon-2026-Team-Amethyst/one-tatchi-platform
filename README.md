# 완땃찌(원터치) 배포 대 출격!

> `one-tatchi-platform`

<p align="center">
  <img src="docs/assets/one-touch-deploy.png" alt="원터치 배포 버튼을 누르는 토끼" width="560">
</p>

**로컬에서 만든 웹앱을 AI 에이전트가 분석하고, 컴플라이언스 검사를 통과한 변경만 클라우드(AWS · GCP)와 온프레미스에 배포한다.**

금융권처럼 규제가 있는 곳에는 멀티클라우드와 **출구전략**이 필요하지만, 매번 사람이 설계하기는 어렵다.
그래서 정적분석 · 테스트 · 취약점 검사 같은 필수 항목을 **기본 템플릿**으로 먼저 깔아 둔다.
그 위에서 AI 에이전트가 서비스를 분석해 배포 파일을 만들고, 배포 파이프라인이 규칙대로 반영한다.

이 레포는 **기본 템플릿과 에이전트 스킬**을 담는다. 배포 대상 앱은 [`demo-app`](https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/demo-app)에 있다.

## 구성

| 구성 | 설명 |
|---|---|
| `/janto-deploy` | 정석 경로. 질문 → 분석 → 배포 파일 생성 → `main` PR → 사람 리뷰 → 테스트 → 운영 |
| `/yolo-deploy` | 예외 경로. 리뷰 없이 `yolo/*` 브랜치로 테스트까지 가고, 검사가 실패하면 AI가 최대 3회 고친다 |
| 기본 템플릿 | Terraform 모듈, App Chart(Helm), 재사용 워크플로. AI는 변수만 채우고 본문은 고치지 않는다 |
| 배포 파이프라인 | 검사(정적분석 · 테스트 · 취약점 · IaC) → 테스트 배포(Blue-Green) → AI 승격 판단 → 운영 승격. 규제 대상이면 운영 앞에서 사람 승인 |
| `slack-bot/` | 배포 결과를 Slack으로 알리고, 버튼으로 승격 · 롤백을 요청한다 |

## 레포 구조

```
one-tatchi-platform/
├── modules/                    # Terraform 기능 계약 + 벤더별 구현체
│   ├── network/        aws/ gcp/ onprem/
│   ├── cluster/        aws/ gcp/ onprem/
│   ├── cluster_addons/ aws/ gcp/ onprem/
│   ├── registry/       aws/ gcp/ onprem/
│   ├── database/       aws/ gcp/ onprem/
│   ├── ci_identity/    aws/ gcp/ onprem/
│   ├── observability/  aws/ gcp/ onprem/
│   └── secret/         aws/ gcp/ onprem/
├── charts/
│   ├── app/                    # App Chart: 릴리스 전략 + 보안 설정 강제. 태그 시 GHCR(OCI)에 배포
│   ├── service-base/           # 서비스 네임스페이스 + DB 시크릿 동기화
│   └── platform-config/        # 클러스터 공통 설정
├── .github/
│   ├── workflows/              # 재사용: checks · infra · deploy / 이 레포용: ci · release
│   └── actions/                # 공통 액션 (감사 로그, Slack 알림 등)
├── bootstrap/                  # state 버킷 · 감사 로그 버킷 · OIDC 역할 (최초 1회)
├── skills/                     # 에이전트 스킬 (/janto-deploy, /yolo-deploy, 분석기)
├── slack-bot/                  # 배포 알림 · 조작 Slack 봇
├── scripts/                    # 보조 스크립트
└── docs/                       # ADR, 설계 문서
```

## demo-app이 이 레포를 쓰는 방법

demo-app은 템플릿을 **태그로 고정해 참조**만 한다. 그래서 에이전트가 템플릿 본문이나 검사 단계를 고칠 수 없다.

| 무엇을 | 어떻게 |
|---|---|
| 재사용 워크플로 | `uses: SoftBank-Hackathon-2026-Team-Amethyst/one-tatchi-platform/.github/workflows/deploy.yml@v1.0.0` |
| Terraform 모듈 | `source = "git::https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/one-tatchi-platform.git//modules/cluster/aws?ref=v1.0.0"` |
| App Chart | `helm upgrade … oci://ghcr.io/softbank-hackathon-2026-team-amethyst/charts/app --version 1.0.0` |

세 버전은 demo-app의 `.deploy/config.yaml` → `template_version` 하나로 맞춘다.

## 재사용 워크플로

| 워크플로 | 하는 일 |
|---|---|
| `checks.yml` | 정적분석(ruff · lint) · 테스트(pytest, Postgres) · 빌드 · 의존성 취약점(Trivy fs) · IaC 규정(Trivy config). 끄는 입력이 없다 |
| `infra.yml` | Terraform fmt · validate · plan(PR 코멘트) / apply. 감사 로그 · Slack 알림 |
| `deploy.yml` | 이미지 빌드(SHA 태그) → App Chart(OCI)로 `helm upgrade` → green이 Paused가 될 때까지 대기 → 주소 · 감사 로그 · Slack(promote/abort 버튼) |

이 레포 자체는 `ci.yml`(모듈 validate · 차트 lint · IaC 검사)과 `release.yml`(태그 `vX.Y.Z` → 차트를 GHCR에 push, 메이저 태그 `v1` 이동)로 관리한다.

## 팀원 작업 방법

1. [`docs/tasks.md`](docs/tasks.md)에서 자기 이름과 맡은 작업을 찾는다.
2. 브랜치에서 작업하고 PR로 올린다. `main`은 보호돼 있어 CI가 통과해야 머지된다(리뷰 승인 불필요).
3. 끝낸 할 일을 `- [x]`로 체크해 코드와 같은 PR에 넣는다. 커밋 메시지와 PR 제목 앞에 `[T번호]`.
4. Claude Code에서는 `/todo-task`, Codex에서는 `$todo-task`로 이 과정을 스킬로 진행할 수 있다.

## 문서

- [설계 문서](docs/plan.html): 브라우저로 열어 본다 (다이어그램은 Mermaid로 그려진다)
- [해야 할 일](docs/tasks.md): 단계별 작업과 역할 분담
- [배포 브리프 스킬](skills/deploy-analyze/SKILL.md): 질문 5개로 배포 정보를 수집하고 브리프와 초기 규제 설정을 저장. 설치·실행·테스트 방법 포함

## 작업 현황

[Softbank 2026 project](https://github.com/orgs/SoftBank-Hackathon-2026-Team-Amethyst/projects/1) 보드와 이 레포의 이슈를 본다.
