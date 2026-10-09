# T4 GCP 검증

2026-10-09, 프로젝트 `one-tatchi-gejkm`, 서울 `asia-northeast3`에서 검증했다. 구현은 플랫폼 [PR #96](https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/one-tatchi-platform/pull/96), Monitoring 반복 변경 수정은 [PR #99](https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/one-tatchi-platform/pull/99)에 있으며 둘 다 머지됐다. 릴리스는 `v1.13.1`이다.

## 완료 기준과 결과

| 확인 항목 | 결과 |
|---|---|
| GCP 프로젝트·결제·API | 프로젝트 ACTIVE, 팀 계정 Owner, 필요한 API 활성화를 확인했다. |
| CI 인증·state | WIF plan/deploy 인증에 성공했다. GCS의 bootstrap/gcp와 demo-app/gcp prefix를 분리했다. |
| GKE·네트워크·저장소 | 비공개 노드 3대가 Ready이며, NAT·Artifact Registry BE/FE 저장소가 생성됐다. CI에서 실제 이미지를 검사하고 업로드했다. |
| DB·Secret | 사설 Cloud SQL Postgres 17이 생성됐고 SecretStore와 test/prod ExternalSecret이 Ready다. 마이그레이션 후 BE의 database=connected, dbConnected=true를 확인했다. |
| DB 저장 확인 | API로 만든 행을 다른 BE 파드와 승격 후 새 파드에서 읽었다. 직접 만든 검증 행 하나만 삭제했다. |
| 비밀번호 저장 | 실제 비밀번호와 현재 GCS state·저장 DB/full plan을 비교해 평문이 없음을 확인했다. 검증 과정에서 비밀번호를 출력하지 않았다. |
| 관측 | GKE CPU 지표와 k8s_container 로그 수집을 확인했다. 기존 중앙 Grafana는 유지했다. |
| Terraform 최종 상태 | 발행된 v1.13.1 원격 모듈과 service-base 차트를 적용한 뒤 plan이 No changes를 반환했다. |
| 공통 출력 | [모듈 계약](../modules/README.md)의 공통 출력 이름과 의미를 대조했다. AWS 전용 출력은 GCP에 복제하지 않는다. |
| 앱 배포·승격 | 같은 App Chart와 공통 BE/FE 값 파일에 GCP 설정만 추가했다. 두 GHA 배포가 성공했고 active/preview의 FE·health·info·votes·guestbook이 HTTP 200을 반환했다. 두 서비스가 Paused인 동안 active는 기존 stable, preview는 새 green을 선택했다. 로컬 승격 후 두 서비스가 Healthy이며 새 이미지가 stable임을 확인했다. |

접속 주소는 [active](http://136.82.112.142/)와 [preview](http://136.82.119.77/)다. stable 이미지 태그는 `f1571e99c019cbd778bc28bcbfb7692c4ff22ab7`이며 BE/FE stable ReplicaSet은 각각 `6466d8dc54`, `7f6987c798`이다.

## 완료 절차 결과

[demo-app PR #36](https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/demo-app/pull/36)은 최신 main의 v1.14.0 참조와 T26 알림·branch 승격 설정을 보존해 충돌을 해결한 뒤 머지됐다. config와 AWS/onprem 루트는 main과 동일하며 GCP 루트도 v1.14.0을 참조한다.

작업 브랜치의 rollout은 CI 신뢰 조건에서 거부됐지만, 머지 후 [main의 GCP rollout](https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/demo-app/actions/runs/37903198486)은 인증·명령·감사 로그를 포함해 성공했다. 임시 브랜치 배포 조건은 제거했다. 최신 [PR 검사](https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/demo-app/actions/runs/37903071761)와 [GCP plan](https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/demo-app/actions/runs/37903071771)도 성공했다.

## 기존 작업 영향

- 플랫폼의 기존 AWS·onprem Terraform 모듈 구현은 T4 이전과 동일하다. 변경한 공통 App Chart의 AWS·onprem 렌더링도 이전 결과와 객체 단위로 동일하다.
- AWS plan은 실행 identity 출력의 차이만 있으며 실제 인프라 변경을 제안하지 않았다. AWS 변수·state·도메인과 기본 DEPLOY_TARGET을 유지했다.
- demo-app의 최신 main 기준으로 앱 소스·Dockerfile·DB SQL·공통 값 파일·smoke 요청·CODEOWNERS를 변경하지 않았다. 팀의 yolo 자동 승격과 Python 검사 설정을 보존했다.
- GCP 인프라만 변경하면 AWS apply를 실행하지 않도록 루트별 경로를 나눴다. 앱 코드·공통 값 변경 시에는 기존 push 배포가 실행된다.
- [공통 코드 검토](reviews/t4-shared-code/2026-10-09-1355.md)에서 현재 배포 경로를 깨뜨리는 결함을 발견하지 않았다. 실제 AWS/onprem 재배포 전체를 수행했다는 뜻은 아니다.

## 실행 근거

- [플랫폼 최초 CI](https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/one-tatchi-platform/actions/runs/37884360045): 5종 성공.
- [패치 CI](https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/one-tatchi-platform/actions/runs/37885966881): 5종 성공.
- [v1.13.1 릴리스](https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/one-tatchi-platform/actions/runs/37886179043): 차트·봇·알림 성공.
- [demo-app 최신 인프라 검사](https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/demo-app/actions/runs/37886279665): AWS/GCP plan 성공.
- [첫 GCP test 배포](https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/demo-app/actions/runs/37885801712).
- [두 번째 GCP test 배포](https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/demo-app/actions/runs/37886291673).
- [Monitoring 대시보드](https://console.cloud.google.com/monitoring/dashboards/builder/760b4ef1-d9f8-436b-a19f-dd98fd18694e?project=one-tatchi-gejkm).

GCP prod 앱 배포·HTTPS 도메인은 이 검증에 포함하지 않는다. prod 승인 관문은 유지한다. 운영·정리는 [GCP 배포 안내](gcp-deploy.md)를 따른다.
