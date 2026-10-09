---
name: deploy-analyze
description: 웹앱 배포 전에 사용자 수, 예산, 데이터 취급, 배포 대상 선호, 가용성을 질문해 브리프와 초기 compliance를 저장하고, 코드베이스 · 서비스 · 트래픽 · 보안 · 예산 분석기 5개로 배포 대상과 구성을 추천하는 분석 보고서(.deploy/report.md)와 배포 계획(.deploy/plan.yaml)을 만든다. janto-deploy / yolo-deploy의 첫 단계이거나, 어디에 어떻게 배포할지 판단이 필요할 때 쓴다.
---

# 배포 분석 (브리프 + 분석기)

두 단계다. **1단계 브리프**는 코드에서 알 수 없는 정보를 사람에게 묻고 `compliance`를 정한다(T15). **2단계 분석**은 분석기 5개로 레포를 조사하고 추천을 종합한다. 이 스킬은 배포하지 않는다. `.deploy/` 아래 파일만 쓴다.

호출한 스킬이 모드를 알려 준다. **janto**(기본, 단독 실행 포함)는 질문한다. **yolo**는 질문하지 않는다. 아래 명령의 `<skill-dir>`은 현재 읽은 `SKILL.md`가 있는 실제 경로다.

## 1단계: 브리프

1. [질문과 저장 계약](references/brief-format.md)을 읽는다.
2. 배포 대상 앱의 루트 경로를 확인하고, 기존 `.deploy/brief.md`와 `.deploy/config.yaml`이 있으면 읽는다. 플랫폼 저장소에 앱의 답변을 저장하지 않는다.
3. 아래 문서의 다섯 항목을 수집한다. 현재 대화에서 명확히 답한 항목은 재사용하고, 이전 브리프는 변경할 사항을 확인해 재사용한다. 코드만 보고 사용자 규모·예산·규제 여부를 추측하지 않는다.
   - **yolo 모드**: 기존 브리프가 있으면 확인 없이 재사용한다. 없으면 질문하지 않고 다섯 항목을 모두 각 질문의 `skip_value`(명시적 건너뛰기)로 저장한다. yolo 스킬 실행이 그 승인이다. 규제 미정은 `regulated`가 된다.
4. (janto) 아래 명령으로 [고정 질문 정의](references/brief-questions.json)에서 질문 도구용 JSON을 얻는다. `batches`의 각 객체를 순서대로 `AskUserQuestion`에 전달한다. 질문·선택지·순서를 다시 작성하지 않는다. 사용자는 메뉴에서 하나씩 선택해 다음 질문으로 넘어간다. 도구의 최대 4문항 제한 때문에 1~4번을 받고, 중간 요약이나 진행 확인 없이 즉시 5번 메뉴를 연다. 이미 명확히 답한 문항만 제외할 수 있다. 도구가 없으면 동일한 객관식 선택지를 한 질문씩 대화로 제시한다.

   ```sh
   uv run --no-project --with-requirements "<skill-dir>/requirements.txt" python "<skill-dir>/scripts/write_brief.py" --questions
   ```

   사용자 수와 월 예산은 범위를 선택받으며 예산은 원화(KRW)로 고정한다. 민감 데이터 취급은 예·아니오·모름으로 받는다. 배포 대상은 AWS·GCP·온프레미스·추천만 허용한다. 별도의 직접 입력 선택지를 추가하지 않는다. 도구 기본 입력 칸에 지원하지 않는 대상을 적으면 네 선택지에서 다시 선택받는다.
5. (janto) 무응답·도구 취소·시간 초과는 건너뛰기로 간주하지 않는다. 사용자가 명시적으로 모름/건너뛰기를 선택했을 때만 문서의 기본값을 적용한다. 데이터 취급 답변이 모호하거나 서로 충돌하면 그 항목만 다시 확인한다.
6. 다섯 항목의 답변 또는 명시적 건너뛰기가 모두 모이면 `brief-questions.json`에서 선택한 `label`에 대응하는 `value`를 해당 `field`에 저장한다. 범위를 단일 숫자로 바꾸지 않는다. 계약에 맞는 JSON을 임시 파일에 저장하고 아래 저장 스크립트를 실행한다. 의존성은 이 스킬의 `requirements.txt`에 있다.

   ```sh
   uv run --no-project --with-requirements "<skill-dir>/requirements.txt" python "<skill-dir>/scripts/write_brief.py" --project-root "<app-root>" --answers "<answers.json>"
   ```

