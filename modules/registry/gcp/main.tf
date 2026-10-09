data "google_client_config" "current" {}

resource "google_artifact_registry_repository" "this" {
  for_each = var.repositories

  project       = data.google_client_config.current.project
  location      = var.region
  repository_id = each.value
  description   = "Docker images for ${each.value}"
  format        = "DOCKER"
  mode          = "STANDARD_REPOSITORY"

  # Immutable tags prevent cleanup of tagged images in Artifact Registry.
  docker_config {
    immutable_tags = false
  }

  cleanup_policy_dry_run = false
  cleanup_policies {
    id     = "delete-older-versions"
    action = "DELETE"
    condition {
      tag_state = "ANY"
    }
  }
  cleanup_policies {
    id     = "keep-recent-versions"
    action = "KEEP"
    most_recent_versions {
      keep_count = var.keep_images
    }
  }
}
