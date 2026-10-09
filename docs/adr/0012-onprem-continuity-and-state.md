# 0012: 잠금 중 연속 실행과 온프레미스 state 이전

상태: 채택 (T27). 두 맥북의 실기 검증 결과는 별도 기록한다.

충전기·네트워크 연결, 열린 덮개와 로그인 세션을 유지하고 launchd의 `caffeinate -s`로 시스템 잠자기를 방지한다.
화면 잠금과 FileVault를 유지한다. 재부팅 뒤 로그인 1회 후 자동 시작은 보조 기능이며, 무인 FileVault 해제는 시도하지 않는다.
기기별 클러스터·state·runner를 분리하고 기존 `onprem` 선택과 runner 라벨을 유지한다. 추가 기기는 `onprem-secondary` 같은 설정값으로 구분하며 사람 이름을 가정하지 않는다.

PostgreSQL은 기존 StatefulSet·PVC·접속 규격을 유지한다. Helm Postgres 교체는 리소스 이름·데이터 경로·비밀번호 수명주기를 함께 바꿔
재부팅 안정성 검증에 불필요한 이전 위험을 추가한다. 현재 구성을 보존하고 비밀번호 저장 경로만 고친다.
Terraform 1.11+ ephemeral 입력과 Kubernetes provider 2.38+ write-only Secret을 사용한다.
기존 Secret의 비밀번호를 읽어 유지하고, Secret 없이 데이터만 있으면 중단한다.
state 이전은 암호화 백업의 복구 검증과 리소스 동일성 확인 뒤 수행하며 알려지지 않은 비밀값을 임의로 제거하지 않는다.

검사와 배포 사이에는 두 아키텍처의 OCI 산출물을 전달한다. 검사가 통과한 동일 index digest를 발행·배포하고 prod는 test의 실제 승격까지 확인한다.
artifact 만료나 태그 충돌은 새 빌드로 우회하지 않는다. 이로 인해 기존 같은 SHA의 단일 아키텍처 태그와 충돌하면 새 커밋에서 배포해야 한다.

인증 출력 제거·필수 ephemeral DB 입력·OCI artifact 계약은 호환되지 않는 변경이므로 v2로 릴리스한다.
AWS/GCP Terraform 루트는 명시적인 `infra_versions` 고정으로 단계적으로 이전한다. v1 메이저 태그와 기존 앱 호출은 유지한다.

운용 및 검증 절차: [scripts/onprem/README.md](../../scripts/onprem/README.md).
