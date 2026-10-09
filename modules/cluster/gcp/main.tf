data "google_client_config" "current" {}

locals {
  # One pool per zone avoids interpreting desired=3 as three nodes in EACH zone.
  zones = sort(var.node_locations)
  pools = {
    for i, zone in local.zones : zone => {
      min     = floor(var.node_count.min / length(local.zones)) + (i < var.node_count.min % length(local.zones) ? 1 : 0)
      desired = floor(var.node_count.desired / length(local.zones)) + (i < var.node_count.desired % length(local.zones) ? 1 : 0)
      max     = floor(var.node_count.max / length(local.zones)) + (i < var.node_count.max % length(local.zones) ? 1 : 0)
    }
  }
}

resource "google_service_account" "nodes" {
  account_id   = "${substr(var.name, 0, 18)}-nodes-${substr(md5(var.name), 0, 5)}"
  display_name = "${var.name} GKE nodes"
}

resource "google_project_iam_member" "nodes" {
  for_each = toset([
    "roles/container.defaultNodeServiceAccount",
    "roles/artifactregistry.reader",
  ])
  project = data.google_client_config.current.project
  role    = each.value
  member  = "serviceAccount:${google_service_account.nodes.email}"
}

# Hosted GitHub runners have changing source IPs, matching the AWS public API setup.
# IAM/RBAC authenticate access; callers with fixed IPs can set authorized_networks.
# trivy:ignore:GCP-0061
resource "google_container_cluster" "this" {
  name                     = var.name
  location                 = var.region
  node_locations           = local.zones
  network                  = var.network_id
  subnetwork               = var.subnet_ids[0]
  min_master_version       = var.kubernetes_version
  remove_default_node_pool = true
  initial_node_count       = 1
  deletion_protection      = false
  enable_shielded_nodes    = true
  datapath_provider        = "ADVANCED_DATAPATH"

  release_channel {
    channel = "REGULAR"
  }

  ip_allocation_policy {
    cluster_secondary_range_name  = var.pods_range_name
    services_secondary_range_name = var.services_range_name
  }

  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = var.master_ipv4_cidr
  }

  dynamic "master_authorized_networks_config" {
    for_each = length(var.authorized_networks) > 0 ? [1] : []
    content {
      dynamic "cidr_blocks" {
        for_each = var.authorized_networks
        content {
          display_name = cidr_blocks.key
          cidr_block   = cidr_blocks.value
        }
      }
    }
  }

  workload_identity_config {
    workload_pool = "${data.google_client_config.current.project}.svc.id.goog"
  }

  master_auth {
    client_certificate_config {
      issue_client_certificate = false
    }
  }

  logging_service    = "logging.googleapis.com/kubernetes"
  monitoring_service = "monitoring.googleapis.com/kubernetes"

  monitoring_config {
    enable_components = ["SYSTEM_COMPONENTS"]
    managed_prometheus {
      enabled = true
    }
  }

  # The temporary default pool also uses the dedicated node identity.
  node_config {
    machine_type    = var.node_instance_types[0]
    service_account = google_service_account.nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
    metadata        = { disable-legacy-endpoints = "true" }
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }
  }

  depends_on = [google_project_iam_member.nodes]
}

resource "google_container_node_pool" "this" {
  for_each           = local.pools
  name               = "nodes-${each.key}"
  location           = var.region
  cluster            = google_container_cluster.this.name
  node_locations     = [each.key]
  initial_node_count = each.value.desired

  autoscaling {
    min_node_count = each.value.min
    max_node_count = each.value.max
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
  }

  node_config {
    machine_type    = var.node_instance_types[0]
    image_type      = "COS_CONTAINERD"
    disk_size_gb    = 30
    disk_type       = "pd-standard"
    service_account = google_service_account.nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
    metadata        = { disable-legacy-endpoints = "true" }

    workload_metadata_config {
      mode = "GKE_METADATA"
    }
    shielded_instance_config {
      enable_secure_boot          = true
      enable_integrity_monitoring = true
    }
  }

  lifecycle {
    # Autoscaler owns live size after creation, just as AWS desired_size can drift.
    ignore_changes = [initial_node_count]
  }
}
