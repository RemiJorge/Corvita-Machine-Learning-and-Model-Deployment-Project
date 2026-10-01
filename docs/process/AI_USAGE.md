
| Part           | Tool          | What the AI did                                                         | What the author did                                                       |
| -------------- | ------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| Specifications | Claude (chat) | Drafted roadmap and specs                                               | Defined requirements, edited every spec file                              |
| F0 to F3 data     | Cursor agent  | Ingest, parse, quality, tables, tests, `docs/data.md`                   | Reviewed code line by line, ran `make data`, spot-checked raw vs parquet  |
| F4 to F8 modeling | Cursor agent  | Features, split, train, evaluate, package, tests                        | Checked leakage rules, ran `make reproduce`, read `reports/metrics.json`  |
| F9 to F10 API     | Cursor agent  | FastAPI, Docker, logging middleware, monitor, `docs/api.md`             | Ran curl examples, `make docker-run`, privacy greps on logs               |
| F11 CI         | Cursor agent  | `.github/workflows/ci.yml`                                              | Pushed branch, verified Actions jobs                                      |
| F12 infra      | Cursor agent  | `infra/`, ADRs 010 to 011, `docs/infrastructure.md`                        | `make tf-validate`, traced resources in `main.tf`                         |
| F13 docs       | Cursor agent  | README, `docs/demo.md`, model card final pass, TIME_LOG and AI_USAGE entries | Read README in 10 min, ran commands, checked numbers against `reports/` |
| F15 fixes      | Claude (chat) + Cursor agent | External Claude review found `record_id` 500, doc/metadata drift, abstention wording; Cursor agent implemented F15 fixes per `docs/process/specs/10_FIXES_AND_OPTIONALS.md` | Re-ran verification greps, `make check`, checked digest and commit in docs |
| O0 optional    | Cursor agent  | MechVent vs RespRate crosstab in quality report and model card note       | Checked four cells sum to 4000, read interpretation                       |
| O3 optional    | Cursor agent  | ICUType subgroup evaluation and `reports/subgroups.json`                  | Verified group sizes sum to 600 on test set                               |
| O1 optional    | Cursor agent  | Terraform billing provider tweak, log `severity`, `pull_cloud_logs.sh`, deployment runbook in `infra/README.md` | Ran `terraform apply`, pushed image, smoke-tested URL; logged in `infra/README.md` |
| O2 optional    | Cursor agent  | PSI reference bins in metadata, monitor PSI, `--shift` on send_requests   | Normal vs shifted traffic with `make monitor`, grep logs for no raw values |

The author reviewed, ran, and understood each delivered part.
