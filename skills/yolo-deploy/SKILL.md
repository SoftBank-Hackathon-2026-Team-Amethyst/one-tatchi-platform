---
name: yolo-deploy
description: 웹앱을 예외 경로(yolo)로 테스트 환경까지 한 번에 올린다. 질문과 리뷰 없이 분석 → 배포 산출물 생성 → yolo/<기능> 브랜치 push → 검사 · test 배포를 지켜보고, 검사가 실패하면 앱 코드를 고쳐 다시 push(최대 3회). 사용자가 명시적으로 "yolo", "/yolo-deploy", "리뷰 없이 바로 테스트"를 요청할 때만 쓴다. 정석 경로는 janto-deploy.
---

# yolo-deploy

대상 레포(현재 폴더)를 분석해 산출물을 만들고 **`yolo/<기능>` 브랜치에 push**한다. push가 곧 test 배포다. 이 스킬도 apply · 릴리스 · 머지를 직접 하지 않는다. 검사는 어떤 경우에도 생략할 수 없다.

## 전제

`janto-deploy`와 같다: 대상 레포 루트, GitHub 원격, `gh auth status` 성공, 깨끗한 작업 트리, `deploy-analyze` · `deploy-provision` 설치.

## 순서

사용자가 쓰는 언어로 문서를 쓴다. 시작 시각을 기록한다. 아래 단계 중 사용자에게 묻는 단계는 없다.

0. **준비.** `git fetch origin && git switch -c yolo/<기능> origin/main`. `<기능>`은 짧은 영문 kebab-case. 반드시 `yolo/`로 시작해야 test로 배포된다.
1. **분석** → `deploy-analyze` (yolo 모드).
   - `.deploy/brief.md`가 있으면 그대로 재사용한다.
   - 없으면 질문하지 않고 다섯 항목을 모두 **명시적 건너뛰기 값**(`null` · `unknown` · `auto`)으로 저장한다. 규제 여부가 미정이므로 `compliance`는 `regulated`가 되고 운영 반영에는 사람 승인이 필요하다. 이 스킬을 실행한 것이 건너뛰기의 승인이다. 코드에서 규모 · 예산 · 규제를 추측해 답변으로 적지 않는다.
   - 분석기는 브리프가 비어 있는 항목을 코드와 문서로 추정하고 모두 보고서의 **가정** 절에 적는다.
2. **리뷰 지점 1 자동 승인.** 추천을 보여 주지 않고 진행한다. 보여 줬을 내용(대상 · 월 비용 · 가정)을 실행 기록에 적는다. 예산 범위를 넘는 추천이면 비용이 가장 낮은 구성으로 바꾸고 그 사실을 적는다.
3. **산출물** → `deploy-provision`. 로컬 검증(이미지 빌드, lint · test, `terraform fmt` · `validate`, `check-artifacts.sh`)이 실패하면 고친다(수정 범위는 아래 "고칠 수 있는 것"). 템플릿 본문은 고칠 수 없다.
4. **커밋 · push.** `[yolo] <무엇을>` 메시지로 커밋하고 `git push -u origin yolo/<기능>`. push가 `checks` → `test` 배포를 일으킨다.
5. **지켜보기.** 이 브랜치의 `deploy` 워크플로 실행을 찾아 끝날 때까지 기다린다.
   ```sh
   run=$(gh run list --workflow deploy.yml --branch "yolo/<기능>" --limit 1 --json databaseId -q '.[0].databaseId')
   gh run watch "$run" --exit-status
   ```
   - **검사(`checks`) 실패**: 수정 루프(아래). 고친 뒤 같은 브랜치에 다시 push하고 5번으로 돌아간다. 최대 3회.
   - **배포(`test`) 실패**: 수정 루프 대상이 아니다. `gh run view "$run" --log-failed`를 읽어 원인을 정리해 보고하고 멈춘다.
   - 성공: `gh run view "$run"`의 요약에서 test 주소(또는 미리보기 port-forward 명령)와 AI 승격 판단 결과를 읽는다.
6. **기록.** `.deploy/log/<YYYYMMDD-HHMMSS>-yolo.md`에 FR-12의 항목을 적는다: 실행자, 시각, 커밋 SHA, 배포 대상(test), `compliance`와 운영 승인 생략 여부, 자동 승인한 리뷰 지점의 내용과 가정, 처음 실패했다가 AI가 고친 항목(실패한 검사 · 고친 파일 · 회차), 차단하지 않은 경고, 승격 판단 결과. 같은 브랜치에 커밋 · push한다(이 push도 test를 다시 배포한다. 기록만 바뀌었으면 이미지 태그만 바뀌고 내용은 같다).
7. **마무리 보고.** test 주소, 승격 판단, 고친 것, 남은 경고, 그리고 다음 단계를 한 번에 말한다. main 반영(PR 자동 생성 · 자동 머지)은 T8이 정한다. 그때까지는 사용자가 `gh pr create --base main --head yolo/<기능>`으로 PR을 열어 janto 경로로 머지한다.

## 수정 루프 (검사 실패 시)

FR-11. 상세 절차는 T14(김형래)가 보강한다. 바뀌지 않는 규칙:

- 실패 로그는 `gh run view "$run" --log-failed`로 읽는다. 실패한 job(`node` · `python` · `image-scan` · `vuln-scan` · `secret-scan` · `license-scan` · `iac-scan` · `config-guard`)별로 원인을 찾는다.
- **고칠 수 있는 것**: 앱 코드, `<서비스>/Dockerfile` · `.dockerignore`, `deploy/**/values*.yaml`, `infra/envs/<대상>/terraform.tfvars`, `.trivyignore`(근거 주석 필수).
- **고치면 중단**: 테스트 코드 삭제 · 비활성화, `.github/workflows/*`(호출부 · 입력), `.deploy/config.yaml`의 `compliance`, `.github/CODEOWNERS`, `pnpm lint`/`ruff` 설정 완화. 이런 수정으로만 통과할 수 있으면 멈추고 사람에게 넘긴다.
- 회차마다 "무엇이 실패했고 무엇을 고쳤는지"를 커밋 메시지와 실행 기록에 남긴다.
- 3회 모두 실패하면 시도한 수정과 남은 오류를 정리해 보고하고 멈춘다. 결과는 `yolo/*` 브랜치와 test에만 남으므로 운영에는 영향이 없다.

## 하지 않는 것

- 사용자에게 질문. 브리프 · 리뷰 지점 · 비용 초과 · 경고 모두 기록으로 대신한다.
- `terraform apply`, `helm`, `kubectl`, `docker push`, 클라우드 CLI 쓰기.
- main 직접 push, main PR 자동 머지(T8 전까지), prod 승인 · 승격 조작.
- `compliance`를 `none`으로 바꾸는 일. yolo 경로에서는 `config-guard`가 막는다.
