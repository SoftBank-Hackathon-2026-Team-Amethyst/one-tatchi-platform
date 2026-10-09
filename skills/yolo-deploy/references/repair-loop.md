# yolo 수정 루프 도구

Python 3.10 이상, Git, 인증된 `gh`가 필요하다. 앱 저장소에서 실행하며 `--repo <로컬 경로>`로 다른 작업 디렉터리를 지정할 수 있다. 별도 LLM API는 사용하지 않는다. AI는 원인 분석과 코드 수정, 도구는 실행 추적과 커밋·push 전 검사를 맡는다.

## 시작

초기 산출물을 커밋·push한 뒤 깨끗한 `yolo/*` 브랜치에서 실행한다. 아래 경로와 검사 명령은 예시다. 코드베이스 분석에서 실제 경로와 검사 명령을 확인해 전달한다.

```sh
python3 "<skill-dir>/scripts/repair_loop.py" init \
  --source be/src --source fe/src \
  --dockerfile be/Dockerfile --dockerfile fe/Dockerfile \
  --value deploy/values-be.yaml --value deploy/values-fe.yaml \
  --check '["pnpm","--dir","be","lint"]' \
  --check '["pnpm","--dir","be","build"]' \
  --check '["pnpm","--dir","fe","lint"]' \
  --check '["pnpm","--dir","fe","build"]'
```

- `--source`: 앱 소스 파일 또는 폴더. 저장소 루트나 배포·인프라·공유 스크립트 폴더를 지정하지 않는다. 일반적인 소스 확장자만 허용하며 알 수 없는 형식은 자동 확대하지 않는다.
- `--dockerfile`: 서비스별 기존 `Dockerfile` 경로.
- `--value`: 기존 `deploy/**/values*.yaml|yml` 또는 `infra/envs/**/*.tfvars` 경로. 필요할 때만 지정한다.
- `--protect`: 비표준 이름의 테스트·fixture·검사 경로. 반복 지정 가능. 표준 테스트·설정·예외 경로는 자동 보호한다.
- `--check`: 저장소 루트에서 실행할 명령의 JSON 인자 배열. 테스트가 있는 앱은 테스트 명령도 포함한다. 셸 문자열을 실행하지 않으며, 명령당 최대 10분이다.

경로와 검사 명령은 이 실행 동안 고정된다. 기존 상태가 있으면 init은 재개만 하며 횟수나 범위를 바꾸지 않는다. 최초 push 이전의 산출물 생성은 수정 회차에 포함하지 않는다.

## 관찰과 수정

```sh
python3 "<skill-dir>/scripts/repair_loop.py" watch
# checks_failed일 때 log_path를 읽고 앱 코드의 원인을 수정한다.
python3 "<skill-dir>/scripts/repair_loop.py" retry \
  --reason "잘못된 반환 타입 때문에 실패한 타입 검사를 앱 코드 수정으로 해결" \
  --file be/src/routes/info.ts
python3 "<skill-dir>/scripts/repair_loop.py" watch
python3 "<skill-dir>/scripts/repair_loop.py" report
```

`watch`는 실행 생성 최대 2분, 선택된 실행 완료 최대 30분을 기다린다. 시간 초과로 원격 실행을 취소하지 않는다. 실행 ID·attempt가 바뀌거나 조건에 맞는 실행이 여러 개면 중단한다.

v1.14.0의 T8 자동 PR job은 앱 수정 대상이 아니다. 성공하면 같은 head SHA의 PR 주소·상태를 보고한다. 원격 브랜치가 사라졌다면 해당 job 성공과 같은 SHA의 PR 머지를 확인한 경우에만 정상 완료로 처리하며, 삭제된 브랜치를 다시 push하지 않는다.

| status | 다음 동작 |
|---|---|
| `ready` | 현재 SHA를 `watch` |
| `watching` | 중단된 관찰은 커밋과 작업 트리가 그대로일 때 `watch`로 재조회 |
| `checks_failed` | 로그 확인 → 허용 파일 최소 수정 → `retry` |
| `pending_push` | 새 수정 없이 인자 없는 `retry`로 같은 커밋 push 재시도 |
| `committing` | 커밋 중 중단·훅 변경 등 결과가 불명확함. 자동 재시도하지 않고 보고 |
| `complete` | 검사·test 배포 job 성공. AI 판단과 트래픽 승격은 실행 요약에서 별도 확인 |
| `stopped` 또는 `error` | 원인·현재 변경·실행 링크를 보고하고 중단 |

명령 종료 코드 0은 `checks_failed`에서도 나올 수 있다. 반드시 JSON status를 읽는다. 명령 오류는 종료 코드 1과 error를 반환하고 기존 상태를 보존한다. 로그 조회 오류가 있으면 새 앱 수정의 근거로 쓰지 않는다.

`retry`는 지정한 파일과 실제 변경이 일치해야 한다. 검사 전후의 staged·unstaged·untracked 변경, 초기 커밋 이후 누적 변경, 이름 변경의 양쪽 경로를 확인한다. 로컬 검사 실패는 커밋·push·회차 증가 없이 중단한다. 커밋 생성 직전에 회차를 예약하므로 커밋 훅 실패 등 불명확한 결과는 자동 재시도하지 않는다. push 응답만 실패한 경우는 만들어진 커밋을 재사용한다.

원본 로그와 상태는 `git rev-parse --git-path yolo-deploy` 아래에 저장하며 커밋하지 않는다. 수정 이력은 도구가 만든 `.deploy/log/<시각>-<초기 SHA>-yolo.md`에 넣어 수정 커밋과 함께 올린다. 최종 결과는 `report`와 사용자 응답으로 남기고 기록만을 위한 후속 push는 하지 않는다. 보고 시 원본 로그나 비밀값을 그대로 복사하지 않는다.

이 보호는 로컬 스킬의 수정·push 절차에 적용된다. 사람이 별도 Git 명령으로 만드는 변경까지 막는 서버 정책은 아니다. 공유 CI 정책 추가, main 자동 머지(T8), S3·yolo-debt 리포트(T10)는 이 도구의 범위 밖이다.
