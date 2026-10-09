terraform {
  required_version = ">= 1.11.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
  }
  # Initial bootstrap uses a separate temporary local root; migrate into this backend.
  backend "gcs" {
    prefix = "bootstrap/gcp"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_storage_bucket" "state" {
  name                        = "${var.project_id}-tfstate"
  project                     = var.project_id
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  versioning {
    enabled = true
  }
  lifecycle {
    prevent_destroy = true
  }
}

module "ci_identity" {
  source = "../../modules/ci_identity/gcp"

  project_id          = var.project_id
  repository_id       = var.repository_id
  repository_owner_id = var.repository_owner_id
  oidc_subject_prefix = var.oidc_subject_prefix
  state_bucket        = google_storage_bucket.state.name
}