7. 스크립트가 성공한 경우에만 두 출력 파일, 적용된 `compliance`, 미정 항목을 안내한다(yolo는 기록에 적는다). 실패 시 오류 원인을 설명하고 해당 답변이나 경로를 바로잡는다.

### 기존 설정과의 충돌

- 최초 설정에서는 답변으로 `compliance`를 만든다. 기존 값이 같은 경우 설정 파일은 변경하지 않는다.
- 기존 값과 새 분류가 다르면 스크립트는 두 출력 파일을 모두 보존하고 실패한다. `config.yaml`을 삭제하거나 직접 수정해 재시도하지 않는다. 사용자에게 변경 필요를 알리고 사람이 검토하는 설정 변경(janto PR, CODEOWNERS 리뷰)으로 넘긴다.
- 규제 여부가 미정이면 승인 생략을 허용하지 않는 `regulated`를 적용하고, 브리프에 미정이라는 근거를 남긴다.
- 브리프 수집을 요청받은 것만으로 클라우드 변경, 커밋, push, PR, 배포를 실행하지 않는다. 두 배포 모드에서 같은 수집·분류 규칙을 사용한다.

## 2단계: 분석기 5개

[references/analyzers/](references/analyzers/)의 파일 하나가 분석기 하나의 지시다. 입력은 레포 전체와 `.deploy/brief.md`. 결과는 `.deploy/analysis/<분석기>.md`.

| 순서 | 분석기 | 지시 | 결과 | 정하는 것 |
|---|---|---|---|---|
| 1 | 코드베이스 | `references/analyzers/codebase.md` | `.deploy/analysis/codebase.md` | 서비스 단위, 런타임, 포트, 헬스체크, 환경변수, 검사 명령, 필요한 코드 수정 |
| 2 | 서비스 | `references/analyzers/service.md` | `.deploy/analysis/service.md` | 서비스 성격, 다루는 데이터, 가용성 요구, 릴리스 주의점 |
| 3 | 트래픽 | `references/analyzers/traffic.md` | `.deploy/analysis/traffic.md` | 서비스별 `replicas` · `resources`, 확장 계획 |
| 4 | 보안 | `references/analyzers/security.md` | `.deploy/analysis/security.md` | 배포를 막는 문제, 외부 노출 범위, 규제가 요구하는 설정 |
| 5 | 예산 | `references/analyzers/budget.md` | `.deploy/analysis/budget.md` | 후보 대상별 예상 월 비용과 예산 대비 |

- 서브에이전트를 사용할 수 있으면 코드베이스 · 서비스 · 트래픽 · 보안을 병렬로 실행하고, 예산은 트래픽 결과가 준비된 뒤 실행한다. 각 분석기에 지시 파일 · 브리프 · 결과 파일 경로를 준다. 병렬 실행이 없으면 위 순서로 진행한다. 예산을 기본 시나리오로 먼저 실행했다면 가정으로 표시하고 최종 트래픽 결과로 다시 계산한다.
- 브리프에 없어서 추정한 값은 모두 각 결과의 **가정** 절에 근거와 함께 적는다.

## 3단계: 종합

다섯 결과를 읽고 [references/report-format.md](references/report-format.md)대로 두 파일을 쓴다.

- `.deploy/report.md`: 사람이 리뷰 지점 1에서 읽는 분석 보고서. 결론(추천)이 맨 위.
- `.deploy/plan.yaml`: `target`, `services`. 스킬 사이의 인계값이라 통째로 다시 쓴다. **`.deploy/config.yaml`은 건드리지 않는다**(`compliance`는 1단계 스크립트가, `template_version`은 `deploy-provision` · `template-update`가 쓴다. CODEOWNERS 리뷰 대상).

### 비용 근거 확인과 보고서 갱신

