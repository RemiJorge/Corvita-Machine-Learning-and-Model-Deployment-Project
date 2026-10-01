# 00. Project brief

Internal summary for agents and maintainers. The employer’s full take-home wording is not stored in this repository.

## Purpose

Adult ICU mortality risk from the first 24 hours of vitals and admission fields (PhysioNet Challenge 2012, set A). Deliver reproducible ML, a Dockerized FastAPI service, tests and monitoring, and GCP Terraform. Demonstration only—not clinical use, not for neonates.

## Data

PhysioNet Challenge 2012 set A ([dataset page](https://physionet.org/content/challenge-2012/1.0.0/)), target `In-hospital_death`, 48 h minimum stay (selection bias documented in `specs/03_DATA_SPEC.md`). Outcome columns are never model inputs.

## Where requirements live

| Topic | Spec |
| --- | --- |
| Architecture and dependencies | `specs/01_ARCHITECTURE_AND_CONVENTIONS.md` |
| Feature order and gates | `specs/02_ROADMAP.md` |
| Data, modeling, API, CI, infra, docs | `specs/03_DATA_SPEC.md` through `specs/08_DOCUMENTATION_SPEC.md` |
| Live review commands | `docs/demo.md` |
| Post-release fixes and optionals | `specs/10_FIXES_AND_OPTIONALS.md` |

## Non-negotiable themes

No leakage (24 h cutoff, train-only fitting, single test evaluation). Determinism via `config/config.yaml`. English everywhere. No secrets, raw data, or Terraform state in Git. Tests and docs ship with each feature.

## Evaluation lens (for design choices)

Reviewers care about reproducibility, traceability, safety handling of bad or missing inputs, honest metrics (baselines, intervals), operability (logs, monitor, rollback story), and clear communication (`README`, model card, ADRs). See `specs/02_ROADMAP.md` for delivery history.

## Out of scope

Labs, deep learning, automated retraining, production auth beyond the infra demo, experiment trackers, paid services.
