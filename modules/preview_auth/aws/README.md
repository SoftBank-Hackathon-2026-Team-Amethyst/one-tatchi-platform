# preview_auth/aws

승인자용 green 미리보기([ADR 0015](../../../docs/adr/0015-authenticated-green-preview.md))의 OIDC 중계를 만든다. Cognito User Pool은 사용자를 직접 갖지 않는다. IdP(SAML)에 로그인한 사용자를 OIDC로 App Chart의 oauth2-proxy에 넘긴다. 직접 가입과 Cognito 자체 계정 로그인은 막는다.

## 연결

| 출력 | 넣는 곳 |
|---|---|
| `issuer_url` | App Chart `previewAuth.issuerUrl` |
| `secret_id` | App Chart `previewAuth.remoteKey`, `cluster_addons` `readable_secret_arns` |
| `saml_acs_url`, `saml_audience` | IdP SAML 앱의 ACS URL · Audience |

`callback_hosts`에는 green 호스트를 모두 넣는다(예: prod · test). 각 호스트의 `/oauth2/callback`만 허용한다. 와일드카드 인증서(`*.<도메인>`)는 한 단계만 덮으므로 `green.yolo.<도메인>` 같은 두 단계 이름은 쓰지 않는다(예: `green-yolo.<도메인>`).

## 적용 순서

IdP 앱을 만들려면 Cognito의 ACS URL이 필요하고, Cognito의 IdP 설정에는 IdP 메타데이터가 필요하다. 그래서 두 번 apply한다.

1. `saml_metadata_url`을 비우고 apply한다. User Pool과 도메인만 생기고, 아무도 로그인할 수 없다.
2. 출력 `saml_acs_url` · `saml_audience`로 IdP에 SAML 앱을 만들고 승인자 그룹을 할당한다. IdP가 이메일을 `saml_email_attribute`(기본 `email`) 속성으로 보내게 한다.
3. IdP의 SAML 메타데이터 URL을 `saml_metadata_url`에 넣고 다시 apply한다.

## 시크릿

oauth2-proxy 환경변수(`OAUTH2_PROXY_CLIENT_ID` · `OAUTH2_PROXY_CLIENT_SECRET` · `OAUTH2_PROXY_COOKIE_SECRET`)를 JSON으로 담은 Secrets Manager 시크릿을 만든다. 클라이언트 시크릿은 Cognito가 만들어 state에 남으므로, 사람이 값을 넣는 `modules/secret`과 달리 이 모듈이 값까지 쓴다. state 접근 권한이 곧 이 시크릿의 접근 권한이다.
