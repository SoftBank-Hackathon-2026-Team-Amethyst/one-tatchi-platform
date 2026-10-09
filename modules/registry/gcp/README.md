# registry/gcp

서비스별 Docker Artifact Registry 저장소를 만든다. 기본 리전은 서울이며 최근 이미지 버전 30개를 유지한다.

```hcl
module "registry" {
  source       = "../../modules/registry/gcp"
  repositories = ["demo-app-be", "demo-app-fe"]
}
```

Google provider에 프로젝트와 인증을 설정한다. 입력은 `repositories`(저장소 이름 집합), `keep_images`(기본 30), `region`(기본 `asia-northeast3`)이다.

`repository_urls`는 저장소 이름별 전체 이미지 주소를 반환한다. 예: `asia-northeast3-docker.pkg.dev/one-tatchi-gejkm/demo-app-be/demo-app-be`. 호출자는 여기에 `:태그`를 붙여 push와 배포에 사용한다. 저장소마다 같은 이름의 이미지 경로 하나를 사용한다.

전체 버전을 삭제 후보로 지정하고 이미지 경로마다 최근 N개를 유지한다. KEEP 정책이 우선하며 정리는 비동기다. 다중 아키텍처 이미지의 하위 manifest는 상위 manifest가 참조하는 동안 남을 수 있다. 배포 중인 버전은 별도로 보호하지 않으므로 보관 범위 밖 버전으로 재배포할 수 없다.

AWS ECR과 달리 GCP는 태그 변경 금지 시 태그가 있는 이미지도 정리할 수 없어 `immutable_tags = false`를 사용한다. 같은 태그를 다시 push할 수 있으므로 C7 호출부는 커밋 SHA 태그를 사용해야 한다. IAM은 이 모듈에서 변경하지 않는다. 노드 읽기는 C3, CI 쓰기는 C5에서 연결한다.

참고: [GCP 정리 정책](https://docs.cloud.google.com/artifact-registry/docs/repositories/cleanup-policy), [Terraform 리소스](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/artifact_registry_repository).
