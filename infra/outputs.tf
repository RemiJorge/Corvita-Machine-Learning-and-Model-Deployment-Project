output "service_url" {
  description = "HTTPS URL of the Cloud Run service."
  value       = google_cloud_run_v2_service.api.uri
}

output "artifacts_bucket" {
  description = "GCS bucket for dataset snapshots, models, and reports."
  value       = google_storage_bucket.artifacts.name
}

output "image_repository" {
  description = "Artifact Registry path for API images (without image name or tag)."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.api.repository_id}"
}

output "runtime_service_account" {
  description = "Email of the Cloud Run runtime service account (no GCP roles)."
  value       = google_service_account.api.email
}

output "deployer_service_account" {
  description = "Email of the deployer service account for CI image push and Cloud Run deploy."
  value       = google_service_account.deployer.email
}
