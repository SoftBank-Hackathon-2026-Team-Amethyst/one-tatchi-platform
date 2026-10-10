# ADR 0011: Green 공개 경로 제거 (T30)

상태: 구현 제안. 기존 배포 적용과 내부 격리 검증은 미완료.

## 발견과 결정

2026-10-10 원격 main d7b1b8c 기준 App Chart는 Blue-Green에서 active와 preview Ingress를 함께 생성했다. AWS preview는 internet-facing ALB에 연결되며 GCP 역시 공개 Ingress 대상이다. promote-judge는 이미 Kubernetes API port-forward를 사용하므로 외부 preview가 필요하지 않다. 외부 공격 요청으로 재현하지 않고 템플릿과 리소스 구성을 검토했다.

- preview Ingress를 생성하지 않는다. 예전 `ingress.previewPort` 입력도 공개 경로를 만들지 않는다.
- active/preview Service는 ClusterIP로 명시한다. Rollouts의 previewService는 유지한다.
- smoke는 인증된 Kubernetes API를 통해 runner의 127.0.0.1에만 port-forward한다.
- 알림에서 preview 공개 URL을 제거한다. active Ingress·승격·롤백 계약은 유지한다.

## 확인한 실환경 범위

현재 로컬 kube context k3d-onetouch에서 test/prod FE·BE preview Service 4개는 ClusterIP였고 Ingress와 NetworkPolicy는 없었다. 이 조회만으로 AWS/GCP 실환경의 노출 여부나 외부 도달성을 확정하지 않는다. 앱 main은 확인 당시 v2.1.4를 참조했다.

## 보안 경계: Agent 전용이라고 부르지 않는다

인증 주체는 AI 모델이 아니라 배포 job의 Kubernetes 자격증명이다. 이번 변경은 공개 preview 경로 제거다. ClusterIP는 클러스터 내부에서 접근할 수 있고 pods/portforward 권한 보유자도 접근할 수 있다. 현재 AWS 배포 역할은 EKS cluster-admin이며 관리자·노드는 신뢰 경계에 포함된다.

내부 비인가 워크로드까지 제한하려면 CNI의 NetworkPolicy 집행 여부, 모든 다른 허용 정책, kubelet probe·관측 접근, 배포/검증 주체 RBAC를 함께 검증해야 한다. NetworkPolicy는 허용 규칙이 합산되므로 deny 정책 하나가 다른 allow를 덮어쓰지 않는다. Argo의 previewMetadata/activeMetadata로 동적 분리는 가능하지만 승격 시 라벨 변경과 트래픽 전환 시점, 최초 배포, abort/undo를 시험하기 전 운영에 적용하지 않는다. 이 부분은 T30 미완료 항목으로 유지한다.

## 기존 설치의 적용 절차

1. 플랫폼 릴리스 후 앱 호출부와 차트 버전을 같은 새 버전으로 올리는 PR을 만든다.
2. test부터 정상 Helm upgrade를 실행한다. Helm이 이전 릴리스의 preview Ingress를 삭제하는지 확인한다. 클라우드 LB controller가 기존 preview listener/backend까지 정리했는지도 확인한다.
3. 직접 생성되거나 다른 릴리스가 소유한 Ingress, Gateway HTTPRoute, Service LoadBalancer/NodePort, 터널 목적지에 preview가 없는지 구성 목록으로 대조한다. 차트 업데이트만으로 외부 관리 리소스를 지웠다고 가정하지 않는다.
4. active 정상 응답, localhost smoke 성공, Green 유지·승격·abort를 확인한다. 관리자 승인 없이 운영 관문을 우회하지 않는다.
5. 운영 적용과 내부 격리 검증을 마친 뒤 이슈를 완료한다. 코드 머지만으로 노출 해소 완료라고 보고하지 않는다.

## 검증과 한계

회귀 테스트는 ALB/GCE/nginx × host 유무 × blueGreen/rolling 12개 조합에서 active Ingress 하나만 렌더되고 preview 대상과 legacy preview port가 없음을 검사한다. Blue-Green의 두 ClusterIP Service와 previewService는 유지한다. smoke 가짜 kubectl은 loopback 바인딩을 요구한다.

port-forward는 한 파드로 연결되고 외부 LB 경로는 검사하지 않는다. BASE_URL은 기존 로컬 테스트 주입 인터페이스이며 Actions 호출부에서 사용하지 않는다. 최초 배포는 기존 Blue가 없으므로 Argo가 active로 연결할 수 있다. 최초 배포까지 사전 검증 없는 공개를 막는 요구는 별도 초기 트래픽 개방 절차가 필요하다.

## T31 보완 (2026-10-10)

이 문서가 막은 것은 인증 없는 공개 preview다. 승인자가 green을 보는 경로는 [ADR 0015](0015-authenticated-green-preview.md)를 따른다. App Chart `previewAuth`를 켜면 oauth2-proxy가 Identity Center SSO 로그인을 강제하고, 인증된 요청만 preview Service로 넘긴다. 인증 설정 없이 preview로 가는 Ingress는 여전히 렌더하지 않으며, 위 회귀 테스트도 유지한다. 승격 판단의 smoke는 계속 localhost port-forward를 쓴다.

참고: [Kubernetes port-forward](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_port-forward/), [NetworkPolicy](https://kubernetes.io/docs/concepts/services-networking/network-policies/), [Argo ephemeral metadata](https://argoproj.github.io/argo-rollouts/features/ephemeral-metadata/).
