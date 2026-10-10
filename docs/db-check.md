# DB 연결 확인 절차

배포 뒤, 그리고 "메모리 모드"가 의심될 때 BE가 실제 DB에 붙어 있는지 확인하는 순서다. 배경과 결정은 [ADR 0016](adr/0016-cloud-db-tls-and-memory-fallback.md).

## 1. 공개 주소에서 확인 (blue, 승격된 버전)

```sh
curl -s https://<도메인>/api/info | jq '{dbConnected, version, env}'
curl -s -o /dev/null -w '%{http_code}\n' https://<도메인>/health   # 200이어야 한다. 503이면 DB 미연결
curl -s https://<도메인>/health | jq '{status, database}'            # database: connected
```

AWS test는 `yolo.<도메인>`, prod는 `<도메인>`. 온프레미스는 Quick Tunnel 주소(배포 알림에 있다). `dbConnected: false`나 `database: fallback-memory`면 메모리 모드다.

## 2. 데이터가 남는지 확인

방명록에 글을 남기고 BE 파드를 지운 뒤(`kubectl delete pod -n <env> -l app.kubernetes.io/name=<앱>-be`) 글이 남아 있으면 DB에 쓰고 있는 것이다. 메모리 모드면 시드 글("시스템 안내")만 남는다.

## 3. green(승격 전)에서 확인

green은 공개 주소가 없다. port-forward로 본다(ADR 0003).

```sh
kubectl port-forward -n <env> svc/<앱>-be-preview 18000:8000 &
curl -s http://127.0.0.1:18000/api/info | jq .dbConnected
```

승격 판단의 smoke 결과(`promote-judgment-<env>` artifact의 `smoke-results.jsonl`)에서 `body_mismatch`가 있는 줄이 메모리 모드 신호다. abort 사유에 `database="fallback-memory" (기대 "connected")`가 보인다.

## 4. 메모리 모드일 때 점검 순서

1. **Secret 키**: `kubectl get secret -n <env> <앱>-db -o jsonpath='{.data.DATABASE_URL}' | base64 -d`. `postgresql://…?sslmode=require` 형식이어야 한다. 없으면 ExternalSecret 상태(`kubectl describe externalsecret`)와 클라우드 시크릿을 본다.
2. **값 파일**: `deploy/values-<서비스>.yaml`에 `env.PGSSL: require`가 있는지. `check-artifacts.sh`가 잡지만 손으로 고친 값 파일은 빠질 수 있다.
3. **DB 쪽 TLS**: RDS는 `rds.force_ssl` 파라미터, Cloud SQL은 `ssl_mode`, 온프레미스는 Postgres args의 `ssl=on`. 앱이 TLS 없이 붙으면 `no pg_hba.conf entry … no encryption` 오류가 BE 로그에 남는다.
4. **마이그레이션 Job 로그**: `kubectl logs -n <env> job/<앱>-be-migration`. 마이그레이션이 성공했는데 앱만 실패하면 네트워크 · 자격증명은 문제가 없고 앱의 TLS 설정만 본다.
5. **BE 로그**: `[DB] Could not connect to PostgreSQL` 줄의 오류 메시지가 원인을 말해 준다. 연결 시간 초과(2초)면 보안그룹 · 서브넷, 인증 오류면 Secret 값이다.

DB가 살아난 뒤에는 앱이 다음 health check에서 재연결한다. 파드를 다시 띄울 필요는 없지만, 메모리에 쓰인 데이터는 DB로 옮겨지지 않는다.
