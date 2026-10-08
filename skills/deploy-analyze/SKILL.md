---
name: deploy-analyze
description: 웹앱 배포 전에 사용자 수, 예산, 데이터 취급, 배포 대상 선호, 가용성을 질문하고 배포 브리프와 초기 compliance 설정을 저장한다. 배포 준비나 브리프 수집 요청에 사용한다.
---

# 배포 브리프 수집

이 스킬은 배포 분석의 입력인 브리프를 수집한다. 코드·비용 분석이나 실제 배포는 호출한 배포 스킬의 후속 단계다.

## 진행 순서

1. [질문과 저장 계약](references/brief-format.md)을 읽는다.
2. 배포 대상 앱의 루트 경로를 확인하고, 기존 `.deploy/brief.md`와 `.deploy/config.yaml`이 있으면 읽는다. 플랫폼 저장소에 앱의 답변을 저장하지 않는다.
3. 아래 문서의 다섯 항목을 수집한다. 현재 대화에서 명확히 답한 항목은 재사용하고, 이전 브리프는 변경할 사항을 확인해 재사용한다. 코드만 보고 사용자 규모·예산·규제 여부를 추측하지 않는다.
4. 선택형 질문은 실행 환경이 제공하는 사용자 질문 도구(Claude Code의 `AskUserQuestion`)로 묻는다. 도구가 없으면 같은 문구를 대화로 묻고 응답을 기다린다. 다섯 항목을 한꺼번에 긴 설문으로 보여 주기보다 2~3개씩 묶는다. 예산과 규모는 직접 입력할 수 있게 한다.
5. 무응답·도구 취소·시간 초과는 건너뛰기로 간주하지 않는다. 사용자가 명시적으로 모름/건너뛰기를 선택했을 때만 문서의 기본값을 적용한다. 데이터 취급 답변이 모호하거나 서로 충돌하면 그 항목만 다시 확인한다.
6. 계약에 맞는 JSON을 임시 파일에 저장하고 아래 저장 스크립트를 실행한다. 의존성은 이 스킬의 `requirements.txt`에 있다. `<skill-dir>`은 현재 읽은 `SKILL.md`가 있는 실제 경로다.

   ```sh
   uv run --no-project --with-requirements "<skill-dir>/requirements.txt" python "<skill-dir>/scripts/write_brief.py" --project-root "<app-root>" --answers "<answers.json>"
   ```

7. 스크립트가 성공한 경우에만 두 출력 파일, 적용된 `compliance`, 미정 항목을 안내한다. 사용자에게 근거와 기본값이 보이도록 한다. 실패 시 오류 원인을 설명하고 해당 답변이나 경로를 바로잡는다.

## 기존 설정과의 충돌

- 최초 설정에서는 답변으로 `compliance`를 만든다. 기존 값이 같은 경우 설정 파일은 변경하지 않는다.
- 기존 값과 새 분류가 다르면 스크립트는 두 출력 파일을 모두 보존하고 실패한다. `config.yaml`을 삭제하거나 직접 수정해 재시도하지 않는다. 사용자에게 변경 필요를 알리고 사람이 검토하는 설정 변경으로 넘긴다.
- 규제 여부가 미정이면 승인 생략을 허용하지 않는 `regulated`를 적용하고, 브리프에 미정이라는 근거를 남긴다.
- 브리프 수집을 요청받은 것만으로 클라우드 변경, 커밋, push, PR, 배포를 실행하지 않는다. 이 스킬은 두 배포 모드에서 같은 수집·분류 규칙을 사용한다.

## 설치와 로컬 검증

이 디렉터리 전체를 Claude Code의 개인 스킬 경로 `~/.claude/skills/deploy-analyze/`에 설치한 뒤 대상 앱에서 `/deploy-analyze`를 실행한다. `skills/`는 배포 원본 위치이며 그 자체로 명령이 등록되는 위치는 아니다.

저장 로직 테스트는 플랫폼 저장소 루트에서 실행한다.

```sh
uv run --no-project --with-requirements skills/deploy-analyze/requirements.txt python -B -m unittest discover -s skills/deploy-analyze/tests -v
```

실제 대화 검증 절차는 [질문 계약의 검증 절](references/brief-format.md#검증)에 있다.
