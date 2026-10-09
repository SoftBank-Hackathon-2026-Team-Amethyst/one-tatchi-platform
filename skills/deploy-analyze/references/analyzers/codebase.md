# 코드베이스 분석기

대상 레포가 무엇으로 만들어졌고 어떻게 실행되는지 알아낸다. 다른 분석기와 `plan.yaml`의 `services`, 그리고 `deploy-provision`의 Dockerfile · 값 파일 · 검사 입력이 이 결과에 의존한다.

## 조사할 것

- **서비스 단위.** 독립 프로세스로 뜨는 것(프론트엔드, API, 워커 등)을 찾는다. 각각 경로, 언어와 런타임 버전, 프레임워크, 패키지 매니저, 실행 명령, 수신 포트.
- **컨테이너화.** Dockerfile · compose 파일이 있는지. 없는 Dockerfile은 "필요한 코드 수정"에 올린다. 있으면 App Chart가 강제하는 조건에 맞는지 본다: non-root **숫자 UID**(`USER 1000`처럼 이름이 아닌 숫자), 읽기 전용 루트 파일시스템에서 동작(쓰기 경로는 `writablePaths`로 선언), 런타임 환경변수를 이미지에 굽지 않음.
- **데이터 저장소.** DB 종류와 버전, 스키마 정의 위치(예: `db/init.sql`), 마이그레이션 도구와 명령. 여러 인스턴스를 막는 저장소(SQLite, 파일 저장)는 운영 DB로 교체 대상.
- **상태.** 로컬 디스크에 쓰는 업로드 · 세션 · 캐시. 인스턴스 간 공유되지 않으면 깨지는 것.
- **설정.** 서비스마다 읽는 환경변수와 출처(DB 접속 → Secret `<서비스>-db`의 `DATABASE_URL` · `PG_URL`, 다른 서비스 주소 → k8s Service 이름 `http://<릴리스>:<포트>`, 비밀값 → Secret, 고정값 → `env`). 빌드 시점에 읽는지 실행 시점에 읽는지.
- **헬스체크.** 경로가 있는지(`/health`). 없으면 추가 대상.
- **검사 명령.** 파이프라인 `checks.yml`은 고정 명령을 돌린다. 레포가 그 명령을 제공하는지 확인한다.
  - Node(pnpm): `pnpm install --frozen-lockfile`, `pnpm lint`, `pnpm build`. `lint` · `build` 스크립트가 없으면 추가 대상. lockfile이 없으면 추가 대상.
  - Python(uv): `uv sync --frozen`, `uv run ruff check`, `uv run pytest`. `uv.lock`이 없으면 추가 대상.
  - 테스트가 Postgres를 쓰면 `db-init` SQL 경로.

## 찾는 방법

매니페스트(`package.json`, `pyproject.toml`, `go.mod` 등), lockfile, 런타임 버전 파일, compose 파일, `.env.example`, README · docs를 읽는다. 실행 명령과 포트는 문서보다 코드와 스크립트를 믿는다.

## 결과 형식

`.deploy/analysis/codebase.md`

```md
# 코드베이스 분석

## 서비스
| 이름 | 경로 | 스택 | 실행 명령 | 포트 | 헬스체크 | Dockerfile | 외부 노출 |

## 데이터 저장소
## 상태
## 환경변수
| 서비스 | 이름 | 출처 | 읽는 시점 |

## 검사 명령 (checks.yml 입력)
- node-dirs: [...] / python-dirs: [...] / image-dirs: [...] / db-init: ...
- 빠진 스크립트 · lockfile:

## 필요한 코드 수정
## 확인 못 한 것
## 가정
```

서비스 이름은 `<앱>-<서비스>`(예: `demo-app-be`)로 쓴다. 이미지 저장소 · Rollout · k8s Service 이름이 모두 이 이름이다.
