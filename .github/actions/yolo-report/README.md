# yolo-report

yolo 배포 한 건이 **누가 · 언제 · 무엇을 · 어떤 문제를 안고** 배포됐는지 남기는 리포트다 (T10, 설계 문서 6.3 · FR-12).
yolo는 사람 리뷰 없이 test(규제 대상이 아니면 prod까지) 가므로, 리뷰 대신 기록을 남긴다.

리포트는 S3 감사 로그 버킷(Object Lock)에 JSON으로 남고, Actions 실행 요약에 표로 보인다.
갚아야 할 문제(`debt`)가 있으면 대상 레포에 `yolo-debt` 라벨 이슈를 연다.

## 파이프라인 연결

재사용 `deploy.yml`의 `yolo-report` job이 이 액션(`action.yml`)을 부른다. 대상 레포 호출부는 고치지 않아도 된다.

```
deploy (test, yolo push, promote-mode auto)
  ├─ 승격 → artifact yolo-promotion (T8) · promote-judgment-test (T7)
  └─ abort → promote-judgment-test만
        ↓ (성공 · 실패 모두)
yolo-report  ── 경고 스캔 → 리포트 → S3 저장 · 실행 요약 · yolo-debt 이슈 → 감사 로그 한 줄(action yolo-report)
        ↓ (성공해야)
yolo-pr (main PR · 자동 머지, T8)
```

- 실행 조건: `yolo-auto-merge: true`, test 환경, `yolo/*` 브랜치 push, 승격 모드 auto, deploy job이 성공 또는 실패로 끝났을 때. janto · main 배포에는 돌지 않는다.
- 리포트가 실패하면 `yolo-pr`이 돌지 않는다. 기록 없이 리뷰 없는 변경이 main에 들어가지 않게 한다.
- `environment: test`로 돈다. 감사 로그 버킷에 쓰는 AWS Deploy 역할은 main 또는 environment가 있는 job만 받는다.
- 토큰: 이슈는 봇 App(`vars.BOT_CLIENT_ID` · `secrets.BOT_PRIVATE_KEY`) 토큰으로 연다. App에 Issues 쓰기 권한이 있어야 한다.
- 입력: `deploy.yml`의 `report-scan-path`(기본 `.`) · `report-iac-path`(기본 `infra`)를 checks의 `scan-path` · `iac-path`와 같게 둔다.
- 결과 파일은 artifact `yolo-report`(`warnings.json` · `report.json`)로도 올린다.

## 리포트 형식

형식은 [`schema.json`](schema.json)(JSON Schema 2020-12)이 기준이다. 예시:

| 예시 | 상황 | 이슈 |
|---|---|---|
| [`examples/report-debt.json`](examples/report-debt.json) | AI 자동 수정 1회 + 새로 들여온 경고 1건(main에 원래 있던 경고 2건은 기록만), 규제 대상 | 연다 |
| [`examples/report-clean.json`](examples/report-clean.json) | 수정 없음, main에 원래 있던 예외 1건만, 규제 대상 아님 | 열지 않는다 |
| [`examples/report-partial.json`](examples/report-partial.json) | 경고 스캔 · 판단 근거 수집 실패 | 연다 |

예시의 CVE · 패키지 · 실행 ID는 설명용 합성 값이다.

### 필드와 출처

| 필드 | 내용 | 가져오는 곳 |
|---|---|---|
| `report_id` | `<run_id>-<run_attempt>` | GitHub Actions 실행 정보 |
| `deploy` | 실행자 · 브랜치 · SHA · 대상 · 환경 · compliance · template_version · 실행 링크 · test 승격 여부 | Actions 실행 정보, 배포한 커밋의 `.deploy/config.yaml`, test 승격 확인 결과(`yolo-promotion.json`, T8) |
| `repairs` | AI 자동 수정 회차 · 파일 · 사유 · 수정 커밋, 이력 파일 | 수정 커밋 `[yolo] 검사 실패 자동 수정 N/3`(제목) · 사유(본문), `.deploy/log/<시각>-<SHA>-yolo.md` (yolo 수정 루프, T14) |
| `warnings` | 배포를 막지 않은 경고와 그중 이 브랜치가 새로 들여온 것(`new_on_branch`) | `scan_warnings.py` (아래 "비차단 경고 수집") |
| `judgment` | 묶음 결정 · 근거, 서비스별 결정 출처 · 지표 · 기준값 · 기준 근접 | artifact `promote-judgment-test`의 `judgment.json` · `<서비스>/metrics.json` · `<서비스>/judgment.json` (T7) |
| `approval` | 운영 승인 필요 · 생략 · 미도달 | compliance(`regulated` · 값 없음 → `required`, `none` → `skipped`), test에서 승격하지 않았으면 `not_reached` |
| `collection` | 항목별 수집 상태 `ok` · `failed` · `not_collected` | 수집 단계 |
| `debt` | 이슈를 열지와 이유 | 아래 규칙 |

