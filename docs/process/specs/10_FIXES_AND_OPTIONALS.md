# 10. Consistency fixes and optional items

Written after an external review of the repository at version 1.0.0. Same workflow as before: one item at a time, handoff report, human verification gate. Do F15 completely before any optional item.

Time used so far: 7.5 h of 24 h (TIME_LOG.md). Planned below: about 9 h.

| ID | Item | Version | Human time | Status |
|---|---|---|---|---|
| F15 | Consistency fixes | 1.0.1 | 2 h | done |
| O0 | RespRate missingness vs MechVent | 1.1.0 | 0.5 h | todo |
| O3 | Subgroups by ICUType | 1.2.0 | 1 h | done |
| O1 | Real deployment on Cloud Run | 1.3.0 | 3 h | todo |
| O2 | PSI drift check | 1.4.0 | 2 h | todo |
| F16 | Final rehearsal and tag | 1.4.0 | 0.5 h | todo |

---

## F15. Consistency fixes (1.0.1)

Each point below was observed in the repository. Fix all of them, one commit per point.

### 1. API returns 500 for a non-numeric `record_id` (bug)

`service._record_id_int` calls `int(request.record_id)`. The schema accepts any string of 1 to 64 characters, so `"record_id": "patient-A12"` crashes with a 500.

- `record_id` is for tracing only and never a feature. Use a constant internal ID (for example `0`) in the DataFrame built by `measurements_to_frame`; keep the original string only for the response echo. Delete `_record_id_int`.
- Test: `test_predict_non_numeric_record_id` expects 200 and the same probability as the same body with `record_id` `"1"`.

### 2. Abstention rationale contradicts the data

The warning says inputs without vitals are "outside what it was trained on", and ADR 008 says this distribution "is not represented in training". The data says otherwise: 71 of 4000 records have no vital in the first 24 hours, and `training_reference.insufficient_rate` is 0.0182 (about 51 training records).

- New warning: "No valid vital sign in the first 24 hours. The model abstains because the score would rest on age, sex and ICU type only."
- Rewrite ADR 008 context with the real counts: such records exist but are rare (about 1.8 %), and for them the model's output depends on admission fields alone, which is not the risk estimate the service is meant to provide. Decision unchanged.
- Update `docs/api.md` and the test that asserts the warning text.

### 3. Stale identifiers in the docs, and a dirty package

- README and model card show manifest digest `62e4ef45…`; `models/1.0.0/metadata.json` and the current `sha256sum data/manifest.json` both give `3d13119b…`.
- Model card shows git commit `7d004194…`; metadata shows `41698a5d…`.
- Metadata has `"git_dirty": true`: the model was packaged from an uncommitted tree.

Fix: after points 1 to 4 are committed, run `make package` on a clean tree, commit `models/`, then copy digest and commit into README and model card from `metadata.json`. Add a test that reads the model card and README and checks that the digest they quote equals `metadata.json` (plain string search), so this cannot drift again.

### 4. Python version mismatch

Metadata `library_versions.python` is 3.14.4, while CI and the Docker image use 3.12. The model loads today, but the README claims a pinned environment.

- Add `.python-version` containing `3.12`.
- Set `requires-python = ">=3.12,<3.13"` in `pyproject.toml`, run `uv lock`, commit.
- Re-run `make reproduce` under 3.12. Report the maximum metric difference. Repackage (point 3).

### 5. Served-model justification in the README is inaccurate

README says logistic regression is served "for calibration". Validation Brier favoured HGB (0.1051 versus 0.1071), and so did the test Brier. Replace with: served because of the primary rule (validation PR-AUC 0.381 versus 0.371); secondary advantages are size, speed and readable coefficients; on the test set HGB scores higher on every metric, but the paired bootstrap interval for the PR-AUC difference contains zero. Same fix in the model card calibration paragraph if needed.

### 6. Brier baseline wording

"Brier at constant training death rate (0.139)" reads as if 0.139 were the Brier score, while the table shows 0.119. Write: "Brier of a constant prediction equal to the training death rate (0.139): 0.119." README and model card.

### 7. Draft markers and contradictions

