# 07. Infrastructure specification

Implemented in F12 (`infra/`, `docs/infrastructure.md`, `make tf-validate`). No `terraform apply` without explicit human approval.

## 1. Target cloud and rationale

Google Cloud, region `northamerica-northeast1` (Montréal).

- Cloud Run scales to zero and its free tier covers a demo, so the setup can be deployed for real at no cost (optional item O1).
- Cloud Run gives an HTTPS URL without a load balancer or a domain.
- A Canadian region matches where Corvita's health data would be expected to live.
- The brief lists GCP Storage, Artifact Registry, Cloud Run and Logging as an accepted option.

Equivalents, for `docs/infrastructure.md`:

| Role | GCP (chosen) | AWS | Azure |
|---|---|---|---|
| Artifacts and data snapshots | Cloud Storage | S3 | Blob Storage |
| Container images | Artifact Registry | ECR | ACR |
| API runtime | Cloud Run | ECS Fargate | Container Apps |
| Logs | Cloud Logging | CloudWatch Logs | Azure Monitor |
| Identity | Service accounts + IAM | IAM roles | Managed identities |

Write an ADR for this choice.

## 2. Files in `/infra`

```
infra/
├── versions.tf               # terraform and provider constraints
├── providers.tf              # google provider with project and region
├── backend.tf                # empty gcs backend block (partial configuration)
├── backend.hcl.example       # bucket and prefix, copied to backend.hcl (git-ignored)
├── variables.tf
├── main.tf                   # all resources, grouped by comments
├── outputs.tf
├── terraform.tfvars.example  # copied to terraform.tfvars (git-ignored)
├── .terraform.lock.hcl       # committed
└── README.md                 # commands, outputs of init and validate, costs, untested steps
```

One `main.tf` is enough for this size. Resources are grouped with a comment header per group. No modules: with a single environment they would add indirection without benefit (say so in `docs/infrastructure.md`).

## 3. Versions

```hcl
terraform {
  required_version = ">= 1.6.0, < 2.0.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> <MAJOR>.0"   # set to the current major version on the Terraform Registry
    }
  }
}
```

Run `terraform init -backend=false`, read the installed provider version, set the constraint to that major version, commit `.terraform.lock.hcl`. Check every argument used below against the documentation of that provider version, since resource schemas change between major versions.

## 4. Backend

```hcl
terraform {
  backend "gcs" {}
}
```

`backend.hcl.example`:

```hcl
bucket = "<project-id>-tfstate"
prefix = "corvita-icu/demo"
```

Initialised with `terraform init -backend-config=backend.hcl` when a real project exists, and with `terraform init -backend=false` for validation. The state bucket is created once by hand (bootstrap problem: Terraform cannot store its state in a bucket it has not created yet), with object versioning on, uniform bucket-level access, public access prevention enforced, and access limited to infrastructure administrators. The GCS backend supports state locking. The README explains why the state is protected: it lists every resource and can contain sensitive attribute values.

## 5. Variables

| Variable | Type | Default | Purpose |
|---|---|---|---|
| `project_id` | string | none | GCP project |
| `region` | string | `northamerica-northeast1` | All regional resources |
| `env` | string | `demo` | Suffix in names and label |
| `image` | string | none | Full image URI with tag, for example `northamerica-northeast1-docker.pkg.dev/<project>/icu-api/icu-api:1.0.0` |
| `model_version` | string | `1.0.0` | Passed to the container as `MODEL_VERSION` |
| `allow_public_invoker` | bool | `false` | Grants `allUsers` the invoker role, for the demo only |
| `data_team_members` | list(string) | `[]` | IAM members (for example `user:name@example.com`) allowed to read and write artifacts |
| `billing_account_id` | string | `""` | When set, creates the budget alert |
| `budget_amount` | number | `5` | Monthly budget in the billing account's currency |
| `force_destroy_bucket` | bool | `false` | Allows `terraform destroy` to delete a non-empty bucket |

No value that identifies a real person, project or account is hardcoded. `terraform.tfvars` is git-ignored.

