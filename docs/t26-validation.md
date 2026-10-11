# T26 알림과 종단 검증

T26 #35는 Slack에서 PR 처리·승격·운영 승인을 수행하고 요청자를 감사 로그에 남기는 작업이다.
이 변경은 배포 결과 알림의 잘못된 입력 연결을 고치고, 과거 실행을 읽기 전용으로 대조하는 도구를 추가한다.
실제 배포, 릴리스, main 머지, T26 완료 처리는 수행하지 않는다.

## 배포 영향

- 플랫폼 main 기준: `c61050baf32256af0ffb55b0471f15c21ebf711c`.
- 확인한 demo-app main: `056e2518b714a3a66db2b81e6fa8127e3700c666`, 워크플로 참조 `v2.14.0`.
- 새 알림은 플랫폼 릴리스와 앱의 참조 버전 갱신 뒤 적용된다. main 머지만으로 기존 고정 태그의 배포 동작이 바뀌지 않는다.
- 승인·자동 머지·승격 조건, job 의존 관계, 버튼 ID/value/생성 조건과 감사 JSON은 유지한다. 봇 이미지 변경은 필요 없다.
- 사용자에게 보여 줄 `flow`, `environment`, `stage`, `next-action`을 `audit-log`가 아니라 `slack-notify`로 전달한다.
- 다음 행동은 실측 → 실패/취소 → 성공한 자동 승격 → 수동 Paused → 그 밖의 상태 순으로 정한다.
  일부 서비스의 promote/abort만 성공해도 `executed`가 생길 수 있으므로 실패 상태에서는 전체 완료를 주장하지 않는다.
  이미 Healthy인 배포와 실측 후 Green 정리는 승격 대기로 표현하지 않는다.

## 읽기 전용 검증 도구

표준 라이브러리 Python 3.11 이상과 인증된 `gh`를 사용한다. 모든 원격 요청은
`gh api --hostname github.com --method GET`으로 제한한다. 클러스터·S3에 접근하거나
워크플로를 실행하지 않는다. 원본 로그·토큰은 보고서에 넣지 않고 항목별 판정과 근거 URL만 출력한다.
실제 감사 JSON은 Actions 로그에 출력된 사본으로 확인하며 S3 원본을 재조회한 것은 아니다.

```sh
python3 scripts/verify-t26-evidence.py \
  --repo SoftBank-Hackathon-2026-Team-Amethyst/demo-app \
  --target aws --services demo-app-be demo-app-fe \
  --pr 83 --deploy-run 38066128039/1 \
  --test-rollout-run 38066602377/1 --prod-rollout-run 38066599367/1
```

- 실행 식별자는 `ID/차수`를 권장한다. 차수를 생략하면 조회 시점의 최신 차수를 선택해 고정한다.
- `--pr`: 일반 PR의 병합·Slack 머지·보호 파일 승인 기록. 수동 재배포에는 필수가 아니다.
- `--deploy-run`: 확인할 main의 배포 실행. `workflow_dispatch`면 수동 재배포로 표시한다.
- `--test-rollout-run`, `--prod-rollout-run`: 해당 환경의 수동 Slack 승격 실행. auto 배포에서는 생략할 수 있으나 실제 활성 이미지 근거는 여전히 필요하다.
- `--yolo-run`: yolo 브랜치의 병합 전 test 실행. PR head와 연결한다. rebase 후 main SHA가 달라도 정상이며 main 실행의 test/prod 이미지는 별도로 대조한다.
- `--target`과 `--services`: 이번 보고서의 배포 대상과 전체 서비스 집합. 다중 대상 배포는 대상마다 따로 확인한다. 한 대상의 성공이 전체 matrix 성공을 의미하지 않는다.
- `--format json`: 기계가 읽을 수 있는 결과. 기본 출력은 Markdown이다. 필요하면 호출자가 파일로 리다이렉트한다.
- `--fixture <JSON>`: 저장된 API/log 구조의 모의 데이터만 읽는다. GitHub에 요청하지 않는다.

종료 코드: `0` 확인됨, `1` 불일치, `2` 미확인 또는 입력·조회 문제.
이 종료 코드를 배포의 필수 관문으로 연결하지 않는다.

### 판정 기준과 한계

1. 저장소·실행·차수·워크플로·대상·환경을 맞춘다. matrix job은 이름의 순서 대신 실제 대상과 환경으로 찾고 여러 후보면 미확인이다.
2. 일반 PR은 병합 SHA와 main push 실행을 연결한다. 실제 스킬 실행 로그가 없으면 이를 janto 스킬 호출이라고 표현하지 않는다.
3. yolo는 branch test → 병합 PR → 새 main 실행으로 연결한다. 수동 재배포를 yolo 자동 실행과 혼동하지 않는다.
4. 실제 timestamp가 붙은 `Name / Namespace / Status / Images` 출력에서 Green 준비 및 서비스별 Healthy stable/active digest를 확인한다.
   `IMAGES` 환경 입력은 기대 이미지일 뿐 활성 이미지의 증거가 아니다. `head_sha`, job success, AI의 promote 추천도 단독 증거가 아니다.
