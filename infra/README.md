# Terraform (GCP)

Infrastructure for the ICU mortality API on Google Cloud. Validation does not need a GCP account. Deployment is optional (project roadmap item O1).

## Validation (no cloud account)

From the repository root:

```bash
make tf-validate
```

Equivalent:

```bash
terraform -chdir=infra fmt -check -recursive
terraform -chdir=infra init -backend=false
terraform -chdir=infra validate
```

### Output of `terraform init -backend=false` (2026-09-30)

Recorded on a machine with Terraform 1.9.8 after the lock file was committed:

```text
Initializing provider plugins...
- Reusing previous version of hashicorp/google from the dependency lock file
- Using previously-installed hashicorp/google v6.50.0

Terraform has been successfully initialized!

You may now begin working with Terraform. Try running "terraform plan" to see
any changes that are required for your infrastructure. All Terraform commands
should now work.

If you ever set or change modules or backend configuration for Terraform,
rerun this command to reinitialize your working directory. If you forget, other
commands will detect it and remind you to do so if necessary.
```

First init on a clean clone also downloads the provider and writes `infra/.terraform.lock.hcl`.

### Output of `terraform validate` (2026-09-30)

```text
Success! The configuration is valid.
```

`terraform validate` checks syntax and internal consistency only. It does not prove IAM or Cloud Run behaviour in a real project.

## Remote state bootstrap

Terraform cannot create the state bucket it depends on. Once per GCP project, an infrastructure admin creates a GCS bucket (versioning on, uniform access, public access prevention enforced, access limited to admins). Copy `backend.hcl.example` to `backend.hcl` (git-ignored), set `bucket` and `prefix`, then:

```bash
terraform -chdir=infra init -backend-config=backend.hcl
```

The state file lists every resource address and may contain sensitive values. It must never be committed. Locking uses the GCS backend native lock.

## Variables

Copy `terraform.tfvars.example` to `terraform.tfvars` (git-ignored). Required: `project_id`, `image`. No real project IDs belong in Git.

`image` ends with the Docker tag you pushed (for example `icu-api:1.3.0`). `model_version` is the `MODEL_VERSION` env var and must match a `models/<version>/` folder inside the image (the Dockerfile currently copies only `1.0.0`). A mismatch makes the container exit before `/health` passes the startup probe.

## Deployment log

Fill this section after a real deploy (O1). Redact project IDs and account details in the plan summary.

| Field | Value |
| --- | --- |
| Date | YYYY-MM-DD |
| Image tag | e.g. `icu-api:1.3.0` |
| `terraform plan` summary (redacted) | e.g. N to add, 0 to change, 0 to destroy |
| Service URL | `https://...` (from `terraform output -raw service_url`) |
| Rollback performed | yes/no; revision names if yes |
| Destroy date | TBD until `terraform destroy` |

## Deployment (optional)

Two-step apply: the image must exist in Artifact Registry before Cloud Run can start.

```bash
cp infra/backend.hcl.example infra/backend.hcl        # set the state bucket
cp infra/terraform.tfvars.example infra/terraform.tfvars
terraform -chdir=infra init -backend-config=backend.hcl

# 1. APIs and registry only
terraform -chdir=infra apply \
  -target=google_project_service.enabled \
  -target=google_artifact_registry_repository.api

# 2. Build and push linux/amd64 image (Apple Silicon hosts need --platform)
gcloud auth configure-docker northamerica-northeast1-docker.pkg.dev
docker build --platform linux/amd64 -t <image-uri>:1.0.0 .
docker push <image-uri>:1.0.0

# 3. Full stack
terraform -chdir=infra plan -out=tfplan
terraform -chdir=infra apply tfplan
```

Public demo URL (only if org policy allows `allUsers`): set `allow_public_invoker = true` in `terraform.tfvars`. See ADR 011.

Rollback after a bad release:

```bash
gcloud run services update-traffic icu-api-demo \
  --region northamerica-northeast1 \
  --to-revisions <previous-revision>=100
```

Teardown:

```bash
terraform -chdir=infra destroy
```

The artifacts bucket refuses destroy while non-empty unless `force_destroy_bucket = true`.

Cold starts: `min_instance_count = 0` means a few seconds delay on the first request after idle time.

## Brief answers

### Who needs access and why

| Role | Access |
| --- | --- |
| Infrastructure admin | Terraform, remote state bucket |
| Deployer service account | Push images, deploy Cloud Run |
| Runtime service account | No GCP roles (identity only) |
| Data team members | Read/write artifacts bucket objects |
| API callers | `roles/run.invoker` (public `allUsers` only for demo) |
| Clinicians | Predictions via hospital integration, not raw cloud data |

### Passwords and secrets

None required. Humans use `gcloud` login; CI would use workload identity federation. Future secrets: Secret Manager with `secretAccessor` on the runtime SA. `.env`, `terraform.tfvars`, and `backend.hcl` stay out of Git.

### Terraform state

Remote, versioned GCS, locking enabled, restricted to infra admins, never committed.

### Data retention

Dataset snapshots and models kept for model lifetime and audit; old object versions pruned by lifecycle rule (keep 5 noncurrent). Logs 30 days in Cloud Logging `_Default`. Request logs contain no patient values.

### Cost control

Scale to zero, `max_instance_count = 1`, optional budget alert, labels on resources, no always-on VMs. Budget notifies; it does not cap spend. Destroy when finished.

### Removing resources

`terraform destroy`. Non-empty artifacts bucket blocked unless `force_destroy_bucket = true`.

### Recovery from failure

Instance crash: Cloud Run restarts (health probes). Bad release: traffic to previous revision. Deleted artifact: restore GCS object version. Region outage: redeploy in another region with the same image tag; copy artifacts or use dual-region bucket in production.

## Cost estimate (2026-09-30)

Assumptions: a few hundred requests, under one second each, 1 vCPU, 512 MiB RAM, one small image, a few MB in GCS.

| Service | Expected demo cost | Pricing reference |
| --- | --- | --- |
| Cloud Run | $0 (within free tier for this traffic) | [Cloud Run pricing](https://cloud.google.com/run/pricing) |
| Artifact Registry | $0 to a few cents | [Artifact Registry pricing](https://cloud.google.com/artifact-registry/pricing) |
| Cloud Storage | Negligible | [Cloud Storage pricing](https://cloud.google.com/storage/pricing) |
| Cloud Logging | Within free ingestion | [Cloud Logging pricing](https://cloud.google.com/stackdriver/pricing) |

Expected total for the review period: **$0**, at most a few cents.

## What cannot be tested without a cloud account

- `terraform plan` and `terraform apply`
- IAM bindings taking effect
- Billing budget resource (needs `billing_account_id` and permission)
- Organisation policies blocking `allUsers`
- Cold start duration
- Cloud Logging parsing of API JSON log lines (after deploy: `bash scripts/pull_cloud_logs.sh`, requires `jq`)
