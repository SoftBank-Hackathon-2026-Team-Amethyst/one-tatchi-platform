# 실행 기록 생성 도구

`scripts/yolo_log.py`는 `.deploy/log/<YYYYMMDD-HHMMSS>-{analyze,provision,yolo}.md` 세 파일을 한 번에 만든다. 기록을 손으로 세 번 쓰는 왕복을 줄이기 위한 것이고, 값은 전부 인자로 받는다. 도구는 추측하지 않는다.

```sh
python3 "<skill-dir>/scripts/yolo_log.py" \
  --actor silano08 --branch yolo/deploy-test --base b8bc6d8 --target aws \
  --started "2026-10-10 17:20" \
  --reuse "기준 커밋 3b0caf7(같은 날): be/ fe/ db/ deploy/ 변경이 서비스 계약을 바꾸지 않음" \
  --recommendation "aws · 전체 USD 331.973 · 예산 over(10만 원). 더 싼 클라우드 후보 없음" \
  --assumption "민감 데이터 '예'는 사내 보관 요구가 아님" \
  --warning "config.yaml template_version 정합은 CODEOWNERS PR" \
  --change "deploy/values-be.yaml APP_VERSION v2.0.1 (changes 필터 통과용)" \
  --verify "be lint · test 8/8 · build 통과" --verify "docker build be · fe 통과"
```

- `--reuse`를 주면 재사용 모드: analyze · provision 기록이 짧은 형식이 된다. 일부 분석기를 돌렸으면 `--rerun`에 적는다.
- `--reuse` 없이 `--analysis`를 주면 전체 실행 모드.
- `--compliance`를 생략하면 `.deploy/config.yaml`에서 읽는다. `template_version`도 거기서 읽는다.
- 같은 시각의 파일이 이미 있으면 덮어쓰지 않고 1로 끝난다. `--dry-run`은 내용만 출력한다.
- 검증 결과(`--verify`)가 아직 없으면 provision 기록에 "아직 없음"이 남는다. push 전에 채운다.
- 수정 루프의 기록(`<시각>-<초기 SHA>-yolo.md`)은 `repair_loop.py`가 따로 만든다. 이 도구는 최초 push 전 기록만 담당한다.
