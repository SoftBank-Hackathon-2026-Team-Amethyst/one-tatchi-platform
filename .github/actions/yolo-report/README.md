# yolo-report

yolo 배포 한 건이 **누가 · 언제 · 무엇을 · 어떤 문제를 안고** 배포됐는지 남기는 리포트다 (T10, 설계 문서 6.3 · FR-12).
yolo는 사람 리뷰 없이 test(규제 대상이 아니면 prod까지) 가므로, 리뷰 대신 기록을 남긴다.

리포트는 S3 감사 로그 버킷(Object Lock)에 JSON으로 남고, Actions 실행 요약에 표로 보인다.
갚아야 할 문제(`debt`)가 있으면 대상 레포에 `yolo-debt` 라벨 이슈를 연다.

## 리포트 형식

형식은 [`schema.json`](schema.json)(JSON Schema 2020-12)이 기준이다. 예시:

| 예시 | 상황 | 이슈 |
|---|---|---|
| [`examples/report-debt.json`](examples/report-debt.json) | AI 자동 수정 1회 + 차단하지 않은 경고 2건, 규제 대상 | 연다 |
| [`examples/report-clean.json`](examples/report-clean.json) | 수정 · 경고 없음, 규제 대상 아님 | 열지 않는다 |
| [`examples/report-partial.json`](examples/report-partial.json) | 경고 스캔 · 판단 근거 수집 실패 | 연다 |

예시의 CVE · 패키지 · 실행 ID는 설명용 합성 값이다.

### 필드와 출처

| 필드 | 내용 | 가져오는 곳 |
|---|---|---|
| `report_id` | `<run_id>-<run_attempt>` | GitHub Actions 실행 정보 |
| `deploy` | 실행자 · 브랜치 · SHA · 대상 · 환경 · compliance · template_version · 실행 링크 · test 승격 여부 | Actions 실행 정보, 배포한 커밋의 `.deploy/config.yaml`, test 승격 확인 결과(`yolo-promotion.json`, T8) |
| `repairs` | AI 자동 수정 회차 · 파일 · 사유 · 수정 커밋, 이력 파일 | 수정 커밋 `[yolo] 검사 실패 자동 수정 N/3`(제목) · 사유(본문), `.deploy/log/<시각>-<SHA>-yolo.md` (yolo 수정 루프, T14) |
| `warnings` | 배포를 막지 않은 경고: MEDIUM 이하 취약점, 라이선스, 검사 예외 | 비차단 Trivy 스캔(JSON), 대상 레포 `.trivyignore` 항목과 사유 주석 |
| `judgment` | 묶음 결정 · 근거, 서비스별 결정 출처 · 지표 · 기준값 · 기준 근접 | artifact `promote-judgment-test`의 `judgment.json` · `<서비스>/metrics.json` · `<서비스>/judgment.json` (T7) |
| `approval` | 운영 승인 필요 · 생략 · 미도달 | compliance(`regulated` · 값 없음 → `required`, `none` → `skipped`), test에서 승격하지 않았으면 `not_reached` |
| `collection` | 항목별 수집 상태 `ok` · `failed` · `not_collected` | 수집 단계 |
| `debt` | 이슈를 열지와 이유 | 아래 규칙 |

- `approval.stage`가 `expected`면 compliance로 계산한 예정 값이다. test 시점에는 prod가 아직 돌지 않는다. `actual`은 prod 실행 결과를 기록할 때 쓴다.
- `near_threshold`는 기준 안이지만 가까운 지표다(예: p95가 기준의 80% 이상). 표시만 하고 이슈 조건에는 넣지 않는다.

## 이슈를 여는 조건 (`debt`)

아래 중 하나라도 해당하면 `open_issue: true`이고, 해당하는 것마다 `reasons`에 한 줄씩 적는다.

- 차단하지 않은 경고가 1건 이상 (`warnings.total > 0`)
- AI 자동 수정이 1회 이상 (`repairs.count > 0`)
- 수집 실패가 1건 이상 (`collection.*.status == "failed"`)

수집 실패를 경고 0건으로 처리하지 않는다. 모르는 상태로 배포된 것도 안고 간 문제다.
`not_collected`는 범위 밖이라 일부러 모으지 않은 항목(현재 `lint`)이며 이슈 조건이 아니다.
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

### 비차단 경고 입력

`--warnings` 파일은 경고 수집 단계가 만든다.

```json
{"status": "ok", "detail": null,
 "scanner": {"name": "trivy", "version": "0.75.0", "db_updated_at": "2026-10-10T00:00:00Z"},
 "items": [{"source": "vulnerability", "severity": "MEDIUM", "id": "CVE-…", "target": "be/pnpm-lock.yaml",
            "package": "…", "title": "…"}]}
```

`status`가 `ok`가 아니거나 항목 형식이 틀리면 `warnings` 수집 실패이고 `detail`이 사유가 된다.

### 테스트

```bash
uv run --no-project --with jsonschema python -B -m unittest discover -s .github/actions/yolo-report/tests -v
```

임시 git 레포와 가짜 artifact로 정상 · 수정 2회 · 경고 · 판단 없음 · 판단 미실행 · abort · SHA 불일치 · 경고 스캔 실패 · compliance 없음 · 기준 근접 · git 이력 오류를 확인하고, 모든 결과와 예시를 `schema.json`으로 검사한다. CI `scripts` 잡에서도 돈다. jsonschema 없이 `python3`로 돌리면 스키마 검사만 건너뛴다.

## 넣지 않는 것

- 토큰 · 비밀번호 · 접속 문자열 같은 비밀값
- 검사 · 배포 원본 로그 전문 (실행 링크로 대신한다)
- 길이 제한: 수정 사유 1000자, 경고 설명 300자, 판단 근거 2000자. 넘으면 자른다
