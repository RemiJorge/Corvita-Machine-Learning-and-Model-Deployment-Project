
| Date       | Start | End   | Hours | Feature   | Notes                                             |
| ---------- | ----- | ----- | ----- | --------- | ------------------------------------------------- |
| 2026-09-29 | 16h30 | 18h   | 1h30  | F0        | Bootstrap, specs, lockfile                        |
| 2026-09-29 | 18h30 | 18h45 | 15min | F1        | Ingest, manifest                                  |
| 2026-09-29 | 19h15 | 20h   | 45min | F2 to F3  | Parse, quality, tables                            |
| 2026-09-29 | 21h   | 22h30 | 1h30  | F4 to F8  | Features through reproduce                        |
| 2026-09-30 | 16h   | 17h   | 1h    | F9 to F10 | API, Docker, monitor                              |
| 2026-09-30 | 17h30 | 18h   | 30min | F11       | CI workflow                                       |
| 2026-09-30 | 18h   | 18h30 | 30min | F12       | Terraform, infra docs                             |
| 2026-09-30 | 19h   | 19h30 | 30min | F13       | README, demo, model card                            |
| 2026-09-30 | 21h   | 22h   | 1h    | F14       | Fresh-clone rehearsal, reproduce fixes, demo prep |
| 2026-09-30 | 22h30 | 00h30 | 2h    | F15       | External review fixes, repackage, docs alignment  |
| 2026-10-01 | 10h   | 10h30 | 30min | O0        | RespRate vs MechVent crosstab                     |
| 2026-10-01 | 10h30 | 11h   | 30min | O3        | ICUType subgroup metrics                          |
| 2026-10-01 | 11h30 | 12h   | 30min | O1        | Cloud Run IaC and scripts                         |
| 2026-10-01 | 12h30 | 14h   | 1h30  | O1        | GCP apply, image push, URL smoke tests            |
| 2026-10-01 | 14h   | 14h30 | 30min | O2        | PSI bins, monitor, send_requests --shift          |
| 2026-10-01 | 16h   | 16h30 | 30min | F16       | Final rehearsal, submission polish                |
| 2026-10-01 | 17h   | 18h30 | 1h30  | 1.4.2     | Analysis notebook, git-optional package, doc pass |


Total: **14 h** of 24 h. Required scope F0 to F14 closed at tag `v1.0.0`. Post-review consistency (F15), optionals O0 to O2, live Cloud Run deploy (O1), and release polish through package **1.4.2** (`CHANGELOG` 1.0.1 to 1.4.2; no separate 1.4.1 release).
