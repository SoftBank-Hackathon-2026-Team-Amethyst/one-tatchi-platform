output "repository_urls" {
  description = "저장소 이름별 전체 이미지 주소 (태그 제외)"
  value = {
    for name, repository in google_artifact_registry_repository.this :
    name => "${repository.location}-docker.pkg.dev/${repository.project}/${repository.repository_id}/${name}"
  }
}