- `approval.stage`가 `expected`면 compliance로 계산한 예정 값이다. test 시점에는 prod가 아직 돌지 않는다. `actual`은 prod 실행 결과를 기록할 때 쓴다.
- `near_threshold`는 기준 안이지만 가까운 지표다(예: p95가 기준의 80% 이상). 표시만 하고 이슈 조건에는 넣지 않는다.

## 이슈를 여는 조건 (`debt`)

아래 중 하나라도 해당하면 `open_issue: true`이고, 해당하는 것마다 `reasons`에 한 줄씩 적는다.

- 이 yolo 브랜치가 새로 들여온 비차단 경고가 1건 이상 (`warnings.new_total > 0`)
- AI 자동 수정이 1회 이상 (`repairs.count > 0`)
- 수집 실패가 1건 이상 (`collection.*.status == "failed"`)

수집 실패를 경고 0건으로 처리하지 않는다. 모르는 상태로 배포된 것도 안고 간 문제다.
main에 원래 있던 경고(`new_on_branch: false`)는 리포트에 기록하지만 이슈 조건으로 세지 않는다. 그 경고는 이미 main에 들어간 상태라 이번 yolo가 안고 들어온 문제가 아니고, 매 배포마다 같은 이슈가 열리는 것을 막는다.
`not_collected`는 범위 밖이라 일부러 모으지 않은 항목(현재 `lint`, `image`)이며 이슈 조건이 아니다.
판단이 `abort`인 것만으로는 이슈를 열지 않는다(문제 버전이 승격되지 않았으므로).

## 수집 (`collect.py`)

입력을 모아 위 형식의 리포트 한 개를 만든다. 표준 라이브러리만 쓴다. 입력이 없거나 깨져도 멈추지 않고 그 항목을 `collection.<항목> = failed`로 남긴다.

```bash
python3 collect.py --output report.json \
  --repo-root <배포한 커밋을 전체 이력으로 checkout한 대상 레포> --base-ref origin/main \
  --target aws --target-label aws \
  --promotion yolo-promotion.json \
  --judgment-dir promote-judge --judge-outcome success \
  --warnings warnings.json
```

| 입력 | 없을 때 |
|---|---|
| Actions 실행 정보 (`GITHUB_SHA` · `GITHUB_REF_NAME` · `GITHUB_ACTOR` · `GITHUB_REPOSITORY` · `GITHUB_RUN_ID` · `GITHUB_RUN_ATTEMPT` · `GITHUB_SERVER_URL`, 같은 이름의 옵션으로도 줄 수 있다) | 실행 오류. `yolo/*` 브랜치가 아니어도 실행 오류 |
| `--repo-root`의 `.deploy/config.yaml` | compliance · template_version이 `null`, 승인은 `required` |
| `--repo-root`의 git 이력 (`--base-ref`와 갈라진 지점 ~ SHA) | `repairs` 수집 실패. checkout은 `fetch-depth: 0`이어야 한다 |
| `--promotion` | 생략하면 test에서 승격하지 않은 배포(`promoted: false`, 승인 `not_reached`). SHA가 다르면 `deploy` 수집 실패 |
| `--judgment-dir` | `--judge-outcome skipped`면 판단 미실행(`not_collected`), 아니면 `judgment` 수집 실패 |
| `--warnings` | `warnings` 수집 실패 |

수정 커밋은 제목이 정확히 `[yolo] 검사 실패 자동 수정 N/3`(N은 1~3)인 커밋만 센다. yolo 수정 루프(`skills/yolo-deploy/scripts/repair_loop.py`)가 만드는 형식이다. 변경 파일 중 `.deploy/log/*-yolo.md`는 `history_file`로 따로 둔다.

### 비차단 경고 수집 (`scan_warnings.py`)

`checks.yml`은 HIGH 이상 중 수정판이 있는 것만 막는다. 이 스크립트는 막지 않은 것을 Trivy로 다시 찾아 `--warnings` 파일을 만든다. 차단 검사의 동작은 바꾸지 않는다.

| 출처 (`source`) | 넣는 것 | 스캔 |
|---|---|---|
| `vulnerability` | UNKNOWN · LOW · MEDIUM, 수정판이 없어 막지 않은 HIGH · CRITICAL | `trivy fs --scanners vuln,license <scan-path>` |
| `license` | MEDIUM(상호주의 등 주의 등급). HIGH 이상은 checks가 막고, LOW · UNKNOWN은 일반 라이선스라 뺀다 | 위와 같은 실행 |
| `misconfiguration` | IaC 설정 UNKNOWN · LOW · MEDIUM (FAIL만) | `trivy fs --scanners misconfig <iac-path>` |
| `scan_exception` | `.trivyignore` 항목. 빈 줄 없이 바로 위에 붙은 주석 묶음이 사유이고, 연달은 항목은 같은 사유를 쓴다 | 파일 읽기 |

각 트리는 자기 `.trivyignore`를 적용해 스캔한다(checks가 본 것과 같다). yolo 브랜치가 갈라진 커밋(`git merge-base <sha> <base-ref>`)을 임시 worktree로 꺼내 같은 방식으로 스캔하고, (출처 · ID · 대상 · 패키지)가 기준에 없던 경고에 `new_on_branch: true`를 붙인다. 스캔이 하나라도 실패하면 `status: failed`로 남기고 종료 코드는 0이다(리포트 수집은 계속한다).

