---
name: deploy-rollback
description: Blue-Green 배포를 되돌린다. 승격 전이면 green을 버리는 abort, 승격 뒤면 직전 버전으로 돌리는 undo를 파이프라인에 요청한다. 사용자가 "롤백", "되돌려", "취소해", "이전 버전으로"라고 하면 쓴다. 급한 상황이므로 질문을 최소로 한다.
---

# deploy-rollback

대상 레포의 `rollout` 워크플로에 `abort` 또는 `undo`를 요청한다. 실제 조작은 파이프라인이 한다.

| 상황 | action | 결과 |
|---|---|---|
| green이 Paused(승격 전) | `abort` | green을 내리고 blue(현재 버전)가 그대로 서비스 |
| 승격한 뒤 문제 | `undo` | 직전 릴리스로 트래픽을 되돌린다 |

## 순서

1. **상태 확인.** 환경 · 대상 · 서비스를 사용자 말에서 정하고(없으면 한 번만 묻는다), 최근 `deploy` · `rollout` 실행 요약으로 지금 어떤 버전이 트래픽을 받고 green이 Paused인지 읽는다. 파일(`.deploy/log`)이 아니라 실행 기록을 믿는다. 승격 전이면 `abort`, 뒤면 `undo`.
2. **요청.** 사용자의 롤백 요청이 승인이다. 다시 묻지 않는다.
   ```sh
   gh workflow run rollout.yml -f action=<abort|undo> -f release=<all|서비스> -f target=<aws|onprem> -f environment=<test|prod> -f requested_by="$(gh api user -q .login)"
   run=$(gh run list --workflow rollout.yml --limit 1 --json databaseId -q '.[0].databaseId')
   gh run watch "$run" --exit-status
   ```
3. **확인.** 실행 요약의 결과와 활성 주소를 전한다. 실패하면 `--log-failed`의 원인을 정리하고, Slack 알림의 버튼으로 같은 조작을 할 수 있다고 알린다.
4. **스키마.** 두 릴리스 사이에 마이그레이션 SQL이 적용됐으면 DB 구조는 새 것으로 남는다(자동으로 되돌리지 않는다). 이전 버전이 새 구조에서 동작하는지 확인하라고 알린다.
5. **기록.** `.deploy/log/<YYYYMMDD-HHMMSS>-rollback.md`: 환경 · 대상 · action · 이유(사용자가 말했다면) · 결과 · 소요 시간.

## 되돌린 뒤

문제의 커밋은 `main`에 남아 있어 다음 머지가 같은 코드를 다시 배포한다. 원인을 고치거나 커밋을 revert하는 PR(janto 경로)이 필요하다고 알린다.

## 하지 않는 것

- 클러스터 직접 조작, 클라우드 CLI, 자격증명 저장.
- `main` 되돌리기 push. PR로 한다.
