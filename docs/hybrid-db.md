# 운영 중인 환경의 DB를 온프레미스로 옮기기 (계층별 배포 위치)

이미 RDS를 쓰는 앱의 환경을 온프레미스 DB(맥북 k3d 등)로 바꾸고, 다 옮긴 뒤 RDS를 정리하는 순서다. 계약과 결정은 [ADR 0018](adr/0018-layered-deploy-placement.md), 통로는 [ADR 0017](adr/0017-db-link-tailscale.md)과 [`modules/db_link/tailscale`](../modules/db_link/tailscale/README.md).

**자동화하지 않는다.** 스킬과 파이프라인은 데이터를 옮기거나 RDS를 지우지 않는다. 아래는 사람이 한 단계씩 확인하며 따르는 절차다. 무중단 이전은 범위 밖이라 쓰기를 멈추는 점검 시간이 필요하다.

> 이 절차는 아직 실제 운영 데이터로 실행해 보지 않았다(2026-10-10). 처음 따를 때는 test에서 먼저 한 번 돌려 보고 이 문서를 고친다.

## 이 절차가 필요 없는 경우

- **새 앱:** 옮길 데이터가 없다. `plan.yaml`에 `layers`만 적고 `database_scope`를 생략하면 처음부터 모든 환경이 온프레미스 DB를 쓰고 RDS를 만들지 않는다.
- **test만 옮기고 데이터는 버려도 될 때:** `database_scope: [test]`로 렌더 · 적용하면 된다. 빈 온프레미스 DB에는 배포마다 도는 마이그레이션 Job(`migration.sql`, `pre-install` · `pre-upgrade` hook)이 테이블을 만든다. 아래 "환경 하나 옮기기"의 2 · 4단계(백업 · 복원)를 건너뛴다.

## 준비 (한 번)

[`modules/db_link/tailscale/README.md`](../modules/db_link/tailscale/README.md) "준비"와 `deploy-provision`의 "사람이 할 일".

- tailnet ACL: `tag:app-aws → tag:db-onprem:5432`만 허용
- Secrets Manager: Tailscale OAuth(`one-tatchi/tailscale-oauth`, 키 `client_id` · `client_secret`)
- 옮길 환경마다:
  - 온프레미스 루트에서 그 환경의 DB를 `<앱>-db-<환경>`으로 publish
  - Secrets Manager `<앱>-db-onprem-<환경>`(키 `username` · `password`, 온프레미스 DB Secret과 같은 값)
- 작업 PC: AWS SSO 로그인, `aws` CLI, `kubectl`(`aws eks update-kubeconfig …`, `infra/envs/aws` 출력 `kubeconfig_command`)

## 환경 하나 옮기기 (RDS → 온프레미스)

한 번에 한 환경만 옮긴다. test를 먼저 옮기고 확인한 뒤 prod를 옮긴다. 아래 `<env>`는 옮길 환경, `<앱>`은 앱 이름(예: `demo-app`)이다.

### 1. 점검 시간 시작: 쓰기를 멈춘다

옮기는 동안 들어온 쓰기는 새 DB에 없다. 규제 대상(`compliance: regulated`) prod는 운영 승인과 같은 수준으로 공지 · 승인을 받는다.

```sh
kubectl -n <env> scale rollout <앱>-be --replicas=0     # BE를 내린다. FE는 그 동안 /api가 실패한다
```

### 2. RDS에서 백업한다

클러스터 안 임시 파드에서 지금 `<앱>-db` Secret(아직 RDS)을 읽어 덤프한다. RDS는 VPC 안에서만 닿는다.

```yaml
# pg-tools.yaml — 작업이 끝나면 지운다
apiVersion: v1
kind: Pod
metadata: { name: pg-tools, namespace: <env> }
spec:
  restartPolicy: Never
  containers:
    - name: pg
      image: postgres:17
      command: ["sleep", "3600"]
      envFrom: [{ secretRef: { name: <앱>-db } }]   # PG_URL · DATABASE_URL (sslmode=require)
```

```sh
kubectl apply -f pg-tools.yaml && kubectl -n <env> wait --for=condition=Ready pod/pg-tools
kubectl -n <env> exec pg-tools -- sh -c 'pg_dump --format=custom --no-owner --file=/tmp/rds.dump "$PG_URL"'
kubectl -n <env> exec pg-tools -- sh -c 'psql "$PG_URL" -Atc "select (select count(*) from guestbook), (select count(*) from votes)"'   # 테이블별 행 수를 적어 둔다 (demo-app 기준)
kubectl -n <env> cp pg-tools:/tmp/rds.dump ./rds-<env>-$(date +%Y%m%d%H%M).dump      # 로컬에도 보관한다
```

prod라면 RDS 스냅샷도 하나 만든다(되돌리기 · 감사용).

```sh
aws rds create-db-snapshot --db-instance-identifier <앱>-db --db-snapshot-identifier <앱>-db-before-onprem-<env>-$(date +%Y%m%d)
```

### 3. 계획을 바꾸고 인프라를 적용한다

- `.deploy/plan.yaml`의 `database_scope`에 `<env>`를 더한다(처음이면 `layers`도 적는다. 형식은 `skills/deploy-analyze/references/report-format.md`).
- `deploy-provision`으로 `infra/envs/aws`를 다시 렌더한다(`DB_LINK=true`, `DB_LINK_HCL`에 `<env>`). 모든 환경을 옮기는 마지막 단계여도 **여기서는 `database_scope`를 생략하지 않는다**(RDS를 남긴다). RDS 정리는 아래 별도 절차다.
- `check-artifacts.sh` 통과 → janto PR. `infra.yml`의 plan 코멘트에서 **`module.database`(RDS)에 destroy · replace가 없는지** 확인한다. 생기는 것은 `db_link` consume Service · `<env>`의 `service-base` 값 변경 정도여야 한다.
- 머지 → `infra.yml` apply.

