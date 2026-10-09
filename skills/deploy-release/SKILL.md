---
name: deploy-release
description: Blue-Green 배포에서 green(새 버전)으로 트래픽을 넘기는 승격을 파이프라인에 요청한다. 사용자가 "승격해", "promote", "트래픽 넘겨"라고 하거나 test · prod의 Paused 릴리스를 확인한 뒤 쓴다. 스킬은 클러스터를 직접 조작하지 않는다.
---

# deploy-release

대상 레포의 `rollout` 워크플로(platform `rollout.yml` 호출부)에 `promote`를 요청한다. 실제 조작은 파이프라인이 클러스터 자격증명으로 한다. 스킬에는 클러스터 권한이 없다.

## 전제

- 대상 레포에 `.github/workflows/rollout.yml`이 있다(T26). 없으면 `deploy-provision`을 다시 돌려 만들거나, Slack 알림의 promote 버튼을 쓰라고 안내한다.
- `gh auth status` 성공. `gh workflow run`에는 `workflow` 권한이 필요하다.

## 순서

1. **대상 확정.** 환경(`test` | `prod`), 배포 대상(`aws` | `onprem`), 서비스(`all` 또는 Rollout 이름). 사용자가 말하지 않은 것은 묻는다. prod 승격은 사람의 결정이므로 요청 문장을 그대로 확인받는다.
2. **상태 확인.** 그 환경의 최근 `deploy` 실행 요약에서 green이 Paused인지, AI 승격 판단(T7) 결과와 근거가 무엇인지 읽는다.
   ```sh
   gh run list --workflow deploy.yml --limit 5 --json databaseId,headBranch,conclusion,createdAt
   gh run view <id>            # 요약의 "주소" · "AI 판단" 절
   ```
   판단이 abort인데 승격을 요청하면 그 근거를 보여 주고 다시 확인받는다.
3. **요청.**
   ```sh
   gh workflow run rollout.yml -f action=promote -f release=<all|서비스> -f target=<aws|onprem> -f environment=<test|prod> -f requested_by="$(gh api user -q .login)"
   run=$(gh run list --workflow rollout.yml --limit 1 --json databaseId -q '.[0].databaseId')
   gh run watch "$run" --exit-status
   ```
4. **확인.** 실행 요약에서 승격 결과와 활성 주소를 읽고 사용자에게 전한다. 실패하면 `gh run view "$run" --log-failed`의 원인을 정리한다. 트래픽은 바뀌지 않았으므로 되돌릴 것은 없다.
5. **기록.** `.deploy/log/<YYYYMMDD-HHMMSS>-release.md`: 환경 · 대상 · 서비스 · 커밋 · 요청자 · 결과 · 소요 시간. 작업 브랜치가 있으면 그 브랜치에, 없으면 사용자에게 커밋 여부를 묻는다.

## 하지 않는 것

- `kubectl argo rollouts promote`, `helm`, 클라우드 CLI. 클러스터 자격증명을 받거나 저장하지 않는다.
- prod `environment` 승인 대신 누르기. 승인은 GitHub에서 사람이 한다.
- 승격 뒤 문제가 생기면 `deploy-rollback`.
