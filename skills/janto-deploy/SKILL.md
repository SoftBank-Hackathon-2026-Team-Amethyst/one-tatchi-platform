---
name: janto-deploy
description: 웹앱을 정석 경로(ちゃんと)로 배포 준비한다. 브리프 질문 → 분석 → 배포 산출물 생성 → 기능 브랜치 push → main PR. 추천 인프라를 사람이 확인하는 리뷰 지점에서 멈춘다. 사용자가 "배포해", "배포 준비", "/janto-deploy"를 요청하면 쓴다. 리뷰 없이 바로 테스트 환경까지 가려면 yolo-deploy.
---

# janto-deploy

대상 레포(현재 폴더)를 분석해 배포 산출물을 만들고 **main PR**을 연다. 이 스킬은 apply · 릴리스 · 머지를 하지 않는다. 머지 뒤 파이프라인이 test → prod로 올린다.

## 전제

- 현재 폴더가 대상 레포의 루트이고 GitHub 원격이 있다. `gh auth status`가 성공한다.
- 작업 트리가 깨끗하다. 아니면 멈추고 사용자에게 커밋 또는 정리를 요청한다.
- 하위 스킬 `deploy-analyze`, `deploy-provision`이 같은 곳에 설치돼 있다(`scripts/install-skills.sh`). 이름으로 호출할 수 없으면 `../<스킬>/SKILL.md`를 읽고 따른다.

## 순서

사용자가 쓰는 언어로 대화하고 문서를 쓴다. 시작 시각을 기록한다.

0. **준비.** `git fetch origin && git switch -c deploy/<기능> origin/main`. `<기능>`은 짧은 영문 kebab-case(예: `deploy/first-deployment`, `deploy/add-worker`). `yolo/`로 시작하는 이름은 쓰지 않는다(yolo 경로가 된다).
1. **분석** → `deploy-analyze` (janto 모드). 브리프 질문 5개를 묻고 분석기 5개를 돌려 `.deploy/brief.md`, `.deploy/analysis/*.md`, `.deploy/report.md`, `.deploy/config.yaml`을 만든다.
2. **리뷰 지점 1: 추천 인프라.** `.deploy/report.md`의 추천(배포 대상, 구성, 예상 월 비용, 필요한 코드 수정, 가정)을 요약해 보여 주고 `AskUserQuestion`으로 승인 · 수정 · 중단을 받는다.
   - 수정: 바뀐 전제로 `.deploy/report.md`와 `.deploy/config.yaml`(`target`, `services`)을 고치고 같은 지점을 다시 보여 준다. `compliance`는 여기서 고치지 않는다(브리프 답변으로만 정해진다).
   - 중단: 브랜치를 남기고 멈춘다. 만든 파일 목록을 알린다.
3. **산출물** → `deploy-provision`. Dockerfile, 값 파일, `infra/envs/<대상>`, `.deploy/smoke.json`, 워크플로 호출부, CODEOWNERS를 만들고 로컬 검증(이미지 빌드, lint · test, `terraform fmt` · `validate`, `check-artifacts.sh`)을 통과시킨다. 실패하면 산출물이나 앱 코드를 고친다. 템플릿 본문은 고칠 수 없다.
4. **커밋 · push · PR.**
   - 커밋 메시지: `[deploy] <무엇을>` 한 줄 + 본문에 산출물 목록. 여러 커밋도 된다.
   - `git push -u origin deploy/<기능>`
   - `gh pr create --base main --title "[deploy] <기능 요약>" --body-file <본문>`. 본문에는 아래를 넣는다.
     - 추천 요약(대상 · 월 비용 · 가정)과 `.deploy/report.md` 링크
     - 만든 파일 목록과 코드 수정 이유
     - 리뷰어가 볼 것: `checks`(검사) 결과, `infra` 워크플로의 **terraform plan 코멘트** → 이것이 **리뷰 지점 2(변경 계획)**다
     - 머지 뒤 흐름: main → test 배포 → AI 승격 판단 결과를 Slack으로 받고 사람이 promote 버튼(**리뷰 지점 3**) → prod(`compliance: regulated`면 environment 승인)
   - 자동 머지는 걸지 않는다. 사람이 리뷰하고 머지한다.
5. **기록.** `.deploy/log/<YYYYMMDD-HHMMSS>-janto.md`에 실행자(`gh api user -q .login`), 시각, 브랜치 · 커밋, 배포 대상, 리뷰 지점 1의 결정, 단계별 소요 시간, PR 주소를 적어 같은 브랜치에 커밋 · push한다.
6. **마무리 보고.** PR 주소, 다음에 누가 무엇을 하는지(리뷰 · 머지 → 자동 배포 → Slack 버튼), 바뀌는 비용을 한 번에 말한다.

## 다시 실행할 때

이미 산출물이 있는 레포에서는 브리프를 재사용할지 확인한 뒤(`deploy-analyze`가 묻는다) 분석을 다시 하고, **달라진 파일만** 고친다. `template_version`은 올리지 않는다. 템플릿 버전 올리기는 `template-update` 워크플로의 PR이 맡는다.

## 하지 않는 것

- `terraform apply`, `helm`, `kubectl`, `docker push`, 클라우드 CLI 쓰기. 로컬 자격증명으로 무엇도 반영하지 않는다.
- platform 레포(템플릿) 수정. 워크플로 호출부의 `uses:`가 가리키는 파일은 읽기만 한다.
- `.deploy/config.yaml`의 `compliance`를 분석 결과로 바꾸는 일. `.github/CODEOWNERS` · 테스트 삭제 · 검사 입력 축소.
- GitHub Variables · environment · 브랜치 보호 설정 변경. 필요하면 PR 본문에 "사람이 할 일"로 적는다.
