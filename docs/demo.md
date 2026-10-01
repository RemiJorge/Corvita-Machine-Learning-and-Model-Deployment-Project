# Review demo script (~12 minutes)

Run from the repository root. Download the dataset before the call (`make data`); during the demo, say files were verified via the manifest rather than downloading live.

Increase terminal font size. Paste commands from this file. Keep `examples/` open for curl bodies.

| Step | Command | What to say | What they should see |
|---|---|---|---|
| 1 | `cat data/manifest.json` | Source files are identified by checksum; PhysioNet did not publish SHA256SUMS for this version | Dataset 1.0.0, license, file digests, 4000 record files |
| 2 | `make reproduce` | Rebuilds tables, features, splits, models, and metrics, then compares to committed artifacts | Messages that splits are identical and metrics match within tolerance |
| 3 | `git diff --stat splits/ reports/` | Nothing changed, so groups and scores are reproduced | Empty diff |
| 4 | `uv run pytest tests/test_tables.py -k cutoff -v` | The 24:00 boundary is tested on both sides | Two passing tests |
| 5 | `uv run pytest tests/test_split.py -v` | No RecordID shared between train, val, and test | All green |
| 6 | `make docker-run` | Image bundles code and served model 1.0.1 (1.0.0 also present for rollback demo); non-root | Container listens on 8080; use a second terminal for curls |
| 7 | `curl -s -X POST localhost:8080/predict -H "Content-Type: application/json" -d @examples/valid.json \| python3 -m json.tool` | Probability, risk flag, model block with version and training data digest | `data_quality.status`: `ok`, `model.version`: `1.0.1` |
| 8 | `curl -s -X POST localhost:8080/predict -H "Content-Type: application/json" -d @examples/invalid.json` | Rejected at validation; nothing reaches the model | HTTP 422 |
| 9 | `curl -s -X POST localhost:8080/predict -H "Content-Type: application/json" -d @examples/missing_vitals.json \| python3 -m json.tool` | Partial inputs still get a score with a warning | `partial`, missing vitals listed |
| 10 | `curl -s -X POST localhost:8080/predict -H "Content-Type: application/json" -d @examples/no_vitals.json \| python3 -m json.tool` | Abstention when no valid vitals | `probability`: null, `insufficient` |
| 11 | `make simulate && make monitor` | Normal traffic passes the monitoring check | Monitor JSON with `status` ok; exit code 0 |
| 12 | `: > logs/requests.jsonl` then `uv run python scripts/send_requests.py --n 50 --drop RespRate && make monitor; echo $?` | Simulated RespRate outage on a clean log triggers alert | Alert in summary; exit code 1 |
| 13 | `uv run python scripts/send_requests.py --n 250` then `make monitor` | PSI baselines on recent traffic | `status` ok; exit code 0 |
| 14 | `uv run python scripts/send_requests.py --n 250 --shift Temp=+1.5` then `make monitor; echo $?` | Simulated temperature bias raises PSI on temp features | Alert on `temp_mean` / `temp_last`; exit code 1 |
| 15 | `make check` | Lint and fast tests | Exit code 0 |
| 16 | `make tf-validate` | Terraform validates; runtime SA has no GCP roles in config | Success messages |
| 17 | Open `docs/model_card.md` | Test metrics with intervals, threshold rationale, limits | One to two screens of results |

Live change drills and expected questions: `docs/process/specs/09_REVIEW_PREP.md` sections 2 and 3.