## 6. Resources (`main.tf`)

Common labels on every resource that supports them: `project = "corvita-icu"`, `env = var.env`, `managed_by = "terraform"`.

### APIs

`google_project_service.enabled` with `for_each` over `run.googleapis.com`, `artifactregistry.googleapis.com`, `storage.googleapis.com`, `logging.googleapis.com`, `iam.googleapis.com`, and `billingbudgets.googleapis.com`. `disable_on_destroy = false`, so destroying this stack never turns off an API used elsewhere in the project.

### Storage for artifacts and data snapshots

`google_storage_bucket.artifacts`:

- name `"${var.project_id}-icu-artifacts-${var.env}"`, location `var.region`;
- `uniform_bucket_level_access = true`, `public_access_prevention = "enforced"`;
- versioning enabled;
- lifecycle rule deleting noncurrent object versions beyond the 5 most recent;
- `force_destroy = var.force_destroy_bucket`.

Holds dataset snapshots with their manifests, model folders, and evaluation reports. It is the audit trail for "which data trained which model".

### Container registry

`google_artifact_registry_repository.api`: format `DOCKER`, `repository_id = "icu-api"`, location `var.region`, immutable tags enabled (a tag like `1.0.0` can never point to a different image). A cleanup policy keeping the 10 most recent versions is optional.

### Identities

- `google_service_account.api`: runtime identity of the Cloud Run service. It receives **no role at all**. The model is inside the image, logs written to stdout are collected by the platform, and the image is pulled by the Cloud Run service agent. An identity with no permission cannot be misused if the container is compromised. Write this in `docs/infrastructure.md`; it is a strong point.
- `google_service_account.deployer`: identity a CI job would use to publish images and deploy. Roles: `roles/artifactregistry.writer` on the repository, `roles/run.developer` on the project, and `roles/iam.serviceAccountUser` on the runtime service account only (needed to deploy a service that runs as it). Not used by the CI of this project; created to make the access model concrete.
- `google_storage_bucket_iam_member` with `for_each` over `var.data_team_members`, role `roles/storage.objectUser` on the artifacts bucket.

### API service

`google_cloud_run_v2_service.api`:

- name `"icu-api-${var.env}"`, location `var.region`, `ingress = "INGRESS_TRAFFIC_ALL"`, `deletion_protection = false` (check the argument exists in the pinned provider version);
- template: `service_account` = runtime account, scaling `min_instance_count = 0`, `max_instance_count = 1`, request timeout 10 seconds, concurrency 20;
- container: `image = var.image`, port 8080, env `MODEL_VERSION = var.model_version`, limits `cpu = "1"`, `memory = "512Mi"`, CPU only allocated during requests;
- startup and liveness probes on `GET /health`;
- `depends_on` the API services.

`max_instance_count = 1` caps both cost and blast radius for the demo. `min_instance_count = 0` means cold starts of a few seconds, acceptable for a demo and stated in the README.

### Invoker access

`google_cloud_run_v2_service_iam_member.public` with `count = var.allow_public_invoker ? 1 : 0`, role `roles/run.invoker`, member `allUsers`. Public access exists only so reviewers can call the demo URL. In real use the API would require authenticated callers (a service account of the hospital integration or an identity-aware proxy). Some organisations block `allUsers` by policy; the README mentions it. ADR required.

### Budget

`google_billing_budget.demo` with `count = var.billing_account_id == "" ? 0 : 1`, filtered on this project (`data "google_project" "this" {}` provides the number), amount `var.budget_amount`, threshold rules at 50 %, 90 % and 100 %. Notifications go to billing administrators by default. A budget alerts; it does not stop spending. The README says so, and adds that `max_instance_count = 1` and scale to zero are the actual spending limits.

### Logging

No resource needed. Cloud Run sends container stdout to Cloud Logging, where the request log lines from the API become structured entries. The `_Default` log bucket keeps logs 30 days, which is the retention stated in the README. Querying the monitoring fields from Cloud Logging is described in `docs/operations.md`; exporting them to a sink is future work.