```bash
python3 scan_warnings.py --output warnings.json --repo-root <대상 레포> --sha <배포 SHA> \
  --base-ref origin/main --scan-path . --iac-path infra   # checks.yml의 scan-path · iac-path와 같게
```

결과 형식 (`collect.py --warnings` 입력):

```json
{"status": "ok", "detail": null, "base_sha": "<갈라진 커밋>",
 "scanner": {"name": "trivy", "version": "0.75.0", "db_updated_at": "2026-10-10T01:03:02Z"},
 "items": [{"source": "vulnerability", "severity": "MEDIUM", "id": "CVE-…", "target": "be/pnpm-lock.yaml",
            "package": "…", "title": "…", "new_on_branch": true}]}
```

`status`가 `ok`가 아니거나, `base_sha`가 없거나, 항목 형식이 틀리면 `warnings` 수집 실패이고 `detail`이 사유가 된다.

- Trivy 버전과 취약점 DB 갱신 시각을 남긴다. checks 시점과 리포트 시점의 DB가 다를 수 있다.
- 이미지(OS 패키지)의 비차단 취약점은 모으지 않는다(`collection.image = not_collected`). 차단 검사는 checks `image-scan`이 한다.
- pnpm lockfile만 있는 레포는 Trivy가 라이선스를 읽지 못해 라이선스 경고가 0건일 수 있다(설치된 `node_modules`가 필요).

## 저장 · 요약 · 이슈 (`publish.py`)

```bash
GH_TOKEN=<봇 App 토큰> AUDIT_LOG_BUCKET=<버킷> python3 publish.py --report report.json
```

| 순서 | 하는 일 | 실패하면 |
|---|---|---|
| 1 | 감사 로그 버킷(Object Lock)에 `reports/yolo/YYYY/MM/DD/<생성 시각>-<SHA 12자>-<report_id>.json`으로 저장. 체크섬 SHA256 | 이슈 · 요약은 계속하고 종료 코드 1 |
| 2 | `debt.open_issue`면 대상 레포에 `yolo-debt` 이슈. 본문 첫 줄의 표지(`<!-- yolo-debt repository=… branch=… -->`)로 같은 yolo 브랜치의 열린 이슈를 찾아, 있으면 코멘트만 단다 | 종료 코드 1 |
| 3 | Actions 실행 요약(`GITHUB_STEP_SUMMARY`)에 표 | — |

- 이슈 담당자는 실행자다. 지정할 수 없는 계정(봇 등)이면 담당자 없이 연다. 이슈는 자동으로 닫지 않는다.
- 이슈 본문: 이유, 기한(`docs/tasks.md` 0단계의 현재 가정 "다음 janto 배포 전까지 해소"), 요약 표, AI 자동 수정, **새로 들여온 경고 상세**, 원래 있던 경고 건수, 수집 실패, 기준 근접 지표, 리포트 원본 위치, 실행 링크.
- 출력(`GITHUB_OUTPUT`): `location`(S3 위치, 실패면 빈 값), `issue`(이슈 주소), `open-issue`.
- 저장이나 이슈가 실패하면 종료 코드 1이다. 기록 없이 성공으로 보고하지 않는다. 이 단계 뒤에 main 자동 머지(T8)가 이어지지 않게 연결한다.
- `gh`는 Issues 쓰기 권한이 있는 토큰(`one-tatchi-bot` App), `aws`는 감사 로그 버킷 쓰기 자격증명이 필요하다.

### 테스트

```bash
uv run --no-project --with jsonschema python -B -m unittest discover -s .github/actions/yolo-report/tests -v
```

임시 git 레포와 가짜 artifact · 가짜 trivy(`tests/fake-trivy`) · 가짜 aws · gh로 확인한다. 수집: 정상 · 수정 2회 · 새 경고와 원래 있던 경고 · 판단 없음 · 판단 미실행 · abort · SHA 불일치 · 경고 스캔 실패 · compliance 없음 · 기준 근접 · git 이력 오류. 경고 스캔: 새 경고 표시 · 등급 거르기 · 예외 사유 주석 · 스캔 실패 · 임시 worktree 정리. 저장 · 이슈: S3 키 · 이슈 생성 · 같은 브랜치 코멘트 · 문제 없음 · S3 실패 · 버킷 없음 · 담당자 지정 실패 · 이슈 실패 · 표 칸 이스케이프. 모든 리포트와 예시를 `schema.json`으로 검사한다. CI `scripts` 잡에서도 돈다. jsonschema 없이 `python3`로 돌리면 스키마 검사만 건너뛴다.

## 넣지 않는 것

- 토큰 · 비밀번호 · 접속 문자열 같은 비밀값
- 검사 · 배포 원본 로그 전문 (실행 링크로 대신한다)
- 길이 제한: 수정 사유 1000자, 경고 설명 300자, 판단 근거 2000자. 넘으면 자른다
