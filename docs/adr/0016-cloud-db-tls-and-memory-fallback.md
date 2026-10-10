# 0016: 클라우드 DB는 TLS 필수, 메모리 폴백은 정상 상태가 아니다

상태: 채택 (T28)

관련: T28, T7, T24, T32, T33, [ADR 0008](0008-gcp-database-credentials.md), 설계 문서 6.4 · 6.5, FR-9

## 배경

AWS test · prod의 BE가 RDS에 붙지 못하고 메모리 모드로 돌았다. `/api/info`는 `dbConnected: false`, 화면에는 "메모리 모드"가 떴고 방명록 · 투표가 재배포마다 사라졌다. 온프레미스는 정상이었다.

확인한 원인은 세 가지가 겹친 것이다.

- RDS Postgres 17(`rds.force_ssl=1`)과 Cloud SQL(`ENCRYPTED_ONLY`)은 TLS 없는 접속을 거부한다. 온프레미스 Postgres는 거부하지 않아 같은 코드가 거기서는 붙었다.
- service-base가 만드는 Secret의 `DATABASE_URL`은 `postgresql+psycopg://…`에 `sslmode`가 없었다. 마이그레이션 Job이 쓰는 `PG_URL`에만 `sslmode=require`가 있어 마이그레이션은 성공하고 앱만 실패했다.
- 앱의 `/health`는 DB가 끊겨도 200을 돌려줬다. smoke는 상태 코드만 봤으므로 메모리 모드의 green이 승격됐다.

## 결정

1. **클라우드 DB 접속은 TLS 필수다.** service-base Secret의 `DATABASE_URL` · `PG_URL`은 `postgresql://…?sslmode=require`로 같고, SQLAlchemy용 `SQLALCHEMY_URL`(`postgresql+psycopg://…?sslmode=require`)을 따로 둔다. 앱은 URL의 `sslmode`를 읽는 드라이버(psycopg · psql)면 그대로, 읽지 않는 드라이버(postgres.js)면 값 파일의 `env.PGSSL: require`로 TLS를 켠다. `check-artifacts.sh`가 DB Secret을 받는 서비스에 `PGSSL`이 있는지 검사한다.
2. **세 배포 대상은 같은 접속 설정을 쓴다.** 온프레미스 Postgres도 TLS를 켜(`modules/database/onprem`, 이미지의 자체 서명 인증서) `sslmode=require`가 어디서나 통과하게 한다. 대상마다 값을 바꾸지 않는다.
3. **`sslmode=require`는 암호화만 보장한다.** 서버 인증서의 CA · 이름 검증은 하지 않는다. 세 대상 모두 사설 네트워크 안의 DB라 지금은 받아들이고, 규제 대상이 실데이터를 다루게 되면 CA 번들과 `verify-full`로 올린다.
4. **메모리 폴백은 데모 안전장치이지 정상 상태가 아니다.** 앱은 실제 DB에 닿지 않으면 readiness(`/health`)를 503으로 떨어뜨린다. 파이프라인은 그것과 별개로 smoke의 `expect_body`로 본문을 본다(`/health`의 `database: connected`, `/api/info`의 `dbConnected: true`). 상태 코드가 200이어도 본문이 어긋나면 실패로 세어 규칙 판정이 fail이 되고 green은 abort된다(ADR 0004의 거부권).

## 영향

- Secret 키 `DATABASE_URL`의 값 형식이 바뀐다. psycopg · psql · postgres.js는 그대로 읽는다. SQLAlchemy로 `DATABASE_URL`을 읽던 앱은 `SQLALCHEMY_URL`로 바꿔야 한다. CI(`checks.yml`)의 Python job도 같은 두 키를 준다.
- `.deploy/smoke.json`에 `expect_body`가 생긴다. DB를 쓰는 서비스의 산출물은 헬스 경로에 이 조건을 넣는다. 조건이 없는 요청은 전과 같이 상태 코드만 본다.
- DB를 끊고 배포하면 승격되지 않는다. 데모 중 DB 장애를 일부러 보여 주려면 승격이 끝난 뒤 blue에서 한다.
- 운영 확인 절차는 [docs/db-check.md](../db-check.md).
