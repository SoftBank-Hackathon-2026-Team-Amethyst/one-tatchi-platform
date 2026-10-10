# 실패 증거의 비밀값 가리기 (T12). cluster.sh(bash) · collect.py · diagnose.py(Python)가 같은 규칙을 쓴다: sed -E -f redact.sed
# GitHub가 등록된 시크릿은 이미 ***로 가리지만, 클러스터 출력 · 앱 로그는 가리지 않는다.
# 값 문자 클래스에서 따옴표 · 쉼표 · 중괄호를 빼서 JSON 구조를 깨지 않는다.
s#(postgres(ql)?(\+[a-z0-9]+)?://)[^@/[:space:]"]+@#\1***@#g
s#(mysql|mongodb(\+srv)?|redis|amqps?)://[^@/[:space:]"]+@#\1://***@#g
s#([Bb]earer )[A-Za-z0-9._~+/=-]{8,}#\1***#g
s#(gh[pousr]_|github_pat_)[A-Za-z0-9_]{10,}#***#g
s#AKIA[0-9A-Z]{16}#***#g
s#xox[abprs]-[A-Za-z0-9-]{10,}#***#g
s#sk-ant-[A-Za-z0-9_-]{10,}#***#g
s#([Pp][Aa][Ss][Ss][Ww]([Oo][Rr])?[Dd]|[Ss][Ee][Cc][Rr][Ee][Tt]|[Tt][Oo][Kk][Ee][Nn]|[Aa][Pp][Ii]_?[Kk][Ee][Yy])(\\?["']?[[:space:]]*[=:][[:space:]]*\\?["']?)[^[:space:]"'\\,}]{3,}#\1\3***#g
