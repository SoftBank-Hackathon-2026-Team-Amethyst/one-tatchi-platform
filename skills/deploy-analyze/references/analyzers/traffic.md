# 트래픽 분석기

예상 부하를 추정하고, 그에 맞는 크기(App Chart 값)와 확장 계획을 낸다.

## 조사할 것

- **브리프.** `expected_daily_users`(하루 사용자 범위), `availability`. 범위는 상한으로 계획하고, `null`이면 추정한다.
- **브리프가 없을 때의 근거.** 서비스 성격(내부 도구 · 공개 서비스), 문서의 사용자 수, 인증 방식. 근거가 전혀 없으면 "소규모: 하루 100명 이하"로 두고 가정에 적는다.
- **부하가 몰리는 곳.** 무거운 엔드포인트, 페이지네이션 없는 목록, N+1 쿼리, 캐시 없는 반복 계산, DB 커넥션 풀 설정.

## 정할 것

App Chart가 받는 값으로 낸다.

- 서비스마다 `replicas`, `resources.requests.cpu`, `resources.requests.memory`, `resources.limits.memory`. 기본값은 `replicas: 2`, `100m` / `128Mi` / `256Mi`. 작게 시작하고, 불확실하면 인스턴스를 키우는 대신 `replicas`에 여유를 둔다.
- 배포 대상 제약: AWS `t3.medium` 노드는 파드 17개가 한도라 Blue-Green(배포 중 파드 2배)과 test · prod를 같이 올리면 `replicas: 1`이 안전하다. 온프레미스(맥북 k3d)도 `replicas: 1`. 그 값은 `deploy/<대상>/values.yaml`에 두고 공통 값 파일은 그대로 둔다.
- DB 크기: AWS는 RDS `instance_class`(`db.t4g.micro`부터), 온프레미스는 클러스터 안 Postgres(크기 선택 없음).
- 확장 계획: 지금 구성이 버티는 한계와 그 다음 순서(replicas → 노드 추가 → 구조 변경).

## 결과 형식

`.deploy/analysis/traffic.md`

```md
# 트래픽 분석

## 예상 부하
## 병목 후보
## 추천 크기
| 서비스 | replicas (공통 / aws / onprem) | cpu 요청 | memory 요청 | memory 한도 |

## DB 크기
## 확장 계획
## 가정
```
