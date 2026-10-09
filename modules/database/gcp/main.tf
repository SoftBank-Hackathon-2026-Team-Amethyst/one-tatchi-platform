resource "google_compute_global_address" "private_services" {
  name          = "${var.name}-sql-range"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  address       = cidrhost(var.private_services_cidr, 0)
  prefix_length = tonumber(split("/", var.private_services_cidr)[1])
  network       = var.network_id
}

resource "google_service_networking_connection" "sql" {
  network                 = var.network_id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_services.name]
  # Other managed services may still use this VPC peering at teardown.
  deletion_policy = "ABANDON"
}

resource "google_sql_database_instance" "this" {
  name                = var.name
  region              = var.region
  database_version    = "POSTGRES_${var.engine_version}"
  deletion_protection = var.deletion_protection
  settings {
    edition           = "ENTERPRISE"
    tier              = var.instance_class
    availability_type = var.multi_az ? "REGIONAL" : "ZONAL"
    disk_size         = var.storage_gb
    disk_type         = "PD_SSD"
    disk_autoresize   = true
    ip_configuration {
      ipv4_enabled    = false
      private_network = var.network_id
      ssl_mode        = "ENCRYPTED_ONLY"
    }
    backup_configuration {
      enabled    = true
      start_time = "18:00"
      backup_retention_settings {
        retained_backups = var.backup_retention_days
      }
    }
    database_flags {
      name  = "log_connections"
      value = "on"
    }
    database_flags {
      name  = "log_disconnections"
      value = "on"
    }
    database_flags {
      name  = "log_min_duration_statement"
      value = "1000"
    }
  }
  depends_on = [google_service_networking_connection.sql]
}

resource "google_sql_database" "app" {
  name     = var.database_name
  instance = google_sql_database_instance.this.name
}

resource "google_secret_manager_secret" "credentials" {
  project   = var.project_id
  secret_id = "${var.name}-credentials"
  replication {
    auto {}
  }
}

ephemeral "random_password" "credentials" {
  length  = 32
  special = false
}

resource "google_secret_manager_secret_version" "credentials" {
  secret                 = google_secret_manager_secret.credentials.id
  secret_data_wo         = jsonencode({ username = var.username, password = ephemeral.random_password.credentials.result })
  secret_data_wo_version = var.password_version
  lifecycle {
    create_before_destroy = true
  }
}

# Re-read the stored version ephemerally so a recreated SQL user uses the existing
# password, not a fresh random value that was never written to Secret Manager.
ephemeral "google_secret_manager_secret_version" "credentials" {
  project    = var.project_id
  secret     = google_secret_manager_secret.credentials.secret_id
  version    = google_secret_manager_secret_version.credentials.version
  depends_on = [google_secret_manager_secret_iam_member.credential_readers]
}

resource "google_sql_user" "app" {
  name                = var.username
  instance            = google_sql_database_instance.this.name
  password_wo         = jsondecode(ephemeral.google_secret_manager_secret_version.credentials.secret_data).password
  password_wo_version = var.password_version
}

resource "google_secret_manager_secret_iam_member" "credential_readers" {
  for_each  = var.credential_readers
  project   = var.project_id
  secret_id = google_secret_manager_secret.credentials.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = each.value
}
