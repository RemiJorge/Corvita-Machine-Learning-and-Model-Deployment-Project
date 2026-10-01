# 09. Review preparation

This spec serves two readers. Agents use section 1 to write `docs/demo.md` in F13. The human owner uses all of it to rehearse.

## 1. Demo script (about 12 minutes)

Run from a fresh terminal in the repository root, with the dataset already downloaded (downloading live wastes time; say it was downloaded with `make data` and show the manifest).

| Step | Command | What to say | What they should see |
|---|---|---|---|
| 1 | `cat data/manifest.json` | Source files are identified by checksum, verified against PhysioNet's published sums | Versions, SHA-256, license |
| 2 | `make reproduce` | Rebuilds tables, features, splits, models and metrics from the raw files, then compares with the committed results | "splits identical, metrics identical" |
| 3 | `git diff --stat splits/ reports/` | Nothing changed, so the groups and scores are reproduced | Empty diff |
| 4 | `pytest tests/test_tables.py -k cutoff -v` | The 24:00 boundary is tested on both sides | Two green tests |
| 5 | `pytest tests/test_split.py -v` | No RecordID shared between groups | Green |
| 6 | `make docker-run` | The image contains the code and model 1.0.0, runs as non-root | Container healthy |
| 7 | `curl ... -d @examples/valid.json` | Probability, flag, and the model block: version, commit, data checksum | Status `ok` |
| 8 | `curl ... -d @examples/invalid.json` | Rejected at the boundary, nothing reaches the model | 422 with field errors |
| 9 | `curl ... -d @examples/missing_vitals.json` | Prediction with status `partial` and a warning | Missing vital listed |
| 10 | `curl ... -d @examples/no_vitals.json` | The model abstains instead of guessing | `probability: null`, `insufficient` |
| 11 | `make simulate && make monitor` | Normal traffic passes the monitoring check | Exit code 0 |
| 12 | `python scripts/send_requests.py --n 50 --drop RespRate && make monitor; echo $?` | A simulated sensor outage raises the alert | Alert listed, exit code 1 |
| 13 | `make check` | Lint and the full fast test suite | Green |
| 14 | `make tf-validate` | Terraform for GCP is valid; the runtime identity has no permission | Success |
| 15 | Open `docs/model_card.md` | Results with intervals and baselines, threshold rationale, limits | |

Keep `examples/` and the commands in a text file to paste from. Increase the terminal font size before the call.

## 2. Live change drills

The brief says the candidate will make one small change during the review. Rehearse each drill once with a timer. Each should take under five minutes including the test.

| Likely request | Where | Steps |
|---|---|---|
| Change the target sensitivity or threshold | `config/config.yaml` `threshold.target_sensitivity` | Edit, `make train evaluate package` with a new model version, restart with `MODEL_VERSION` |
| Add a feature (min, max or standard deviation of a vital) | `icu/features.py`, `FEATURE_COLUMNS` | Add the aggregation, update the column list and the fixture expectations, run tests, retrain as a new major model version (schema change) |
| Add an input validation rule (for example age at least 18) | `config/config.yaml` bounds, `icu/api/schemas.py` | Edit, add a 422 test, run tests |
| Add a field to the API response | `icu/api/schemas.py`, `icu/api/service.py` | Add the field, update the example response and a test |
| Change the monitoring threshold or add a latency alert | `config/config.yaml`, `icu/monitor.py` | Edit, add a synthetic log test |
| Change the cutoff to 12 hours | `config/config.yaml` `cutoff_minutes` | Edit, update the boundary tests to 720 and 721, `make reproduce` |
| Exclude a vital from the model | `config/config.yaml` `vitals`, `FEATURE_COLUMNS` | Edit, tests, retrain |

Because every tunable value lives in the config and the feature code is one module, most drills are a config edit plus a test. Say this out loud when doing it: it is the design paying off.

## 3. Questions to expect and where the answer lives

Answer in one sentence first, then detail.

| Question | Short answer | Source |
|---|---|---|
| Why is 24:00 included? | The brief says so; the boundary is tested on both sides | data spec section 7 |
| How do you know there is no leakage? | Forbidden-column test, pipelines fitted on train only, test scored once, choices from validation | modeling spec |
| Why no class weights? | They distort probabilities; the threshold handles imbalance; Brier stays honest | ADR 4 |
| Why this threshold? | Sensitivity target set on validation; alert load reported; the target is a clinical decision exposed in config | ADR 5 |
| Why did you serve the logistic regression (or HGB)? | Rule applied on validation numbers, cited in the ADR | ADR 7 |
| Why are the intervals so wide? | About 600 test records and 80 deaths | model card |
| What does the 48 h inclusion rule do to your results? | Early deaths are missing, so the population is easier and calibration may not transfer | data spec section 8 |
| Why does the API abstain with no vitals? | Outside the training distribution; a number would look trustworthy while resting on nothing | ADR 8 |
| How would you retrain and release? | Manual retrain, shadow, guardrails, canary, promote; rollback by revision | operations doc |
| Why does the runtime service account have no role? | It does not need any; least privilege | infra spec section 6 |
| What would change for NOA and newborns? | Grouping by infant, gestational-age-dependent norms, higher sampling rate, edge inference, bedside alarms independent of the cloud, regulatory lifecycle | first exercise and job context |
| Which parts did AI write? | Answer from `AI_USAGE.md`, then explain one piece of that code without looking | AI_USAGE.md |
| What would you do with more time? | Labs, external validation, recalibration on held-out data, PSI drift, real deployment with authenticated callers | README |

## 4. How to talk about limitations

State them before being asked, once, calmly, with the consequence and the next step. For example: "The test set has about 80 deaths, so the AUROC interval is wide and I would not claim one model beats the other; the paired bootstrap interval contains zero. The next step would be external validation on another dataset." A reviewer at a medical device company trusts a candidate who knows where the numbers stop being reliable.

## 5. Checklist the day before

- [ ] Fresh clone passes every README command.
- [ ] CI green on `main`, tag `v1.0.0` pushed.
- [ ] Docker image built and tested on the demo machine.
- [ ] Demo commands in a text file, font size increased, notifications off.
- [ ] Drills rehearsed once each with a timer.
- [ ] Model card numbers read aloud once in English.
- [ ] `TIME_LOG.md` total and unfinished items final.
- [ ] If deployed (O1): URL tested from another network, and a reminder set to run `terraform destroy` after the review.
