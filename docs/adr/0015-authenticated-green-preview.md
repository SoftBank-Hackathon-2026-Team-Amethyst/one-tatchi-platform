# [ADR-0015] 승인자용 green 미리보기: Identity Center SSO로 인증

* **상태 (Status):** 승인됨(Accepted). T30 담당자와 합의함. aws test 적용과 SSO 로그인 확인 완료(2026-10-10)
* **날짜 (Date):** 2026-10-10
* **관련:** T31, T30, T6, T2, T23, [ADR 0003](0003-green-access-port-forward.md), [ADR 0011](0011-private-green-access.md), [ADR 0001](0001-aws-account-structure.md), 설계 문서 FR-6

## 1. 배경 및 문제 상황 (Context and Problem Statement)

* **상황:** T30(ADR 0011)은 인증 없이 열려 있던 preview Ingress(`:8080`)를 지웠다. green 파드, `<release>-preview` Service, Slack 승격 버튼은 그대로다. 자동 판단(promote-judge)은 port-forward로 green을 본다.
* **문제:** 사람이 green을 볼 방법이 없어졌다.
  * regulated 대상은 사람이 승격해야 진행된다(T6). 지금 Slack 알림의 preview 자리에는 `(비공개: 인증된 Kubernetes port-forward로 검증)`만 나온다. 승인자는 green을 열어 보지 못하고 AI 판단만 보고 버튼을 누르게 된다.
  * 승인자마다 kubeconfig를 주고 port-forward를 시키는 것은 현실적이지 않고, 클러스터 권한을 필요 이상으로 넓힌다.
  * 설계 문서 FR-6은 "승격 전 미리보기 주소를 제공한다"이다. 지금은 이 요구를 만족하지 않는다.
* **목표:**
  * 승인자가 Slack 링크 하나로 green을 연다. 인증되지 않은 요청은 green에 닿지 않는다.
  * 사용자 원장(SSOT)은 이미 쓰고 있는 IAM Identity Center 하나다(`org/sso.tf`). 대상마다 사용자를 따로 만들지 않는다.
  * aws · gcp · onprem에서 같은 방식으로 동작한다(ADR 0003의 이식성 목표).
  * 템플릿에는 범용 입력만 두고, 팀 전용 설정(Identity Center)은 `org/`와 demo-app에 둔다.

## 2. 고려한 옵션들 (Considered Options)

Identity Center는 직접 만든 앱에 SAML IdP로 동작한다. ALB · oauth2-proxy가 쓰는 범용 OIDC 엔드포인트는 없다. 그래서 어느 옵션이든 **Cognito User Pool을 OIDC 중계로 둔다**: Identity Center(SAML) → Cognito(OIDC issuer). 옵션은 인증을 어디서 강제하느냐로 나뉜다.

### 1. 대상별 네이티브 인증

aws는 ALB `authenticate-cognito`, gcp는 IAP + Identity Platform, onprem은 Cloudflare Access로 강제한다.

**Pros**
* 클러스터 안에 추가 컴포넌트가 없다. AWS는 annotation 몇 줄이다.

**Cons**
* 구현이 세 가지다. 차트 · 워크플로 분기가 늘고 각각 따로 검증해야 한다.
* IAP와 Cloudflare Access는 각 플랫폼의 별도 설정(Identity Platform, Zero Trust 조직)이 필요하다.

### 2. 차트 안 oauth2-proxy (선택)

preview를 켠 릴리스마다 oauth2-proxy를 띄우고, preview Ingress(또는 터널)는 oauth2-proxy로만 보낸다. oauth2-proxy는 Cognito를 OIDC issuer로 쓰고, 인증된 요청만 `<release>-preview`로 넘긴다.

**Pros**
* 대상과 관계없이 같은 차트 코드다. Ingress나 터널이 무엇이든 그 뒤에서 동작한다.
* k3d에서도 그대로 시험할 수 있다.

**Cons**
* 릴리스마다 파드가 하나 더 뜬다(preview를 켠 릴리스만).
* 클라이언트 시크릿과 쿠키 시크릿을 Kubernetes Secret으로 넣어야 한다.

### 3. 승인자가 직접 port-forward

**Pros**
* 추가 구성이 없다.

**Cons**
* 승인자마다 클러스터 자격증명이 필요하다. Slack 승인 흐름(T26)과 맞지 않는다.

## 3. 결정 사항 (Decision Outcome)

* **옵션 2를 선택한다.** 사용자 원장은 Identity Center, OIDC 중계는 Cognito, 강제 지점은 차트 안 oauth2-proxy다.
* AWS에서 ALB 네이티브 인증으로 바꾸는 것은, oauth2-proxy 운영이 부담이 될 때 다시 검토한다. Cognito는 그대로 쓸 수 있다.

```
승인자 → green.<host> (ALB / GCE Ingress / Cloudflare Tunnel)
          └ oauth2-proxy ──OIDC──> Cognito User Pool ──SAML──> IAM Identity Center
               └ 인증된 요청만 → <release>-preview (ClusterIP) → green 파드
```

