# failure-diagnosis

배포 단계(이미지 발행 `publish` · 배포 `deploy`)가 실패하면 실패 증거를 모아 Claude로 원인을 요약한다 (T12).
지금 실패 알림은 "작업 실패. 실행 로그를 확인해 주세요"뿐이라, 사람이 Actions 로그와 클러스터를 뒤져야 원인을 안다.
요약은 Actions 실행 요약 · Slack · (커밋에 연결된 PR이 있으면) PR 코멘트에 남는다.

## 흐름

```
publish · deploy job 실패
  └─ (deploy job 안, if: failure()) 클러스터 상태 수집 → artifact
       Rollout 상태 · Warning 이벤트 · Ready가 아닌 파드 로그 · 마이그레이션 Job 로그
진단 job (ubuntu, 실패한 job 뒤)
  ├─ 실패한 job의 로그를 API로 받음 (실패 step · 오류 줄 · 끝부분)
  ├─ 비밀값 가리기 · 크기 제한 → evidence.json
  ├─ Claude 구조화 출력 → diagnosis.json (실패하면 fallback)
  └─ 실행 요약 · Slack "원인 요약" 메시지 · PR 코멘트
```

- 성공 · 승격 판단의 의도된 abort에는 돌지 않는다(abort는 이미 AI 근거가 있다).
- 진단이 실패해도 배포 결과와 기존 알림은 바뀌지 않는다.
- 기존 배포 단계와 공용 `slack-notify`는 고치지 않는다. 실패 시 단계와 진단 job을 더하기만 한다.
- 외부 LLM으로 보내는 범위: test 환경만 요약한다. prod는 기본적으로 요약하지 않고 `source: fallback`(오류 줄만)으로 남긴다.

## 형식

| 파일 | 내용 | 스키마 |
|---|---|---|
| `evidence.json` | 요약의 입력. 실행 · 배포 정보, 실패한 job(실패 step · 오류 줄 · 로그 끝), 클러스터 상태, 항목별 수집 상태 | [`evidence.schema.json`](evidence.schema.json) |
| `diagnosis.json` | 요약 결과. 분류 · 요약 · 근거 줄 · 확인/조치 · 확신도, AI 요약인지 fallback인지 | [`diagnosis.schema.json`](diagnosis.schema.json) |

분류(`category`): `migration` · `image_publish` · `rollout_unhealthy` · `credentials` · `timeout` · `configuration` · `infrastructure` · `unknown`.

수집 실패는 `collection.<항목>.status = failed`로 남긴다. 클러스터에 접속하지 않는 `publish` job은 `cluster`가 `not_collected`다.

### 예시

실제 demo-app 실패 실행에서 만들었다.

| 예시 | 실행 | 내용 |
|---|---|---|
| [`examples/evidence-migration.json`](examples/evidence-migration.json) · [`diagnosis-migration.json`](examples/diagnosis-migration.json) | [38070479286](https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/demo-app/actions/runs/38070479286) | helm `pre-upgrade hooks failed: Job/test/demo-app-be-migration … failed: 3/1`. Actions 로그에는 Job이 실패했다는 것만 남고 원인은 Job 파드 로그에 있다. 클러스터 부분(이벤트 · Job 로그)은 지금 남아 있지 않아 **설명용 합성 값**으로 채웠다 |
| [`examples/evidence-image-publish.json`](examples/evidence-image-publish.json) · [`diagnosis-image-publish.json`](examples/diagnosis-image-publish.json) | [38066156334](https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/demo-app/actions/runs/38066156334) | `existing tag has different digest`. 원인이 Actions 로그에 그대로 있다 |
| [`examples/diagnosis-fallback.json`](examples/diagnosis-fallback.json) | — | Claude 시간 초과 → 오류 줄만 보여 준다 |

## 수집 스크립트

| 파일 | 어디서 | 하는 일 |
|---|---|---|
| [`cluster.sh`](cluster.sh) | 실패한 deploy job 안 (`if: failure()`, onprem은 맥북 러너) | Rollout 상태 · Warning 이벤트 40개 · Ready가 아니거나 재시작한 파드 10개의 로그 끝(재시작했으면 `--previous`) · `<서비스>-migration` Job 상태와 로그 → `cluster.json`. bash · kubectl · jq · sed만 쓴다 |
| [`collect.py`](collect.py) | 진단 job (ubuntu) | 실행의 실패한 `deploy` · `publish` job(최대 3개) 로그를 API로 받아 실패 step · 오류 줄 · 첫 `##[error]` 앞뒤를 뽑고 `cluster.json`과 합쳐 `evidence.json`을 만든다. 로그 API에는 `actions: read` 토큰(봇 App 토큰)이 필요하다 |
| [`redact.sed`](redact.sed) | 두 스크립트 공용 | 접속 문자열 비밀번호 · Bearer · GitHub/AWS/Slack/Anthropic 토큰 형태 · `password=` 류 값을 `***`로 가린다. 가린 뒤 JSON이 깨지면 내용을 버리고 수집 실패로 남긴다 |

클러스터 상태는 실패한 job 안에서, Actions 로그는 진단 job에서 모으는 이유는 [ADR 0019](../../../docs/adr/0019-failure-evidence-collection.md).

둘 다 하나가 실패해도 멈추지 않고 `collection`에 이유를 남긴다. 테스트: `uv run --no-project --with jsonschema python -B -m unittest discover -s .github/actions/failure-diagnosis/tests` (가짜 kubectl · gh, 실제 demo-app 실패 로그 일부를 `tests/fixtures`에 둔다).

## 넣지 않는 것

- 비밀값: GitHub가 가린 값(`***`) 외에도 클러스터 출력의 접속 문자열 · 토큰 형태를 가린다(수집 단계).
- 로그 전문: 항목별 크기 상한(실패 step 로그 끝 12000자, 파드 · Job 로그 끝 4000자, 이벤트 40개)을 넘지 않는다.
- 코드 수정 PR: 요약의 `actions`에 고칠 곳 · 방향만 적는다. 코드 수정은 yolo 수정 루프(T14)와 사람 리뷰가 맡는다.
