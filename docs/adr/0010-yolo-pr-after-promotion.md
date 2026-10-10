# ADR 0010: test 승격 뒤 GitHub Actions가 yolo PR을 만든다

- 상태: 결정
- 관련: T8, T5, T13

yolo의 main 반영은 로컬 스킬이 종료돼도 이어져야 한다. 재사용 `deploy.yml`은
`yolo-auto-merge: true`일 때 모든 서비스의 Healthy 상태, stable/current 해시,
stable ReplicaSet의 이미지 SHA를 확인한다. 확인 실패·abort·manual 배포에는 PR을 만들지 않는다.

별도 `yolo-pr` job은 GitHub App(`BOT_CLIENT_ID`, `BOT_PRIVATE_KEY`)으로 PR을 생성하거나
기존 PR의 자동 보고서 영역을 갱신한다. App은 Contents/Pull requests 쓰기,
Actions 읽기 권한이 필요하고 워크플로 변경이 포함된 PR은 Workflows 쓰기도 필요하다.
기본 GITHUB_TOKEN으로 만든 PR은 후속 CI가 시작되지 않으므로 쓰지 않는다.

main 필수 검사 설정이 없어도 검사를 생략하지 않는다. 같은 head의 `pull_request` 이벤트
deploy 실행과, infra 변경 시 존재하는 infra 워크플로가 성공해야 자동 머지를 요청한다.
PR 이미지 검사가 20분 이상 걸린 실검증 결과를 반영해 대기는 최대 45분이며, 브랜치가 바뀌면 해당 실행은 멈춘다. `--match-head-commit`으로
승격한 head에 대해서만 `gh pr merge --auto --rebase`를 요청한다. 리뷰 규칙은 우회하지 않으며,
리뷰 대기가 있으면 GitHub의 auto-merge 대기 상태로 남는다. `yolo-pr` job 제한은 준비·API 호출 여유를 포함해 50분이다. 대기 중 추가 push에도 검사를
강제하려면 레포의 필수 검사 규칙을 설정해야 한다. 설정은 레포 관리자가 담당한다.

GitHub rebase merge는 SHA를 유지하지 않는다. 따라서 main push에서 해당 SHA에 연결된
merged PR의 같은 레포·main base·yolo head·yolo 라벨을 확인해 `promote-mode: branch`를
auto로 해석한다. main의 새 SHA로 test를 다시 검증하고 그 이미지를 prod에 쓴다.
일반 janto main과 workflow_dispatch는 manual이다. regulated 운영 승인은 계속 별도로 받는다.

`target·services`는 `.deploy/plan.yaml`에, CODEOWNERS 보호 값은 `.deploy/config.yaml`에 둔다.
기존 config를 최초 정리할 때는 리뷰가 필요하지만 이후 계획만 바꾸는 PR은 config를 건드리지 않는다.
스킬은 실행 기록을 최초 push와 수정 회차에 포함한다. 성공 뒤 기록용 재push는 자동 머지·브랜치
삭제와 경합하므로 하지 않고, 정확한 SHA·배포 결과·판단 artifact 링크는 Actions와 PR에 남긴다.

참고: [GitHub의 rebase 동작](https://docs.github.com/en/pull-requests/reference/pull-request-merges#rebase-and-merge-your-commits).

로컬 스킬은 push 실행 전체(초기 검사·test 배포·PR 검사)를 최대 90분 관찰한다.
`yolo-pr` 성공은 자동 머지 **요청** 성공이며 실제 머지 완료와 다르다. 스킬은 같은 SHA의
main PR을 즉시 조회하고, OPEN이면 10초 간격으로 최대 5회(최초 포함) 조회한다.
MERGED만 머지 완료, CLOSED는 중단, 계속 OPEN이면 `waiting_merge`로 보고한다.
`watch` 재개 시 저장된 PR만 다시 조회하며 Actions 재실행이나 머지를 요청하지 않는다.
조회마다 head SHA와 원격 브랜치를 검증하고, 브랜치 삭제는 같은 SHA의 MERGED로만 인정한다.
이 관찰은 실제 머지를 확인하지만 사람이 머지했는지 봇이 머지했는지는 판정하지 않는다.
