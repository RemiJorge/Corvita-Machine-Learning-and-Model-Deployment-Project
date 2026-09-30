
| Part           | Tool          | What the AI did                                                         | What the author did                                                       |
| -------------- | ------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| Specifications | Claude (chat) | Drafted roadmap and specs                                               | Defined requirements, edited every spec file                              |
| F0–F3 data     | Cursor agent  | Ingest, parse, quality, tables, tests, `docs/data.md`                   | Reviewed code line by line, ran `make data`, spot-checked raw vs parquet  |
| F4–F8 modeling | Cursor agent  | Features, split, train, evaluate, package, tests                        | Checked leakage rules, ran `make reproduce`, read `reports/metrics.json`  |
| F9–F10 API     | Cursor agent  | FastAPI, Docker, logging middleware, monitor, `docs/api.md`             | Ran curl examples, `make docker-run`, privacy greps on logs               |
| F11 CI         | Cursor agent  | `.github/workflows/ci.yml`                                              | Pushed branch, verified Actions jobs (confirm badge)                      |
| F12 infra      | Cursor agent  | `infra/`, ADRs 010–011, `docs/infrastructure.md`                        | `make tf-validate`, traced resources in `main.tf`                         |
| F13 docs       | Cursor agent  | README, `docs/demo.md`, model card final pass, TIME_LOG/AI_USAGE drafts | Read README in 10 min, ran commands, confirmed numbers against `reports/` |


Confirm tool names, rows, and accuracy before submission. The author reviewed, ran, and understood each delivered part.