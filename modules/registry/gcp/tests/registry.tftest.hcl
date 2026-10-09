mock_provider "google" {
  mock_data "google_client_config" {
    defaults = {
      project = "test-project"
    }
  }
}

variables {
  repositories = ["demo-app-be", "demo-app-fe"]
}

run "service_repositories_and_retention" {
  command = plan
  assert {
    condition = tomap(output.repository_urls) == tomap({
      demo-app-be = "asia-northeast3-docker.pkg.dev/test-project/demo-app-be/demo-app-be"
      demo-app-fe = "asia-northeast3-docker.pkg.dev/test-project/demo-app-fe/demo-app-fe"
    })
    error_message = "Each service must have its own repository and complete push address."
  }
  assert {
    condition = alltrue([for repository in google_artifact_registry_repository.this :
      repository.format == "DOCKER" && !repository.cleanup_policy_dry_run && !repository.docker_config[0].immutable_tags &&
      length(repository.cleanup_policies) == 2 &&
      length([for policy in repository.cleanup_policies : policy if policy.action == "DELETE" && try(policy.condition[0].tag_state, "") == "ANY"]) == 1 &&
      length([for policy in repository.cleanup_policies : policy if policy.action == "KEEP" && try(policy.most_recent_versions[0].keep_count, 0) == 30]) == 1
    ])
    error_message = "Cleanup must delete older tagged and untagged versions while preserving the latest 30."
  }
}

run "custom_retention" {
  command = plan
  variables {
    keep_images = 5
  }
  assert {
    condition = alltrue([for repository in google_artifact_registry_repository.this :
      length([for policy in repository.cleanup_policies : policy if policy.action == "KEEP" && try(policy.most_recent_versions[0].keep_count, 0) == 5]) == 1
    ])
    error_message = "Custom retention must be applied to all service repositories."
  }
}

run "reject_zero_retention" {
  command = plan
  variables {
    keep_images = 0
  }
  expect_failures = [var.keep_images]
}

run "reject_nested_repository_name" {
  command = plan
  variables {
    repositories = ["demo-app/be"]
  }
  expect_failures = [var.repositories]
}
