# T17 실제 조회 검증 — 2026-10-10

대시보드: https://onetatchi.soulee.dev/grafana/d/deploy-overview

## 온프레미스 테스트와 읽기 전용 재검증

대상 실행은 [demo-app 38047517925, attempt 1](https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/demo-app/actions/runs/38047517925),
SHA `208c12ac2df277122af4a75fb3591de853069921`, onprem-secondary / test다.
원래 workflow의 verify는 실패했고 cleanup은 성공했다. 이 결과를 성공으로 덮어쓰지 않는다.

- `ai-comparison.json`의 `matched=true`: 원본 metrics·60초 관찰 창·판단·run/attempt/SHA가 CloudWatch 및 Grafana 행과 일치했다. AI smoke는 runtime counter를 증가시키지 않았다.
- 실제 요청 증가량 BE 35 / FE 20, BE 오류 5회, 300ms 지연 10회. warm-up을 포함한 최종 원본 counter는 BE 37 / FE 21이다.
- `cleanup-result.json`은 passed. 이번 green만 abort·제거했고 blue Ready 및 prod 메타데이터 불변을 확인했다.
- verify 실패 원인은 배포 context `k3d-onetouch-hyeongrae`를 수집 라벨 `onetouch-hyeongrae` 대신 사용한 것과 histogram 경계의 문자열 비교였다.

수정된 `Client.runtime`으로 원본 artifact의 green과 traffic snapshot을 사용해,
저장된 마지막 조회 시각 **2026-10-10 11:23:49.758 UTC**에서 실제 Grafana 과거 데이터를 다시 읽었다.
새 배포·장애 주입 없이 counter 37/21과 모든 histogram bucket의 일치 검사를 통과했다.
같은 시각의 실제 provision된 패널 쿼리 결과:

| 서비스 | 요청/초 | HTTP 5xx 비율 | histogram p95 |
|---|---:|---:|---:|
| demo-app-be | 0.0701754 | 25% | 475ms |
| demo-app-fe | 0.0140351 | 0% | 4.75ms |

오류 비율은 해당 시각의 5분 rate 결과이며, 전체 테스트의 단순 오류 비율과 다르다.
AWS·onprem 각 BE/FE의 sample age는 1.643~12.109초였으며 CloudWatch와 온프레미스 CPU/메모리의 freshness 검사도 통과했다.

## GCP 조회

AWS apply [38048409419](https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/demo-app/actions/runs/38048409419)로
projected token·플러그인 ADC 전달 수정이 적용됐다. 이후 발견된 PromQL legacy migration 문제는
`timeSeriesList: {}`를 유지하면 해결됨을 실제 API로 확인했다.
중앙 Grafana의 Cloud Monitoring에서 `count({__name__="kubernetes_io:container_cpu_core_usage_time"})`가
102개 시계열을 반환했다. 서비스 계정 private key나 IAM 확대 없이 WIF 인증과 Monitoring 조회가 성공했다.

이 문서 작성 시점에는 ADC `project_id` 및 대시보드 쿼리 호환 패치의 배포가 남아 있다.
GCP 앱 HTTP 시계열은 비어 있었으므로 GCP 앱 지표까지 검증 완료한 것으로 기록하지 않는다.