1. 예산 분석기의 [도구 실행 순서](references/analyzers/budget.md)를 따라 pricing-inventory.json → pricing-input.json · resource-assessment.json → prices.json → costs.json을 생성한다. report로 budget.md와 cost-summary.md를 같은 계산 결과에서 만든다.
2. 종합 결과의 target · services 크기 · DB · 공유 환경과 계산 구성을 대조한다. 최종 추천 크기가 바뀌면 자원 목록을 갱신하고 map → lookup → calculate → report를 다시 실행한다. replicas 변화만으로 노드를 늘리거나 줄이지 않는다.
3. report.md를 위 형식으로 작성한 뒤 추천 candidate_id를 지정해 report 명령에 --report 경로를 전달한다. 그 비용 블록은 도구가 갱신하며 종합 단계에서 다른 금액을 만들어 넣지 않는다.
4. 예산 초과·초과 가능·판정 미정, 부분 소계, 환율·조회 시각과 미산정 사유를 리뷰 지점 1에서 함께 설명한다. 별도 대안 견적이 없으면 절감액 미산정 사유를 남긴다. 도구 실패를 성공이나 최신 단가로 바꾸지 않는다.
5. .deploy/config.yaml은 브리프 분류와 template_version의 기존 소유 규칙을 따른다. 비용 도구와 종합 단계는 이 파일을 수정하지 않는다.

### 배포 대상 추천 규칙

`aws` · `onprem` · `gcp` 중 하나를 추천한다. 하이브리드(클라우드 + 온프레미스 동시)는 비목표라 추천하지 않는다.

1. **규제가 먼저다.** 브리프의 민감 데이터 답변이 `yes`이고 서비스 분석이 데이터 국내 · 사내 보관을 요구하면 `onprem`. 규제가 있어도 보관 위치 요구가 없으면 클라우드도 가능하다(운영 승인은 `compliance`가 따로 강제한다).
2. **선호가 있으면 따른다.** `preferred_target`이 `aws` · `gcp` · `onprem`이면 그 값. 규제 규칙과 충돌하면 보고서에 충돌을 적고 규제를 따른다.
3. **`auto`면** 코드에 남은 흔적(클라우드 SDK · 설정), 같은 범위에서 완전하게 계산한 비용 비교 순으로 정한다. 부분 소계를 가장 저렴한 전체 비용처럼 비교하지 않는다. 비용 우열을 확정하지 못하면 확인 조건을 적고, 근거가 없으면 `aws`를 기본 후보로 둔다.
4. **GCP 구현체(T4)를 제공한다.** `gcp`를 추천할 때는 대상 앱의 프로젝트·리전·CI 인증·GKE 접속·레지스트리·DB 구성과 템플릿 참조를 확인하고 준비되지 않은 조건을 보고서에 적는다. 가격 조회 성공만으로 배포 준비가 완료됐다고 판단하지 않는다.
5. **온프레미스는 클러스터가 있어야 한다.** 브리프 · 레포에 self-hosted runner와 kube context 정보가 없으면 `onprem`을 추천하지 않고 보고서에 조건을 적는다.

추천에는 이유 한 줄과, 검토했다가 버린 대안마다 한 줄을 붙인다.

## 기록

`.deploy/log/<YYYYMMDD-HHMMSS>-analyze.md`: 모드, 브리프 재사용 여부, 돌린 분석기와 병렬 여부, 소요 시간, 추천 결과.

## 끝난 상태

- `.deploy/brief.md`, `.deploy/config.yaml`(`compliance`), `.deploy/plan.yaml`(`target`, `services`)
- `.deploy/analysis/` 아래 결과 5개, 가격 입력·단가·비용·자원 평가 JSON, `cost-summary.md`, `.deploy/report.md`
- 추정한 값이 모두 보고서 **가정** 절에 있고, 비용 표와 추천 비용 블록이 같은 계산 근거를 사용한다

## 설치와 로컬 검증

`scripts/install-skills.sh`가 이 폴더를 `~/.claude/skills/deploy-analyze`(Claude Code)와 `~/.agents/skills/deploy-analyze`(Codex)에 링크한다. `skills/`는 배포 원본 위치이며 그 자체로 명령이 등록되는 위치는 아니다. 이전 질문이 계속 보이면 새 대화에서 실행하고, 설치본의 `--questions` 출력 첫 선택지가 `100명 이하`인지 확인한다.

저장 로직 테스트는 플랫폼 저장소 루트에서 실행한다.

```sh
uv run --no-project --with-requirements skills/deploy-analyze/requirements.txt python -B -m unittest discover -s skills/deploy-analyze/tests -v
```

실제 대화 검증 절차는 [질문 계약의 검증 절](references/brief-format.md#검증)에 있다.
