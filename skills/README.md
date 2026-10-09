# 에이전트 스킬

개발자가 로컬에서 실행하는 진입점이다. 스킬은 대상 레포(demo-app)를 분석해 배포 산출물을 만들고 브랜치로 올린다. **스킬은 아무것도 apply하지 않는다.** 인프라 반영과 릴리스는 머지 뒤 배포 파이프라인(재사용 워크플로)이 한다. 설계 문서 6.1, 6.3.

| 스킬 | 역할 |
|---|---|
| `/janto-deploy` | 정석 진입점. 브리프 → 분석 → 산출물 → **기능 브랜치 + main PR**. 리뷰 지점 1(추천 인프라)에서 사람 확인 |
| `/yolo-deploy` | 예외 진입점. 질문 없이 분석 → 산출물 → **`yolo/<기능>` push** → 검사 · test 배포를 지켜본다. 검사 실패는 AI가 고쳐 다시 push (최대 3회, T14) |
| `deploy-analyze` | 브리프 질문 5개(T15) + 분석기 5개(코드베이스 · 서비스 · 트래픽 · 보안 · 예산) → `.deploy/report.md`, `.deploy/config.yaml` |
| `deploy-provision` | 산출물 생성(Dockerfile, 값 파일, `infra/envs/<대상>`, `.deploy/config.yaml`, `.deploy/smoke.json`, 워크플로 호출부). 템플릿은 태그로만 참조 |
| `deploy-release` | 파이프라인의 승격(`rollout.yml promote`)을 요청한다 |
| `deploy-rollback` | 파이프라인의 취소 · 되돌리기(`rollout.yml abort \| undo`)를 요청한다 |

사전 검증 레포의 `deploy-relocate`(배포 대상 간 이전)는 옮기지 않았다. 운영 중 서비스의 이전은 비목표다(설계 문서 3장).

## 설치

스킬 원본은 이 폴더다. Claude Code와 Codex는 개인 스킬 경로에서 읽으므로 심볼릭 링크로 설치한다.

```sh
scripts/install-skills.sh            # ~/.claude/skills/<이름>, ~/.agents/skills/<이름> → 이 폴더
scripts/install-skills.sh --remove   # 링크만 지운다
```

이 레포를 `git pull`하면 설치본도 같이 바뀐다. 대상 앱(demo-app) 폴더에서 `/janto-deploy` 또는 `/yolo-deploy`를 실행한다.

## 계약

- **쓰기 범위**: 대상 레포만. platform 레포, 클라우드, 클러스터, GitHub 설정(Variables · environment)은 건드리지 않는다.
- **템플릿은 태그로 참조**: 워크플로 `uses: …@vX.Y.Z`, 모듈 `?ref=vX.Y.Z`, 차트 `chart-version: X.Y.Z`. 세 버전은 `.deploy/config.yaml`의 `template_version` 하나로 맞춘다(루트 README "버전 표기 규칙").
- **템플릿 본문은 고치지 않는다**: 검사 단계 · App Chart 보안 설정 · Terraform 모듈은 platform에 있다. 스킬은 변수 값과 호출부만 만든다.
- **비밀값을 쓰지 않는다**: 값 파일 · tfvars · 브리프에 토큰 · 비밀번호 · 접속 문자열을 적지 않는다. DB 접속 정보는 Terraform이 만든 k8s Secret(`<서비스>-db`)으로 들어간다.
- **`compliance`는 사람이 정한다**: `deploy-analyze`의 저장 스크립트가 브리프 답변으로 한 번 쓴다. 바꾸려면 janto PR(CODEOWNERS 리뷰). yolo 경로에서 바꾸면 검사(`config-guard`)가 실패한다.
- **`.deploy/config.yaml`에는 파이프라인 값만**(`template_version`, `compliance`). 이 파일은 CODEOWNERS 리뷰 대상이라, 스킬 인계값(`target`, `services`)은 `.deploy/plan.yaml`에 둔다. 그래야 janto 산출물 PR이 오너 리뷰 없이 머지된다.
- **기록**: 스킬 실행마다 `.deploy/log/<YYYYMMDD-HHMMSS>-<스킬>.md`를 남긴다. 중간 산출물(`.deploy/brief.md`, `.deploy/analysis/`, `.deploy/report.md`, `.deploy/plan.yaml`)도 레포에 커밋한다.

## 두 경로의 차이

| | `/janto-deploy` (정석) | `/yolo-deploy` (예외) |
|---|---|---|
| 브리프 | 질문 5개를 묻는다 | 묻지 않는다. 기존 브리프를 재사용하고, 없으면 전부 "모름"으로 저장(규제 미정 → `regulated`) |
| 리뷰 지점 1 (추천 인프라) | 멈추고 승인받는다 | 자동 승인하고 기록에 남긴다 |
| 브랜치 | `deploy/<기능>` → main PR | `yolo/<기능>` push |
| 검사 실패 | 사람이 고친다 | AI가 앱 코드 · Dockerfile · 값 파일만 고쳐 다시 push (최대 3회) |
| 다음 단계 | 리뷰어가 PR(검사 · plan 코멘트)을 보고 머지 → main → test → prod(승인) | push 즉시 test. AI 승격 판단(T7). main PR 자동 생성은 T8 |

## 검증

- 자동 테스트: `uv run --no-project --with-requirements skills/deploy-analyze/requirements.txt python -B -m unittest discover -s skills/deploy-analyze/tests`
- 산출물 검사: `skills/deploy-provision/scripts/check-artifacts.sh <대상 레포 경로>` (자리표시자 잔존, 버전 표기 일치, 필수 파일)
- 대화 검증: 임시 앱 폴더에서 `/janto-deploy`를 실행해 PR이 열리고 `template_version`과 세 참조가 같은 태그인지 확인한다.
