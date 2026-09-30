locals {
  common_labels = {
    project    = "corvita-icu"
    env        = var.env
    managed_by = "terraform"
  }

  enabled_apis = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "storage.googleapis.com",
    "logging.googleapis.com",
    "iam.googleapis.com",
    "billingbudgets.googleapis.com",
  ])
}

data "google_project" "this" {}

# --- APIs ---

resource "google_project_service" "enabled" {
  for_each = local.enabled_apis

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# --- Storage for artifacts and data snapshots ---

resource "google_storage_bucket" "artifacts" {
  name                        = "${var.project_id}-icu-artifacts-${var.env}"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = var.force_destroy_bucket

  versioning {
    enabled = true
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      num_newer_versions = 5
      with_state         = "ARCHIVED"
    }
  }

  labels = local.common_labels
}

# --- Container registry ---

resource "google_artifact_registry_repository" "api" {
  location      = var.region
  repository_id = "icu-api"
  format        = "DOCKER"
  description   = "Container images for the ICU mortality API."

  docker_config {
    immutable_tags = true
  }

  labels = local.common_labels

  depends_on = [google_project_service.enabled]
}

# --- Identities ---

resource "google_service_account" "api" {
  account_id   = "icu-api-runtime-${var.env}"
  display_name = "ICU API Cloud Run runtime (${var.env})"
}

resource "google_service_account" "deployer" {
  account_id   = "icu-api-deployer-${var.env}"
  display_name = "ICU API CI deployer (${var.env})"
}

resource "google_project_iam_member" "deployer_run_developer" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_artifact_registry_repository_iam_member" "deployer_writer" {
  project    = var.project_id
  location   = google_artifact_registry_repository.api.location
  repository = google_artifact_registry_repository.api.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_service_account_iam_member" "deployer_runtime_user" {
  service_account_id = google_service_account.api.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_storage_bucket_iam_member" "data_team" {
  for_each = toset(var.data_team_members)

  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectUser"
  member = each.value
}

# --- API service (Cloud Run) ---

resource "google_cloud_run_v2_service" "api" {
  name                = "icu-api-${var.env}"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  labels = local.common_labels

  template {
    service_account = google_service_account.api.email

    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }

    timeout                          = "10s"
    max_instance_request_concurrency = 20

    containers {
      image = var.image

      ports {
        container_port = 8080
      }

      env {
        name  = "MODEL_VERSION"
        value = var.model_version
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle = true
      }

      startup_probe {
        http_get {
          path = "/health"
          port = 8080
        }
      }

      liveness_probe {
        http_get {
          path = "/health"
          port = 8080
        }
      }
    }
  }

  depends_on = [google_project_service.enabled]
}

# --- Invoker access ---

resource "google_cloud_run_v2_service_iam_member" "public" {
  count = var.allow_public_invoker ? 1 : 0

  project  = var.project_id
  location = google_cloud_run_v2_service.api.location
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# --- Budget ---

resource "google_billing_budget" "demo" {
  count = var.billing_account_id == "" ? 0 : 1

  billing_account = var.billing_account_id
  display_name    = "icu-mortality-${var.env}"

  budget_filter {
    projects = ["projects/${data.google_project.this.number}"]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(floor(var.budget_amount))
      nanos         = tonumber((var.budget_amount - floor(var.budget_amount)) * 1e9)
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }

  threshold_rules {
    threshold_percent = 0.9
  }

  threshold_rules {
    threshold_percent = 1.0
  }

  depends_on = [google_project_service.enabled]
}
