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

## 넣지 않는 것

- 토큰 · 비밀번호 · 접속 문자열 같은 비밀값
- 검사 · 배포 원본 로그 전문 (실행 링크로 대신한다)
- 길이 제한: 수정 사유 1000자, 경고 설명 300자, 판단 근거 2000자. 넘으면 자른다
