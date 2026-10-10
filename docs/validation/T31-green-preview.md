# T31 승인자용 green 미리보기: 해결한 문제와 방법

2026-10-10 기준. 설계 결정은 [ADR 0015](../adr/0015-authenticated-green-preview.md), 작업 계획은 `docs/tasks.md`의 T31을 따른다.

## 1. 승인자가 green을 볼 수 없었다 (green 인증)

### 문제

- 처음에는 green이 ALB `:8080` 포트로 **인증 없이 인터넷에 공개**돼 있었다.
- T30([ADR 0011](../adr/0011-private-green-access.md))이 공개 경로를 없애자, 이번에는 **아무도 green을 볼 수 없게** 됐다.
- regulated 대상은 사람이 승격을 눌러야 한다(T6). 승인자는 green을 열어 보지 못하고 AI 판단만 보고 승인하게 됐다. 설계 문서 FR-6("승격 전 미리보기 주소 제공")도 만족하지 않았다.

### 해결

`green.<host>`를 **Identity Center SSO 로그인 뒤에서만** 다시 열었다.

```
승인자 → green 호스트 (ALB) → oauth2-proxy ──OIDC──> Cognito ──SAML──> IAM Identity Center
                                └ 인증된 요청만 → <release>-preview (ClusterIP) → green 파드
```

- 사용자 원장은 Identity Center 하나다. Cognito는 SAML을 OIDC로 바꾸는 중계일 뿐, 사용자를 갖지 않는다. 직접 가입과 Cognito 자체 계정 로그인은 막았다.
- App Chart `previewAuth`: 켜면 oauth2-proxy · Service · ExternalSecret · Ingress를 만든다. 인증 설정(`host` · `issuerUrl` · `remoteKey`)이 하나라도 빠지면 렌더가 실패한다. 인증 없이 green으로 가는 Ingress는 여전히 만들지 않는다.
- `modules/preview_auth/aws`: Cognito User Pool · 로그인 도메인 · SAML IdP · 앱 클라이언트 · oauth2-proxy 시크릿.
- 재사용 `deploy.yml`의 `preview-host` 입력: Slack 알림과 실행 요약에 `https://<host>/ (SSO 로그인 필요)`를 다시 넣는다.
- 호스트: test `green-yolo.onetatchi.soulee.dev`, prod `green.onetatchi.soulee.dev`. 인증서가 `*.onetatchi.soulee.dev`라서 `green.yolo.…`처럼 두 단계인 이름은 쓰지 않는다.

### 확인

- test에서 SSO 로그인이 되는 것을 확인했다.
- 로그인하지 않은 요청은 `/`든 `/api/health`든 302로 Cognito → Identity Center 로그인으로 보내지고, green에 닿지 않는다.
- active(`yolo.onetatchi.soulee.dev`)는 200으로 그대로 동작한다.
- **AI 승격 판단에는 영향이 없다.** promote-judge는 Ingress를 거치지 않고 클러스터 API로 `<release>-preview`에 port-forward하므로 oauth2-proxy를 지나지 않는다. SSO를 켠 뒤의 test 배포에서 BE · FE 모두 AI 판단이 `promote`였다(에러율 0%, p95 492ms · 500ms).

## 2. green 화면이 blue BE를 불렀다 (green → blue)

### 문제

- demo-app FE의 nginx는 `/api/`를 `demo-app-be`(active, 즉 blue) Service로 프록시한다.
- 그래서 green FE 화면을 열어도 **API는 blue BE가 응답**했다. 승인자가 green 화면을 봐도 BE 변경은 검증되지 않았다.
- FE 파드 설정을 `-preview` BE로 바꾸는 방법은 쓸 수 없다. 같은 파드가 승격 뒤에는 active가 되므로, 다음 배포 때 실제 사용자 트래픽이 검증되지 않은 BE로 간다.

### 해결

파드는 그대로 두고, **green 호스트 앞단에서 경로를 나눴다.**

- App Chart `previewAuth.routes`(v2.4.0): oauth2-proxy가 `/api/`는 `demo-app-be-preview`로, 나머지는 FE preview로 보낸다.
- 경로 접두사는 그대로 넘긴다. oauth2-proxy v7.15.4 바이너리로 `/`, `/index.html`, `/apix` → FE, `/api/info`, `/api/chaos/reset` → BE를 먼저 확인했다. 인증하지 않은 요청은 두 경로 모두 302였다.
- active 트래픽과 승격 이후 동작은 바뀌지 않는다. BE가 바뀌지 않은 배포에서는 BE preview가 active와 같다.
- demo-app `deploy/values-fe.yaml`에 설정했다(demo-app #65). demo-app 템플릿이 v2.4.0 이상으로 올라가야 실제로 적용된다.

## 3. 진행 중 함께 고친 문제

| 문제 | 해결 |
|---|---|
| PR plan 역할(ReadOnlyAccess)이 새 oauth2-proxy 시크릿 버전을 refresh하지 못해, demo-app의 모든 aws PR plan이 실패할 상황 | `secret_reader_arns`로 그 시크릿 하나에만 plan 역할 읽기 정책을 붙였다(v2.2.1). plan 역할은 state에서 같은 값을 이미 읽을 수 있어 노출 범위는 늘지 않는다 |
| SAML IdP의 `provider_details`를 Cognito가 채워, plan마다 지우려는 in-place 변경이 나옴 | 그 키들을 `ignore_changes`로 무시한다 |
| slack-bot Helm 릴리스가 `pending-upgrade`에 멈춰 infra apply가 실패 | 실행 중인 것과 같은 리비전 4로 rollback했다. 파드는 재시작되지 않았다 |
| 와일드카드 인증서가 두 단계 이름을 덮지 않음 | test green 호스트를 `green-yolo.…`로 정했다 |

## 남은 것

- onprem · gcp 적용(T31 할 일 7). aws에서만 쓰고 두 대상은 port-forward로 두는 방안을 검토 중이다.
- 할당되지 않은 Identity Center 사용자가 거부되는지는 실제 계정으로 시험하지 않았다.
- Identity Center MFA가 꺼져 있어 인증은 비밀번호 하나다(ADR 0001).