**ADR 0011과의 관계:** ADR 0011이 막은 것은 "인증 없는 공개 preview"다. 이 ADR은 인증이 강제된 경우에만 preview 주소를 허용한다. 차트는 인증 설정 없이 preview Ingress를 렌더하지 않는다. T30의 회귀 테스트(인증 없는 preview 없음)는 유지하고, 인증을 켠 조합만 테스트를 추가한다. 합의되면 ADR 0011에 이 문서를 가리키는 보완 문단을 넣는다.

## 4. 구성

| 위치 | 내용 |
|---|---|
| `charts/app` | `previewAuth.enabled`, `previewAuth.host`, `previewAuth.issuerUrl`, `previewAuth.remoteKey`(클라이언트 ID · 시크릿 · 쿠키 시크릿을 담은 클라우드 시크릿, ClusterSecretStore로 가져온다), 허용 이메일 도메인. 켜면 oauth2-proxy Deployment · Service · ExternalSecret과, `ingress.enabled`일 때 Ingress를 만든다. 꺼져 있으면 지금과 같다. |
| `modules/preview_auth/aws` | Cognito User Pool, 도메인, 앱 클라이언트, SAML IdP(메타데이터 URL은 변수). 콜백 URL 목록을 받는다. 다른 팀은 SAML IdP 자리에 자기 IdP를 넣으면 된다. |
| `org/` (팀 전용) | Identity Center 고객 관리형 SAML 앱, 승인자 그룹 할당. SAML 앱의 ACS URL · 속성 매핑을 API로 설정할 수 없으면 `org/README.md`의 "콘솔 설정" 표에 적는다. |
| demo-app | 모듈 호출, green 호스트 DNS · 인증서, 대상별 values, 시크릿 주입. |
| `deploy.yml` | preview 인증을 켠 릴리스는 Slack 알림과 실행 요약에 `https://green.<host>/`를 다시 넣는다. |
| promote-judge | 변경 없음. 지금처럼 port-forward로 smoke를 보낸다. |

**접근 대상:** Identity Center에서 SAML 앱에 할당한 그룹만 로그인할 수 있다. 기본은 `onetatchi-admin`(승인자)이다. `readonly` 그룹에 열지는 T31에서 정한다.

**호스트:** aws는 `green.onetatchi.soulee.dev`, `green-yolo.onetatchi.soulee.dev`(Route53). 인증서가 `*.onetatchi.soulee.dev`라서 `green.yolo.…`처럼 두 단계인 이름은 덮지 못한다. onprem은 Quick Tunnel 주소가 바뀌어 Cognito 콜백 URL을 고정할 수 없으므로 Named Tunnel이 필요하다. `onetatchi.soulee.dev` 아래는 Route53에 위임돼 있으므로, Cloudflare 영역(`soulee.dev`) 아래 별도 이름이 필요한지 확인한다. gcp는 GCE Ingress 주소에 붙일 호스트를 정한다.

## 5. 결과와 남는 위험

* 인증된 승인자는 Slack 링크로 green을 연다. 인증되지 않은 요청은 oauth2-proxy에서 Cognito 로그인으로 돌려보내지고 green에 닿지 않는다.
* **green FE가 blue BE를 부르는 문제는 `previewAuth.routes`로 해결한다.** demo-app FE의 nginx는 `/api/`를 `demo-app-be`(active Service)로 프록시한다. 그래서 green 호스트에서는 oauth2-proxy가 `/api/`를 nginx 대신 `demo-app-be-preview`로 바로 보낸다. 파드 설정은 바꾸지 않으므로 승격 뒤 active 트래픽에는 영향이 없다. BE가 바뀌지 않은 배포에서는 BE preview가 active와 같다.
* **인증은 비밀번호 하나다.** Identity Center MFA가 꺼져 있다(ADR 0001). 해커톤 범위에서는 받아들이고, 운영으로 쓰려면 MFA를 켠다.
* **onprem · gcp 인증이 AWS에 의존한다.** Identity Center와 Cognito가 AWS에 있으므로 AWS 장애 시 다른 대상의 green 미리보기도 열리지 않는다. 승격 버튼과 promote-judge는 영향을 받지 않는다.
* 클러스터 내부 접근 격리(NetworkPolicy · RBAC)는 이 결정과 별개로 T30에 남는다.
* Cognito 요금: SAML 페더레이션 사용자의 무료 MAU 범위는 적용 전에 확인한다. 팀 규모(5명)에서는 비용이 거의 없을 것으로 예상한다.

참고: [Cognito SAML IdP](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-saml-idp.html), [Identity Center 고객 관리형 SAML 앱](https://docs.aws.amazon.com/singlesignon/latest/userguide/customermanagedapps-saml2-setup.html), [oauth2-proxy OIDC](https://oauth2-proxy.github.io/oauth2-proxy/configuration/providers/openid_connect).