## 7. Outputs

`service_url` (Cloud Run URI), `artifacts_bucket`, `image_repository` (the `<region>-docker.pkg.dev/<project>/icu-api` path), `runtime_service_account`, `deployer_service_account`.

## 8. Commands

Validation, no cloud account needed:

```bash
make tf-validate
# terraform -chdir=infra fmt -check -recursive
# terraform -chdir=infra init -backend=false
# terraform -chdir=infra validate
```

Real deployment (optional item O1), documented in `infra/README.md`:

```bash
cp infra/backend.hcl.example infra/backend.hcl        # set the state bucket
cp infra/terraform.tfvars.example infra/terraform.tfvars
terraform -chdir=infra init -backend-config=backend.hcl

# 1. Create the registry first (the image must exist before the service)
terraform -chdir=infra apply -target=google_project_service.enabled -target=google_artifact_registry_repository.api

# 2. Build and push the image for linux/amd64 (needed on Apple Silicon)
gcloud auth configure-docker northamerica-northeast1-docker.pkg.dev
docker build --platform linux/amd64 -t <image-uri>:1.0.0 .
docker push <image-uri>:1.0.0

# 3. Everything else
terraform -chdir=infra plan -out=tfplan
terraform -chdir=infra apply tfplan

# Rollback: send all traffic to the previous revision
gcloud run services update-traffic icu-api-demo --region northamerica-northeast1 --to-revisions <previous-revision>=100

# Teardown after the review
terraform -chdir=infra destroy
```

The two-step apply is a known limit of creating the registry and the service in one stack. Write it plainly rather than hiding it.

## 9. README content required by the brief

| Question from the brief | Answer to write |
|---|---|
| Who needs access and why | Table: infrastructure admin (Terraform, state bucket), deployer service account (push images, deploy), runtime service account (nothing), data team members (artifacts bucket), API callers (invoker role, public only for the demo), clinicians (only see predictions through the hospital integration, never raw data) |
| Passwords and secrets | None are needed by this system. No key files: humans use `gcloud` login, CI would use workload identity federation. If a secret appears later, it goes to Secret Manager with `secretAccessor` granted to the runtime account only. `.env`, `terraform.tfvars`, `backend.hcl` are git-ignored |
| Terraform state | Remote in a versioned GCS bucket with locking, restricted to infra admins, never committed |
| Data retention | Dataset snapshots and models kept for the life of the model plus audit needs; old object versions pruned by lifecycle rule; logs 30 days; logs contain no patient values |
| Cost control | Scale to zero, one instance maximum, budget alert, labels for cost reporting, no always-on resources, `terraform destroy` after use |
| Removing resources | `terraform destroy`; the bucket is protected against accidental deletion unless `force_destroy_bucket = true` |
| Recovery from failure | Instance crash: Cloud Run restarts it (probes). Bad release: route traffic to the previous revision. Deleted artifact: restore a previous object version. Region outage: apply the same Terraform with `region = "northamerica-northeast2"` (Toronto) and redeploy the same image tag; artifacts can be copied or the bucket made dual-region in production |

## 10. Cost estimate

Write it in `infra/README.md` with a date and links to the official pricing pages, and state the assumptions (a few hundred requests, under one second each, 1 vCPU, 512 MiB).

- Cloud Run: within the monthly free tier (vCPU-seconds, GiB-seconds and 2 million requests), so 0.
- Artifact Registry: a small free storage allowance, then a few cents per GB per month. A slim image of a few hundred MB costs at most cents.
- Cloud Storage: a few MB of artifacts, negligible.
- Cloud Logging: well within the free ingestion allowance.
- Expected total for the demo period: 0, at most a few cents.

## 11. What cannot be tested without a cloud account

List in `infra/README.md`: `terraform plan` and `apply`, IAM bindings taking effect, the budget resource (needs a billing account and permission), organisation policies blocking `allUsers`, cold start duration, Cloud Logging parsing of the JSON lines. `terraform validate` proves syntax and internal consistency only, as the brief itself notes.