- Remove every "(confirm)", "(draft ...)" and "Confirm tool names..." line once the human owner has checked the content.
- README says "Unfinished: F14 fresh-clone rehearsal and tag v1.0.0" while TIME_LOG says F14 is done. Make them agree.
- Move the `[Unreleased]` changelog entries into `[1.0.1]` with this feature.

### 8. Typography

Replace em dashes and en dashes in `README.md` (18), `AI_USAGE.md` (4), `TIME_LOG.md` (3) and `src/icu/evaluate.py` (3). Use a colon, a comma, "to" for ranges ("1 to 4", "F2 to F3"). Replace the `…` in the README input table with explicit names. Fix the warning "1 measurement values were" (singular and plural).

### 9. Docker log permissions

Replace the README workaround (`chmod 666`) by running the container as the host user in `make docker-run`: add `--user "$$(id -u):$$(id -g)"` to `docker run`. Check that the API starts and writes `logs/requests.jsonl`. Remove the workaround sentence from the README.

### 10. Report placeholder that points to the specs

`reports/data_quality.json` contains `"resp_rate_missing_vs_mechvent": {"note": "optional analysis, see section 9"}`. A report must not reference internal specs. O0 fills it; if O0 is skipped, remove the key.

### 11. Specs referenced but not committed

`.gitignore` excludes `specs/`, `AGENTS.md` and `CLAUDE.md`, but README, CHANGELOG, AI_USAGE and `docs/demo.md` mention the specs. Human owner decides:

- recommended: commit `specs/`, `AGENTS.md` and `CLAUDE.md`, which shows how the agents were directed and supports `AI_USAGE.md`;
- otherwise: remove every mention of `specs/` from committed files.

### 12. ADR gaps

Numbering starts at 002. Write `001-reject-unknown-parameters.md` (the API rejects `"Hr"` instead of silently treating heart rate as missing). The no-refit decision is covered inside ADR 007; that is enough.

### 13. License and attribution

- Add `LICENSE` (MIT) for the code.
- The dataset license recorded in the manifest is Open Data Commons Attribution v1.0, which requires attribution. Add a "Data and citation" section to the README with the citation text shown on the PhysioNet dataset page (copy it from the page, do not write it from memory).

### 14. Model card additions (numbers already in `reports/`)

- Missingness carries risk: in the test set, records missing at least one vital have a death rate of 70/421 (16.6 %) against 13/179 (7.3 %) for complete records. Mostly RespRate, missing for 73 % of training records.
- Alert load: at the validation threshold the served model flags about 47 patients per 100 on the test set. State that this is heavy for clinical use and that `threshold.target_sensitivity` is the lever to discuss with clinicians.

### Human verification

1. `make check`: green, including the new tests.
2. `curl` with `"record_id": "abc"`: 200.
3. `grep -rn $'\u2014\|\u2013' --include=*.md --include=*.py . --exclude-dir=.venv`: no result (Unicode em and en dash).
4. `grep -rn "confirm\|draft" README.md TIME_LOG.md AI_USAGE.md`: no result.
5. `sha256sum data/manifest.json`, compare with README, model card and `metadata.json`.
6. `jq .git_dirty models/1.0.0/metadata.json`: `false`. `jq .library_versions.python`: `3.12.x`.
7. `make docker-run` without any `chmod`: log file written.

---

## O0. RespRate missingness versus MechVent (1.1.0)

Implements `specs/03_DATA_SPEC.md` section 9.

- In `quality.py`, for each record, whether any `MechVent = 1` appears in the first 1440 minutes and whether RespRate is missing in the same window. Cross-tabulation (2 x 2 counts) plus the death rate in each cell.
- Replace the placeholder key in `reports/data_quality.json` with the real table.
- One paragraph in `docs/data.md` and one line in the model card: whether the data supports "RespRate is mostly absent for ventilated patients", with the counts.
- `MechVent` never becomes a feature (test: it is not in `FEATURE_COLUMNS`).

Human verification: open the report, check that the four cells sum to 4000, read the paragraph.

---

## O3. Subgroups by ICUType (1.2.0)

- Reuse `metrics_for_subgroup` and the bootstrap functions from `evaluate.py`; add ICUType 1 to 4 as subgroups, both models, test set only.
- For each group: `n`, deaths, observed death rate, mean predicted probability, and the metrics with 95 % intervals, or `"too few events"` under 10 deaths or 10 survivors.
- `reports/subgroups.json`, a table in the model card, two sentences of interpretation. The key comparison is observed death rate against mean predicted probability per group.
- One sentence linking to NOA: the same check would run per hospital, firmware version and gestational age band.

