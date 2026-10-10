#!/usr/bin/env bash
# 한 서비스의 Helm 값 파일을 적용 순서대로 출력한다 (한 줄에 하나). deploy.yml이 -f 인자를 만들 때 쓴다.
#   values-files.sh <기본 값 파일> <target> <environment>
# 순서 (뒤가 앞을 덮어쓴다):
#   1. deploy/values-<서비스>.yaml                 서비스 기본값 (모든 대상 · 환경 공통)
#   2. deploy/<target>/values.yaml                 대상별 덧붙임 (aws · gcp · onprem). 있을 때만
#   3. deploy/values-<서비스>.<environment>.yaml   환경별 덧붙임 (test · prod). 있을 때만 (T35)
# 환경별 파일이 가장 뒤라서 "test에서만 켜는 값"(장애 주입 등)은 3번에만 둔다. 파일이 없으면 이전과 같다.
set -euo pipefail

base="${1:?기본 값 파일}"; target="${2:?target}"; environment="${3:?environment}"
case "$base" in *.yaml) ;; *) echo "값 파일은 .yaml 이어야 한다: $base" >&2; exit 1 ;; esac

echo "$base"
[ -f "deploy/$target/values.yaml" ] && echo "deploy/$target/values.yaml"
env_file="${base%.yaml}.$environment.yaml"
[ -f "$env_file" ] && echo "$env_file"
exit 0
