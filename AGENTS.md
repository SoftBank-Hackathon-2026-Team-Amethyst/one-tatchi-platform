# 에이전트 작업 안내

이 레포는 원터치 배포의 기본 템플릿(Terraform 모듈, App Chart, 재사용 워크플로, bootstrap, 스킬)을 담는다. 배포 대상 앱은 `demo-app` 레포에 있다.

## 작업 전에

1. `docs/tasks.md`를 먼저 읽는다. 팀 작업 계획이고, 맨 위 **작업 규칙**을 따른다. 진행 상황의 기준은 프로젝트 보드(이슈)다.
2. 사용자 이름으로 **역할 분담**에서 맡은 작업을 찾고, **선행** 작업이 끝났는지 확인한다.
3. `main`은 보호돼 있다. 브랜치에서 작업하고 PR로 올린다(CI 통과 시 자동 머지, 리뷰 승인 불필요).
4. 커밋 메시지와 PR 제목 앞에 `[T번호]`. 끝낸 할 일은 PR 머지 후 **이슈에서** 체크한다(`python3 scripts/sync_tasks.py tick T번호 순번`). tasks.md 체크박스는 봇이 고친다.

이 순서는 `todo-task` 스킬에 정리돼 있다 (Claude Code `/todo-task`, Codex `$todo-task`).

## 설계 · 용어

- 설계 문서: `docs/plan.html`
- 템플릿 원칙: AI는 변수만 채우고 템플릿 본문은 고치지 않는다. demo-app은 이 레포를 태그(`v1.x.y`)로만 참조한다.

## 검증

- Terraform: `terraform fmt -check -recursive`, 모듈 폴더마다 `terraform init -backend=false && terraform validate`
- 차트: `helm lint charts/<차트>`
- 워크플로: CI(`ci.yml`)가 PR마다 같은 검사를 돌린다.