Human verification: `make evaluate`, open the table, check that the group sizes sum to 600.

---

## O1. Real deployment on Cloud Run (1.3.0)

The human owner runs every command that touches the cloud. Agents only change files.

### File changes

1. `infra/providers.tf`: add `user_project_override = true` and `billing_project = var.project_id` so the billing budget API accepts user credentials.
2. Request logs: add `"severity": "INFO"` (or `"ERROR"` for 5xx) to each JSON line so Cloud Logging classifies entries. Update the logging test.
3. `scripts/pull_cloud_logs.sh`: `gcloud logging read` filtered on `resource.type="cloud_run_revision"` and `jsonPayload.path="/predict"`, piped to `jq -c '.[].jsonPayload'` into `logs/cloud_requests.jsonl`. `jq` is documented as a prerequisite for this optional step only.
4. `infra/README.md`: a "Deployment log" section with the date, the redacted `terraform plan` summary, the service URL, the rollback performed, and the `destroy` date once done.

### Runbook (human)

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project <project-id>

gcloud storage buckets create gs://<project-id>-tfstate --location=northamerica-northeast1 \
  --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update gs://<project-id>-tfstate --versioning

cp infra/backend.hcl.example infra/backend.hcl
cp infra/terraform.tfvars.example infra/terraform.tfvars   # project_id, image, allow_public_invoker = true, billing_account_id
terraform -chdir=infra init -backend-config=backend.hcl
terraform -chdir=infra apply -target=google_project_service.enabled -target=google_artifact_registry_repository.api

gcloud auth configure-docker northamerica-northeast1-docker.pkg.dev
IMAGE=northamerica-northeast1-docker.pkg.dev/<project-id>/icu-api/icu-api:1.3.0
docker build --platform linux/amd64 -t $IMAGE . && docker push $IMAGE

terraform -chdir=infra plan -out=tfplan
terraform -chdir=infra apply tfplan
URL=$(terraform -chdir=infra output -raw service_url)

curl -s $URL/health
uv run python scripts/send_requests.py --base-url $URL --n 100
bash scripts/pull_cloud_logs.sh && uv run python -m icu.monitor --log logs/cloud_requests.jsonl
```

Rollback demo: push `1.3.1` (same code, new tag, since tags are immutable), `terraform apply -var image=...:1.3.1`, then route traffic back:

```bash
gcloud run revisions list --service icu-api-demo --region northamerica-northeast1
gcloud run services update-traffic icu-api-demo --region northamerica-northeast1 --to-revisions <previous>=100
```

After the review: `terraform -chdir=infra destroy`, then delete the state bucket or the whole project.

### Human verification

URL answers `/health` from a phone on mobile data; the monitoring check runs on cloud logs; rollback shown; budget visible in the console; calendar reminder set for `destroy`.

---

## O2. PSI drift check (1.4.0)

- Training: for each continuous feature (`age`, `*_mean`, `*_last`, `*_count`), store decile edges and training proportions in `training_reference.psi_bins`, with missing values as an extra bin. Metadata-only change of the model: version `1.0.1` of the model folder (`models/1.0.1/`), same pipeline file.
- API: log the bin index of each feature per request, never the value. Document why this keeps logs free of patient values.
- `monitor.py`: PSI per feature over the window, `epsilon = 1e-4` for empty bins, alert above `monitoring.psi_alert` (default 0.25), no PSI below `monitoring.psi_min_requests` (default 200). State in `docs/operations.md` that 0.1 and 0.25 are conventions from practice, not statistical tests.
- `send_requests.py --shift Temp=+1.5` to simulate a miscalibrated sensor.
- Tests: identical distribution gives PSI close to 0; shifted distribution triggers the alert; small window returns `not_enough_data`.

Human verification: normal traffic then `make monitor` (ok); shifted traffic then `make monitor` (alert on `temp_mean` and `temp_last`); grep the log to confirm no raw values.

---

## F16. Final rehearsal and tag

Fresh clone, README from top to bottom, demo script once aloud, `TIME_LOG.md` total final, tag the last version.
