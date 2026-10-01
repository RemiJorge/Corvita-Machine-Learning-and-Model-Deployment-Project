# Infrastructure

Terraform in `infra/` describes a demo deployment of the ICU mortality API on Google Cloud. Nothing in this repository applies Terraform to a real project unless a human runs `terraform apply` (optional item O1 in the roadmap).

## Why Google Cloud

See [010-gcp-target-cloud.md](decisions/010-gcp-target-cloud.md). Region default is `northamerica-northeast1` (Montréal). Cloud Run scales to zero, exposes HTTPS without a load balancer, and fits a low-traffic demo.

| Role | GCP (chosen) | AWS | Azure |
| --- | --- | --- | --- |
| Artifacts and data snapshots | Cloud Storage | S3 | Blob Storage |
| Container images | Artifact Registry | ECR | ACR |
| API runtime | Cloud Run | ECS Fargate | Container Apps |
| Logs | Cloud Logging | CloudWatch Logs | Azure Monitor |
| Identity | Service accounts + IAM | IAM roles | Managed identities |

## Architecture

```text
Reviewers / hospital integration
        |
        v  (HTTPS, invoker IAM; optional allUsers for demo)
Cloud Run service icu-api-<env>  (0--1 instances, 512 MiB, port 8080)
        |  runtime SA: no GCP roles; model in image (ADR 009)
        v
stdout JSON request logs (includes `severity` for Cloud Logging) --> Cloud Logging (_Default retention 30 days)

CI / deployer SA --> Artifact Registry (icu-api) --> image pull (platform)
Data team IAM members --> GCS artifacts bucket (snapshots, models, reports)
```

State lives in a versioned GCS bucket configured via `backend.hcl` (not in Git). Bootstrap that bucket by hand before the first `terraform init` with backend config.

## Terraform layout

All resources sit in one file, [infra/main.tf](../infra/main.tf). There are no modules: a single environment does not need the extra indirection.

| Terraform address | Purpose |
| --- | --- |
| `data.google_project.this` | Project number for billing budget filter |
| `google_project_service.enabled` | Enables Run, Artifact Registry, Storage, Logging, IAM, Billing Budgets APIs (`disable_on_destroy = false`) |
| `google_storage_bucket.artifacts` | Private versioned bucket for dataset snapshots, model folders, evaluation reports; lifecycle keeps 5 noncurrent versions |
| `google_artifact_registry_repository.api` | Docker repository `icu-api`, immutable tags |
| `google_service_account.api` | Cloud Run runtime identity; **no IAM roles** on this account |
| `google_service_account.deployer` | CI-style identity to push images and deploy Cloud Run |
| `google_project_iam_member.deployer_run_developer` | `roles/run.developer` for deployer SA |
| `google_artifact_registry_repository_iam_member.deployer_writer` | `roles/artifactregistry.writer` on `icu-api` repo |
| `google_service_account_iam_member.deployer_runtime_user` | `roles/iam.serviceAccountUser` so deployer can run the service as the runtime SA |
| `google_storage_bucket_iam_member.data_team` | `roles/storage.objectUser` on artifacts bucket per `data_team_members` |
| `google_cloud_run_v2_service.api` | Serves the API image, `MODEL_VERSION` env, probes on `GET /health`, max 1 instance |
| `google_cloud_run_v2_service_iam_member.public` | Optional `allUsers` invoker when `allow_public_invoker` is true (ADR 011) |
| `google_billing_budget.demo` | Optional monthly budget alert when `billing_account_id` is set |

Outputs: `service_url`, `artifacts_bucket`, `image_repository`, `runtime_service_account`, `deployer_service_account` ([infra/outputs.tf](../infra/outputs.tf)).

## Runtime service account with zero permissions

The model ships inside the container image (ADR 009). The container writes logs to stdout; Cloud Run and Cloud Logging collect them without granting the runtime SA logging API roles. Images are pulled by the Cloud Run service agent, not by the runtime SA. If the process inside the container is compromised, the attached identity cannot read the artifacts bucket or call other GCP APIs. Loading models from GCS at startup would require `roles/storage.objectViewer` on that bucket; that is a deliberate scale-up change, not this demo default.

## Access model

| Actor | Access | Why |
| --- | --- | --- |
| Infrastructure admin | Terraform, remote state bucket | Create and change cloud resources |
| Deployer service account | Push images, deploy Cloud Run | CI pipeline (not wired in this repo) |
| Runtime service account | None on GCP | Limit blast radius of a compromised container |
| Data team members (`data_team_members`) | Read/write objects in artifacts bucket | Audit trail for data and models |
| API callers | `roles/run.invoker` on the service | Call `/predict`; public only when demo flag is on |
| Clinicians | None on this stack | See predictions only through hospital integration |

## Secrets and configuration

No application secrets are required. Humans use `gcloud auth login`; CI would use workload identity federation. Future secrets would go in Secret Manager with `secretAccessor` on the runtime SA only. `infra/terraform.tfvars`, `infra/backend.hcl`, and `.env` are git-ignored.

## Data retention

- Artifacts bucket: versioning on; lifecycle drops older noncurrent versions beyond the five most recent.
- Logs: Cloud Logging `_Default` bucket, 30 days (platform default stated in `infra/README.md`).
- Request logs contain no patient vital values (see [operations.md](operations.md)).

## Cost and spending limits

Scale to zero, `max_instance_count = 1`, and optional budget notifications. A budget alerts billing admins; it does not stop usage. Details and links: [infra/README.md](../infra/README.md).

## Recovery

- Container crash: Cloud Run restarts; liveness probe on `/health`.
- Bad release: route 100 % traffic to the previous revision (`gcloud run services update-traffic`, documented in `infra/README.md`).
- Deleted artifact object: restore from a noncurrent GCS version.
- Region outage: redeploy in another region (for example `northamerica-northeast2`) with the same image tag; copy or dual-region the bucket in production.

## Operations cross-links

Monitoring queries and rollback steps: [operations.md](operations.md). After a Cloud Run deploy, optional `bash scripts/pull_cloud_logs.sh` then `uv run python -m icu.monitor --log logs/cloud_requests.jsonl` (see O1 runbook in `specs/10_FIXES_AND_OPTIONALS.md`). Commands, init/validate output, and untested steps: [infra/README.md](../infra/README.md).