5. Paused인 서비스는 Green 준비 이후 실제 promote 명령 결과와 활성 상태가 필요하다. 수동 승격은 Slack 요청자의 promote 감사 JSON도 확인한다.
6. `regulated` 운영 승인은 해당 시도 시작 이후·prod job 시작 이전의 봇 승인 표지와 감사 요청자를 대조한다.
   승인 표지 자체에는 차수가 없으므로 이전 표지만 있으면 미확인이다. `none`은 승인 부재를 정상으로 본다.
7. 로그에 출력된 `Run` 스크립트·입력 묶음과 ANSI 색상으로 표시된 명령은 실행 증거에서 제외한다.
   감사 기록은 실제 `audit log: s3://...` 뒤 JSON만 인정한다.
8. 로그 만료·권한 부족·알 수 없는 YAML 표현·최종 이미지 관측 누락은 미확인이다. 명백히 다른 digest나 잘못된 시간 순서는 불일치다.
   현재 클러스터 상태, Slack 화면, 모든 과거 코드 버전의 로그 형식까지 보증하지 않는다.

GitHub의 보호 파일 규칙 전체를 복제하지 않는다. 현재 프로젝트의 `.deploy/config.yaml`과
`CODEOWNERS` 변경에 대한 Slack 리뷰 증거를 확인하며, 실제 승인 권한은 GitHub가 판단한다.

## 기존 기록에 적용한 결과 — 2026-10-11 KST

위 명령으로 과거 실행을 조회했으며 결과는 **불일치**, 경로는 **수동 재배포**다.

| 확인 대상 | 결과 |
|---|---|
| [배포 38066128039, 시도 1](https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/demo-app/actions/runs/38066128039/attempts/1) | test/prod 배포 job 성공, 동일 main 이미지, Slack 운영 승인과 감사 요청자 확인 |
| [test 승격 38066602377](https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/demo-app/actions/runs/38066602377/attempts/1) | 두 서비스 모두 Green 준비 이후 Healthy stable/active digest 일치 |
| [prod 승격 38066599367](https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/demo-app/actions/runs/38066599367/attempts/1) | 선택한 승격이 이번 prod Green 준비보다 먼저 발생. 이번 버전의 prod 승격 근거로 사용할 수 없음 |

prod rollout 자체가 실패했다는 뜻은 아니다. 그 실행은 성공했지만 새 버전 배포보다 앞선 승격이다.
현재 운영이 계속 이전 버전이라는 뜻도 아니다. 이후 실행은 이 보고서의 범위 밖이다.
PR #83의 Slack 리뷰·머지 기록과 이 수동 실행을 합쳐 janto 전체 완료로 보고하지 않는다.

## 검증과 후속 실배포 절차

```sh
uv run --no-project --with 'pyyaml>=6,<7' python -B -m unittest discover -s .github/actions/slack-notify/tests -v
python3 -B -m unittest discover -s scripts/tests -p test_t26_evidence.py -v
python3 -B scripts/verify-t26-evidence.py --fixture scripts/tests/t26-fixtures/ordinary.json
```

fixture는 합성 데이터이며 실제 배포 기록이 아니다. CI는 모의 데이터로만 검증한다.
알림 테스트는 실제 워크플로 스크립트와 composite action을 실행하되 curl을 교체해 Slack payload만 수집한다.

로컬 확인 결과: 알림 10개, 증거 판정 33개, 기존 yolo 16개, Slack 봇 41개 테스트와
promote-judge 모의 테스트 전체가 통과했다. 알림 테스트는 수정 전 입력 계약 오류와 연결 누락으로 실패하는 것도 확인했다.
워크플로 구조 비교에서 배포 job 의존성·승인 조건·버튼 선택 로직은 동일하다.
actionlint는 기준 main과 동일한 `create-github-app-token@v3`의 `client-id/app-id` 메타데이터 진단
6건만 남았으며 이번 변경에서 추가된 진단은 없다.

후속 실제 검증은 수정본의 릴리스·앱 반영을 별도로 승인받은 뒤 수행한다.
새 일반 PR의 Slack 리뷰/머지 → main test → test 승격 → 규제 대상 운영 승인 → prod Green 준비 →
prod 승격 순서로 실행하고, 각 단계 실행 ID/차수와 두 서비스의 활성 digest를 남긴다.
자동 승격 경로는 yolo branch와 rebase 후 main 실행을 각각 기록한다.
최종 활성 이미지가 로그에 없으면 추가 관측 근거를 남기기 전까지 미확인으로 둔다.