apply 뒤 `<env>`의 `<앱>-db` ExternalSecret이 온프레미스 DB를 가리킨다. External Secrets는 1시간마다 다시 읽으므로 바로 반영한다.

```sh
kubectl -n <env> annotate externalsecret <앱>-db force-sync=$(date +%s) --overwrite
kubectl -n <env> get secret <앱>-db -o jsonpath='{.data.PG_URL}' | base64 -d | sed 's#//[^@]*@#//***@#'   # 호스트가 <앱>-db-onprem.<env>.svc… 인지
```

### 4. 온프레미스 DB로 복원한다

같은 임시 파드를 다시 만들어(Secret이 바뀌었으므로) 온프레미스 DB에 복원한다. 새 DB가 비어 있어야 한다. 이미 마이그레이션 Job이 만든 빈 테이블이 있으면 `--clean --if-exists`로 덮는다.

```sh
kubectl -n <env> delete pod pg-tools --ignore-not-found && kubectl apply -f pg-tools.yaml && kubectl -n <env> wait --for=condition=Ready pod/pg-tools
kubectl -n <env> cp ./rds-<env>-<시각>.dump pg-tools:/tmp/rds.dump
kubectl -n <env> exec pg-tools -- sh -c 'pg_restore --clean --if-exists --no-owner --dbname="$PG_URL" /tmp/rds.dump'
kubectl -n <env> exec pg-tools -- sh -c 'psql "$PG_URL" -Atc "select (select count(*) from guestbook), (select count(*) from votes)"'   # 2단계의 행 수와 같아야 한다
kubectl -n <env> delete pod pg-tools
```

### 5. 점검 시간 끝: BE를 다시 올리고 확인한다

```sh
kubectl -n <env> scale rollout <앱>-be --replicas=<원래 값>   # 0에서 새로 뜨는 파드는 바뀐 Secret을 읽는다
```

[DB 연결 확인 절차](db-check.md)대로 `/health`의 `database: connected`, `/api/info`의 `dbConnected: true`, 백업 전 행이 화면 · API에 보이는지, 새 글이 남고 BE 파드를 지워도 유지되는지 본다. 다음 배포의 승격 판단은 smoke `expect_body`(ADR 0016)로 DB 연결을 다시 확인한다.

### 되돌리기

`database_scope`에서 `<env>`를 빼고 다시 렌더 → PR → apply → `force-sync` → BE 재시작이면 Secret이 RDS로 돌아간다. **전환 뒤 온프레미스 DB에 들어온 쓰기는 RDS에 없다.** 필요하면 2 · 4단계를 반대 방향으로 한다.

## RDS 정리 (모든 환경을 옮긴 뒤)

> ⚠️ `modules/database/aws`는 기본값이 `deletion_protection = false`, `skip_final_snapshot = true`다. RDS 블록이 빠진 루트를 apply하면 **최종 스냅샷 없이 바로 지운다.** 아래 1 · 2단계를 건너뛰지 않는다.

1. 모든 환경이 온프레미스 DB로 붙어 있고(위 5단계 확인), 그 상태로 한 번 이상 배포 · 승격이 끝났는지 확인한다.
2. 수동 스냅샷을 만들고 `available`이 될 때까지 기다린다. 이 스냅샷이 RDS의 마지막 데이터다.
   ```sh
   aws rds create-db-snapshot --db-instance-identifier <앱>-db --db-snapshot-identifier <앱>-db-final-$(date +%Y%m%d)
   aws rds wait db-snapshot-available --db-snapshot-identifier <앱>-db-final-<날짜>
   ```
3. `plan.yaml`에서 `database_scope`를 지운다(= 모든 환경) → `NO_RDS=true`로 다시 렌더 → `check-artifacts.sh` 통과 → janto PR.
4. plan 코멘트에서 destroy 대상이 RDS와 그 부속(서브넷 그룹 · 보안 그룹 · 자격증명 시크릿)뿐인지 확인한다. 다른 자원이 바뀌면 멈춘다.
5. 머지 → apply. RDS 비용이 사라진다.

## 확인한 것 · 바뀌지 않는 것

- **`deploy.yml`:** 바꿀 것이 없다. 앱과 마이그레이션 Job은 `<앱>-db` Secret만 읽고, 그 값이 RDS인지 온프레미스인지 모른다. 새 DB의 테이블은 다음 배포의 `pre-upgrade` 마이그레이션이 만든다(SQL은 여러 번 실행해도 안전해야 한다).
- **`infra.yml`:** 바꿀 것이 없다. `db_link` 연결이 든 AWS 루트도 같은 plan · apply 경로로 반영된다(demo-app #69에서 실제 적용됨).
- **승격 판단:** DB가 끊긴 green은 smoke `expect_body`(`database: connected`)가 실패해 abort된다(ADR 0016). 단 이미 승격된 blue도 같은 DB를 쓰므로 온프레미스 DB가 내려가면 서비스도 멈춘다(ADR 0018 한계).
- **Secret 반영 시간:** ExternalSecret `refreshInterval`이 1시간이라 전환 직후에는 `force-sync`와 BE 재시작이 필요하다.
