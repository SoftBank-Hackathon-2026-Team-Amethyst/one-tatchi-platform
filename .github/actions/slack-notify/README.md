# 배포우사기 알림의 경로와 요청 (T26)

알림에 배포 경로(flow), 소스 브랜치, 배포 환경(environment), 현재 단계(stage), 사람이 할 일(next-action)을 표시한다. 모두 표시용 입력이며 버튼 action_id/value와 권한 정책은 바꾸지 않는다. 입력을 생략한 기존 호출도 유지한다.

## 알림 순서

- Janto / 일반 PR: 검사 통과 → 코드 리뷰 승인(보호 파일 변경 시 필요)·PR 머지 버튼.
- test 실행 시작: main 또는 yolo 브랜치 소스의 test 배포 준비 알림. 수동 재배포를 새 머지로 표현하지 않는다.
- test 배포 결과: 수동 모드는 근거 확인 후 트래픽 승격·Green 취소, 자동 모드는 실제 promote 실행 여부를 표시.
- prod 운영 승인 요청: prod Green 생성 전 배포 시작을 허용하는 승인·거절. PR 리뷰나 트래픽 승격과 구분.
- prod 배포 결과: 수동 모드는 트래픽 승격·Green 취소, 자동 승격 성공은 되돌리기.
- Slack에서 승격·복구 요청 후 rollout 실행 결과: 별도 수동 조작 결과 알림. 원래 배포 경로 정보는 현재 버튼 계약에 없어 Janto라고 추측하지 않는다.

Yolo PR은 pr-ready에서 제외되어 코드 리뷰·머지 버튼 알림이 오지 않는다. 자동 머지 처리는 yolo-pr job이 담당하며, 보호 규칙에 걸리면 사람이 GitHub PR에서 처리해야 할 수 있다. 이번 변경은 별도의 Yolo PR 생성/머지 완료 알림을 추가하지 않는다.

`promote-mode: branch`에서 판정한 auto를 Yolo로 표시한다. manual은 Janto / 일반 배포로 표시한다. 실제 스킬 호출 이력을 보증하지 않는다. workflow_dispatch는 수동 재배포, 명시적 auto는 자동 승격 배포로 표시한다.

## 적용

공통 액션과 workflow 변경이므로 봇 버튼 핸들러 이미지 변경은 필요 없다. 플랫폼 릴리스 후 demo-app의 workflow template-ref를 해당 버전으로 올려야 새 알림이 나온다. 이전에 게시한 Slack 메시지는 바뀌지 않는다.

검증은 curl 대체 프로그램으로 chat.postMessage payload를 로컬 렌더링한다. 실제 Slack 게시나 승인 버튼 실행은 하지 않는다.
