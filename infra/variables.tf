variable "project_id" {
  type        = string
  description = "GCP project ID."
}

variable "region" {
  type        = string
  default     = "northamerica-northeast1"
  description = "GCP region for regional resources."
}

variable "env" {
  type        = string
  default     = "demo"
  description = "Environment suffix in resource names and labels."
}

variable "image" {
  type        = string
  description = "Full container image URI with tag, for example northamerica-northeast1-docker.pkg.dev/PROJECT/icu-api/icu-api:1.0.0."
}

variable "model_version" {
  type        = string
  default     = "1.0.0"
  description = "Value passed to the container as MODEL_VERSION."
}

variable "allow_public_invoker" {
  type        = bool
  default     = false
  description = "When true, grants allUsers the Cloud Run invoker role (demo only)."
}

variable "data_team_members" {
  type        = list(string)
  default     = []
  description = "IAM members allowed to read and write objects in the artifacts bucket, for example user:name@example.com."
}

variable "billing_account_id" {
  type        = string
  default     = ""
  description = "When non-empty, creates a billing budget alert for this project."
}

variable "budget_amount" {
  type        = number
  default     = 5
  description = "Monthly budget amount in the billing account currency."
}

variable "force_destroy_bucket" {
  type        = bool
  default     = false
  description = "When true, terraform destroy may delete a non-empty artifacts bucket."
}
