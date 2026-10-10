# db_link / tailscale

앱과 DB가 다른 클러스터에 있을 때(T32 · T33) 둘을 잇는 비공개 통로. Tailscale Kubernetes Operator를 클러스터에 올리고,

- **publish**: 클러스터 안 DB(예: `demo-app-db-test.platform.svc.cluster.local:5432`)를 tailnet에만 내보낸다. 인터넷에 포트가 열리지 않는다.
- **consume**: 상대 클러스터가 publish한 DB를 보통의 ClusterIP Service(`<이름>.<네임스페이스>.svc.cluster.local`)로 끌어온다.

양쪽이 같은 모듈이라 방향을 바꿔도(앱=온프레미스, DB=AWS) 입력만 달라진다. 앱 · App Chart · 워크플로는 아무것도 몰라도 된다. `service-base`의 `database.host`에 `consumed[<이름>].host`를 넣으면 끝이다.

## 준비 (tailnet 1회)

1. ACL(`Access controls`)에 태그와 허용 규칙:
   ```json
   "tagOwners": {
     "tag:k8s-operator": ["autogroup:admin"],
     "tag:k8s":          ["tag:k8s-operator"],
     "tag:db-onprem":    ["tag:k8s-operator"],
     "tag:app-aws":      ["tag:k8s-operator"]
   },
   "grants": [{ "src": ["tag:app-aws"], "dst": ["tag:db-onprem"], "ip": ["5432"] }]
   ```
2. `Settings → Trust credentials`에서 OAuth 클라이언트: 스코프 **Devices → Core: Write**, **Keys → Auth Keys: Write**, (HA ProxyGroup을 쓸 거면 **Services: Read · Write**), 태그 `tag:k8s-operator`. 양쪽 클러스터가 같은 클라이언트를 써도 된다.
3. `DNS` 탭의 tailnet 이름(`xxxx.ts.net`)을 `tailnet` 입력에.

## 입력

| 이름 | 설명 |
|---|---|
| `cluster_name` | operator 기기 이름 접두 (`<cluster_name>-operator`) |
| `tailnet` | tailnet DNS 이름 |
| `create_oauth_secret` | 기본 true. false면 `tailscale/operator-oauth`(키 `client_id` · `client_secret`)를 다른 것이 만든다고 본다. CI로 apply하는 클라우드 루트는 service-base의 `secret` 블록(External Secrets)으로 만들고 이 모듈을 `depends_on`으로 뒤에 둔다 |
| `oauth_client_id`, `oauth_client_secret` | `create_oauth_secret`가 true일 때. ephemeral · sensitive. write-only Secret으로만 전달하고 state에 남지 않는다 |
| `manage_namespace` | 기본 true. service-base가 `tailscale` 네임스페이스를 만들면 false |
| `oauth_revision` | OAuth 값을 바꿨을 때 올린다 |
| `operator_chart_version` | `tailscale-operator` 차트 버전 (예: `1.102.4`) |
| `publish` | `{ <tailnet 호스트명> = { target, port = 5432, tags = ["tag:db-onprem"] } }`. Service는 `tailscale/publish-<호스트명>`에 생긴다 |
| `consume` | `{ <키> = { namespace, fqdn, name = <키>, port = 5432, tags = ["tag:app-aws"] } }`. Service 이름은 `name`(비우면 키) |

## 출력

| 이름 | 설명 |
|---|---|
| `published` | `{ <호스트명> = "<호스트명>.<tailnet>" }` → 상대 쪽 `consume.fqdn` |
| `consumed` | `{ <이름> = { host, port } }` → `service-base`의 `database.host` · `port` |

## 동작

- publish는 ExternalName Service에 `tailscale.com/expose` 어노테이션을 단다. operator가 프록시 파드(StatefulSet)를 만들어 target으로 포워딩한다. DB Service 자체는 건드리지 않는다.
- consume은 `tailscale.com/tailnet-fqdn` 어노테이션을 단 ExternalName Service. operator가 egress 프록시를 만들고 `externalName`을 그 headless Service로 바꾼다(모듈은 그 변경을 무시한다).
- 프록시는 `NET_ADMIN`을 쓴다(iptables DNAT). k3d(k3s)와 EKS 모두 허용돼 있다.
- TLS는 Postgres 쪽(`sslmode=require`)이 그대로 담당한다. 통로는 WireGuard로 한 번 더 암호화된다.

## 한계

- 단일 프록시(standalone). 프록시 파드가 재시작하는 동안 DB 연결이 끊긴다. HA가 필요하면 ProxyGroup으로 바꾼다.
- 온프레미스 DB가 내려가면 그 DB를 쓰는 클라우드 앱도 같이 멈춘다. BE는 `/health` 503으로 드러내야 한다(T28).
- 무료 tailnet은 사용자 3명 · 기기 100대. operator · 프록시는 사용자 수를 쓰지 않는다.
