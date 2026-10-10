# [ADR-0016] 계층별 배포의 DB 통로: Tailscale Operator로 publish · consume

* **상태 (Status):** 제안(Proposed). T32 담당자(배규태)와 접점 합의 전
* **날짜 (Date):** 2026-10-10
* **관련:** T33, T32, T27, T28, [ADR 0012](0012-onprem-continuity-and-state.md), 설계 문서 6.4, FR-9, NFR-2

## 1. 배경 및 문제 상황 (Context and Problem Statement)

* **상황:** T32는 같은 앱 정의로 FE · BE는 AWS에, DB는 온프레미스(맥북 k3d)에 두는 조합을 지원한다. 온프레미스 Postgres는 클러스터 안 StatefulSet이고 외부 노출은 Cloudflare Quick Tunnel(HTTP 전용, 익명)뿐이다. RDS는 VPC 안에서만 닿는다.
* **문제:** EKS 파드가 맥북 Postgres에 붙을 길이 없다. 포트포워딩(공유기 · CGNAT)이나 공개 노출은 안 된다(DB 포트를 인터넷에 열지 않는다). 접속 정보는 AWS 쪽 `<앱>-db` Secret으로만 흘러야 하고(NFR-2), 앱 · 차트 · 워크플로는 조합을 몰라야 한다(FR-9).
* **제약:** 계정 · 예산 없음. 맥북에 상주 데몬을 늘리지 않는다(T27 재부팅 복구 범위를 넓히지 않는다). 반대 방향(앱=온프레미스, DB=AWS)도 같은 방식이어야 한다.

## 2. 고려한 옵션들 (Considered Options)

### 1. Cloudflare Named Tunnel + Access(TCP) + EKS `cloudflared access tcp` 프록시
* 장점: cloudflared를 이미 쓴다. 고정 호스트명이 생겨 온프레미스 FR-10도 같이 풀린다.
* 단점: Cloudflare 계정과 **Cloudflare에 올린 DNS 존**이 필요하다. `soulee.dev`는 Route53이라 서브존 위임이 선행된다. Access 서비스 토큰 · DNS 레코드 · 프록시까지 설정 조각이 많고, 프록시 홉이 하나 더 들어간다.

### 2. Tailscale 앱을 맥북에 설치 + EKS subnet router
* 장점: 커널 모드라 처리량이 좋다.
* 단점: 맥북 호스트에 데몬이 하나 더 생겨 T27의 launchd 복구 범위가 넓어진다. 맥북 밖(EKS)에서 k3d 내부 IP를 subnet route로 광고해야 해 Docker 네트워크 의존이 생긴다.

### 3. Tailscale Kubernetes Operator를 양쪽 클러스터에 (채택)
* DB 쪽: ExternalName Service에 `tailscale.com/expose`를 달아 DB를 tailnet에만 내보낸다(**publish**). 앱 쪽: `tailscale.com/tailnet-fqdn` ExternalName Service로 tailnet의 DB를 ClusterIP Service처럼 끌어온다(**consume**).
* 장점: 호스트에 아무것도 안 깐다. 양쪽이 같은 모듈이라 방향을 바꿔도 입력만 달라진다. 전부 Terraform · Helm으로 코드화된다. 계정만 있으면 되고 무료 범위(사용자 3명 · 기기 100대)로 충분하다. ACL 태그로 "AWS 앱 → 온프레미스 DB 5432"만 허용한다.
* 단점: 프록시가 iptables DNAT(`NET_ADMIN`)를 쓴다. standalone 프록시는 재시작 동안 끊긴다(HA는 ProxyGroup). 조정 서버는 Tailscale SaaS다(데이터 경로는 P2P WireGuard).

## 3. 결정 (Decision)

옵션 3. `modules/db_link/tailscale` 하나로 publish · consume을 모두 제공한다.

* **접점(T32와의 경계):** 앱 클러스터의 `<앱>-db` Secret에 `DATABASE_URL` · `PG_URL`(`sslmode=require`)이 들어오면 그 위(앱 · App Chart · 워크플로)는 바뀌지 않는다. `service-base`의 `database.host`에 `consumed[<이름>].host`를 넣는 것이 전부다.
* **대칭:** 반대 방향(앱=온프레미스, DB=RDS)은 EKS 쪽에서 RDS 엔드포인트를 publish하고 k3d 쪽에서 consume한다. RDS 보안 그룹에 EKS 노드 SG가 이미 허용돼 있어 추가 규칙이 없다. 첫 조합(FE · BE=AWS / DB=onprem)만 T32 완료 기준에 넣는다.
* **비밀값:** OAuth 클라이언트 값은 ephemeral 입력 → write-only Secret `tailscale/operator-oauth`. state에는 revision만 남는다. 온프레미스 루트는 onpremctl이 환경변수를 그대로 넘기므로 `TF_VAR_…`로 공급한다.
* **TLS:** 통로는 WireGuard로 암호화되고, 그 위에서 Postgres TLS(`sslmode=require`, T28)를 그대로 쓴다.
* **ACL:** `tag:app-aws → tag:db-onprem:5432`만 허용. 허용 태그가 없는 프록시는 대상 기기를 netmap에서 보지 못해 forwarding rule을 만들지 못한다(k3d에서 확인).
* **Cloudflare는 보류, 교체 가능:** Cloudflare 존이 생기면 `modules/db_link/cloudflare`로 publisher만 바꾼다. 입력 · 출력 계약(`publish` · `consume` · `published` · `consumed`)은 유지한다.

## 4. 결과 (Consequences)

* 좋은 점: 온프레미스 원칙("관리형 서비스를 쓰지 않는다")을 데이터 경로에서 지킨다. 맥북 재부팅 시 k3d가 뜨면 프록시 파드가 따라 뜬다(T27 범위 그대로).
* 감수할 점: 온프레미스 DB가 내려가면 그 DB를 쓰는 클라우드 앱도 멈춘다. BE는 메모리 폴백으로 숨기지 않고 `/health` 503으로 드러낸다(T28). 프록시 파드가 EKS에 2개(operator · egress) 늘어난다(t3.medium 파드 한도 계산에 포함, T29).
* 검증(2026-10-10, k3d): operator 합류 → `demo-app-db-test.tailb7ed7e.ts.net` publish → `test` 네임스페이스의 consume Service로 psql 접속. 클라이언트 주소가 publish 프록시, `pg_stat_ssl.ssl = t`. 허용 태그 없는 consume은 해석 실패. AWS EKS 쪽 consume은 T33 할 일 1의 남은 검증이다.
