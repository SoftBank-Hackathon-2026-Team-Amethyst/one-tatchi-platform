# approval-timeout

운영 승인 요청이 정해진 시간 안에 처리되지 않은 워크플로 실행을 취소하고 Slack에 알린다. 재사용 워크플로 `.github/workflows/approval-timeout.yml`이 `reap.py`를 돌린다.

- 대상: `status=waiting`인 실행 중 `workflow`(기본 `deploy.yml`) 것. 대기 시작 시각은 `waiting` 상태인 job의 생성 시각, 없으면 실행 시작 시각.
- `max-wait-minutes`(기본 60) 이상이면 `gh run cancel`. `dry-run`이면 적기만 한다.
- 출력: `count`, `details`(Slack mrkdwn), `cancelled`(실행 ID JSON).
- 대상 레포 호출부: `deploy-provision` 템플릿 `approval-timeout.yml`(15분마다 schedule + 수동 실행). 호출 레포의 토큰에 `actions: write`가 필요하다.

테스트: `python3 -B -m unittest discover -s .github/actions/approval-timeout/tests -v`
