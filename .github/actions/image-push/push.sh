#!/usr/bin/env bash
# 서비스 이미지를 빌드해 배포 대상 레지스트리에 올리고, 저장소 주소(태그 제외)를 stdout 마지막 줄에 출력한다.
# 같은 태그가 있으면 건너뛴다 (태그 덮어쓰기 금지, test에서 만들고 검사한 이미지를 prod가 그대로 쓴다).
# 사용법: push.sh <target> <name> <path> <tag>
# 환경변수: ECR_REGISTRY(aws), GH_TOKEN · OWNER(onprem), SOURCE(이미지 라벨)
set -euo pipefail
target="$1" name="$2" context="$3" tag="$4"

# 로그인 정보는 job 전용 위치에 둔다 (self-hosted runner의 키체인 · 기본 설정을 쓰지 않는다).
export DOCKER_CONFIG="$RUNNER_TEMP/docker"
mkdir -p "$DOCKER_CONFIG"
case "$target" in
  aws)
    repo="$ECR_REGISTRY/$name"
    exists() { aws ecr describe-images --repository-name "$name" --image-ids imageTag="$tag" >/dev/null 2>&1; } ;;
  gcp)
    : "${GCP_REGION:?GCP_REGION is required}" "${GCP_PROJECT:?GCP_PROJECT is required}"
    repo="$GCP_REGION-docker.pkg.dev/$GCP_PROJECT/$name/$name"
    gcloud auth configure-docker "$GCP_REGION-docker.pkg.dev" --quiet >&2
    exists() { gcloud artifacts docker images describe "$repo:$tag" --project "$GCP_PROJECT" >/dev/null 2>&1; } ;;
  onprem)
    repo="ghcr.io/$(echo "$OWNER" | tr '[:upper:]' '[:lower:]')/$name"
    # docker login은 macOS에서 키체인에 저장하려다 launchd 서비스(runner)에서 실패한다.
    # 설정 파일에 auths가 있으면 Docker CLI가 기본 키체인 저장소를 고르지 않으므로 직접 적는다.
    # RUNNER_TEMP는 job이 끝나면 지워진다.
    printf '{"auths":{"ghcr.io":{"auth":"%s"}}}' "$(printf '%s:%s' "$GITHUB_ACTOR" "$GH_TOKEN" | base64 | tr -d '\n')" \
      > "$DOCKER_CONFIG/config.json"
    exists() { docker manifest inspect "$repo:$tag" >/dev/null 2>&1; } ;;
  *)
    echo "::error::지원하지 않는 배포 대상: $target (aws | gcp | onprem)" >&2; exit 1 ;;
esac

if exists; then
  echo "image $repo:$tag already exists" >&2
else
  # 이미지는 runner의 아키텍처로 빌드된다 (EKS ubuntu runner amd64, 맥북 runner arm64).
  docker build --label "org.opencontainers.image.source=$SOURCE" -t "$repo:$tag" "$context" >&2
  # 배포할 바로 그 이미지를 push 전에 검사한다 (checks의 image-scan은 다른 runner에서 따로 빌드한 이미지라 같지 않다).
  # 기준은 checks와 같다: HIGH 이상, 수정 버전 있는 것만, .trivyignore 예외.
  command -v trivy >/dev/null || { echo "::error::trivy가 없다 (deploy.yml의 setup-trivy 단계)" >&2; exit 1; }
  ignore=(); [ -f .trivyignore ] && ignore=(--ignorefile .trivyignore)
  trivy image --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 "${ignore[@]}" "$repo:$tag" >&2
  docker push "$repo:$tag" >&2
fi
echo "$repo"
