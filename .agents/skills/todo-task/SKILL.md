---
name: todo-task
description: 원터치 배포 팀 작업 진행. docs/tasks.md에서 내 작업을 찾아 다음 할 일을 하고, 끝낸 항목을 체크해 같은 PR로 올린다. 이슈와 프로젝트 보드는 tasks.md를 따라 자동으로 맞춰진다. "내 할 일", "다음 작업", "T3 하자", /todo-task 같은 요청에 쓴다.
---

# todo-task

`docs/tasks.md`가 팀 작업의 유일한 기준이다. 이 순서를 따른다.

## 1. 최신 상태와 사용자 확인

1. `git pull --rebase`로 최신 `docs/tasks.md`를 받는다.
2. 사용자가 누구인지 확인한다: `gh api user -q .login` 또는 `git config user.name`.

| GitHub 로그인 | 이름 |
|---|---|
| silano08 | 원가연 |
| soulee-dev | 이소울 |
| hyeongrae-kim | 김형래 |
| baejun10 | 배준범 |
| baekyutae | 배규태 |

모르면 사용자에게 이름을 묻는다.

## 2. 내 작업 보여 주기

1. `docs/tasks.md`의 **역할 분담**에서 그 사람의 작업 번호를 찾는다.
2. 각 작업 섹션(`### [T번호]`)에서 남은 할 일(`- [ ]`)과 **선행** 작업을 읽는다.
3. 표로 보여 준다: 작업 · 우선순위 · 남은 할 일 수 · 선행이 끝났는지(선행 작업의 할 일이 모두 `- [x]`면 끝남).
4. 인자로 작업 번호(예: `T3`)를 받았으면 그 작업으로 바로 간다. 아니면 **P0이고 선행이 끝난 작업** 중 첫 번째를 추천하고 확인받는다.

## 3. 작업하기

0. `main`은 보호돼 있어 직접 push할 수 없다. `main`에서 브랜치를 만든다: `git switch -c t<번호>-<짧은-이름>` (예: `t3-onprem-k3d`).
1. 고른 작업의 **어디에 필요 · 만들 것 · 목표 · 완료 기준**과 관련 설계 문서 절(`docs/plan.html`)을 읽고 시작한다.
2. 남은 할 일을 위에서부터 하나씩 한다. 한 번에 하나.
3. 다른 사람 작업 영역(다른 담당의 파일이나 할 일)을 바꿔야 하면 멈추고 사용자에게 알린다.

## 4. 체크하고 PR 올리기

1. 끝낸 할 일을 `- [ ]` → `- [x]`로 바꾼다. 일부만 했으면 체크하지 않고 할 일 문장 끝에 `(진행 중: 무엇까지)`를 붙인다.
2. 할 일이 바뀌었거나 새로 생겼으면 그 작업 섹션을 고친다. 진행 상황은 `docs/tasks.md`에 적는다.
   이슈 본문의 **할 일** 체크리스트도 같이 맞춘다: `.agents/skills/todo-task/scripts/issue-sync.sh T3` (할 일을 다른 작업으로 넘겼으면 두 작업 모두)
3. 코드 변경과 체크 변경을 **같은 커밋**에 넣는다. 메시지 앞에 작업 번호: `[T3] k3d 클러스터 생성 스크립트 추가`
4. 이슈 번호는 `gh issue list --search "[T3]" --state all`로 찾는다. PR 본문에 `Refs #번호`, 할 일이 다 끝나고 **완료 기준**을 만족하면 `Closes #번호`.
5. 사용자에게 확인받은 뒤 브랜치를 push하고 PR을 연다: `gh pr create --title "[T3] …" --body "…"`.
   - 브랜치 이름은 작업 번호로 시작한다(`t3-…`). 어떤 작업인지 이름만 보고 알 수 있게 한다.
   - PR 본문 첫 줄에 연결된 작업을 이슈 링크로 적는다: `**작업:** [T3 온프레미스 구현체](https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/one-tatchi-platform/issues/6)`
   - demo-app처럼 다른 레포에 올리는 PR도 같다. 링크는 one-tatchi-platform 이슈로 걸고, `Refs`는 `SoftBank-Hackathon-2026-Team-Amethyst/one-tatchi-platform#6` 형식으로 쓴다.
6. 자동 머지를 건다: `gh pr merge --auto --squash`. CI(`terraform` · `charts` · `iac-scan`)가 실패하면 고쳐서 같은 브랜치에 다시 push한다.

## 5. 이슈와 보드는 자동

`docs/tasks.md`가 main에 머지되면 `sync-tasks` 워크플로가 이슈와 [프로젝트 보드](https://github.com/orgs/SoftBank-Hackathon-2026-Team-Amethyst/projects/1)를 맞춘다. 보드 카드와 이슈 본문은 손으로 고치지 않는다.

| tasks.md 상태 | 보드 | 이슈 |
|---|---|---|
| 하나도 체크 안 됨 | Backlog (Ready면 그대로) | 열림 |
| 일부 체크 | In progress (In review면 그대로) | 열림 |
| 전부 체크 | Done | 자동으로 닫힘 |

- 할 일을 다른 작업으로 옮기거나 문장을 바꿔도 다음 머지 때 이슈 본문이 다시 만들어진다.
- 새 `### [T번호]` 섹션을 추가하면 이슈가 생기고 보드에 올라간다. 작업 번호는 바꾸거나 다시 쓰지 않는다(이슈와 짝을 맞추는 열쇠다).
- 워크플로 경고(담당이 다름, 닫힌 이슈에 남은 할 일 등)가 보이면 tasks.md를 고쳐 맞춘다.

## 하지 않는 것

- 체크만 하고 실제 작업이나 검증을 건너뛰지 않는다. 완료 기준을 확인하지 못했으면 그렇게 말한다.
- `docs/plan.html`에 진행 상황을 적지 않는다(설계 문서다).
- 다른 사람 작업의 체크박스를 바꾸지 않는다. 보드 카드와 이슈 본문은 직접 고치지 않는다.
