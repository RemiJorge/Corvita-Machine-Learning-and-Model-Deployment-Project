# 00. Project brief

## 1. The assignment in one paragraph

Use the first 24 hours of ICU data to predict whether an adult patient will die during the hospital stay (`In-hospital_death`), combining vital signs measured over time with information recorded at admission. Compare a logistic regression with one tree-based model, serve the chosen model with FastAPI in Docker, test and monitor it, and describe the cloud setup with Terraform files for a real cloud. Everything must run on a laptop. The exercise uses adult data to assess skills useful for NOA. The model is not meant for medical use, and not for newborns.

## 2. Dataset

- PhysioNet Challenge 2012, version 1.0.0: https://physionet.org/content/challenge-2012/1.0.0/
- Use set A and its outcomes file `Outcomes-a.txt`, joined on `RecordID`.
- Target: `In-hospital_death` (1 = died in hospital).
- `-1` means missing.
- Records are adults who stayed in ICU at least 48 hours. The project must explain how this limits the results (see `specs/03_DATA_SPEC.md`, section "Selection bias").
- Fields from the outcomes file are never model inputs.

## 3. Required tasks (from the official brief)

| Task | Requirement |
|---|---|
| Prepare data | Save source file versions and checksums. Check fields, units, values and times. Build vital-sign and admission tables linked by `RecordID`. Track missing values. Keep measurements from 00:00 to 24:00 after admission, 24:00 included. Exclude later data. |
| Build model inputs | Use `HR`, `RespRate`, `Temp`, `Age`, `Gender`, `ICUType`. For each vital: count, mean, last value. Add missing-data flags. Encode categorical fields and assemble inputs. Lab data and complex methods are optional. |
| Train and compare | Logistic regression versus one tree-based model. Split RecordIDs 70 / 15 / 15 (train / validation / test) with similar death rates and a fixed seed. Fit data preparation on train only. Choose settings and the risk cutoff on validation only. Report test PR-AUC, AUROC, sensitivity, specificity and Brier score. Check results when vitals are missing. |
| Run predictions | Save data and code versions, split IDs, seed, settings, scores and model files. FastAPI `POST /predict` in Docker using the saved preparation steps. Return predicted probability, model version and a data-quality flag. Validate input fields and explain what happens with wrong or missing values. |
| Plan cloud setup | Show where files and images are stored, where the API runs, who has access, where logs go. Terraform in `/infra` with pinned provider versions, output of `terraform init -backend=false` and `terraform validate`. |
| Test and monitor | Test that later data is excluded, that RecordIDs never overlap across groups, and that valid and invalid API calls behave correctly. One CI workflow. Log requests, errors and response times. A check for too much missing vital data. Explain how to detect changing data, retrain, release a model and roll back. Do not automate retraining. |

## 4. What must be shown during the review

1. Rebuild model inputs from the same source files with the README commands.
2. Recreate the same data groups and similar model scores, stating any expected difference.
3. Start the Docker container.
4. Send a valid `POST /predict`, an invalid request, and one with missing vital signs.
5. Show which data and which model version produced one prediction.
6. Run the tests and the monitoring check.
7. Make one small change live.

## 5. Files to submit

README, exact library versions, data loading and preparation code, saved RecordIDs for each group, results for both models, saved model and preparation steps, API examples, tests, one CI workflow, `/infra`, and a short model summary (purpose, results, limits). The README also covers system design, input fields, run commands, AI use, time spent, unfinished work, and plans for real-world use.

The README must answer: who needs access and why; how passwords and the Terraform state are protected; how long data is kept; how costs are controlled; how resources are removed; how the system recovers from failure.

## 6. Constraints

- At most 24 hours of human work over three working days. Time spent and unfinished items must be reported.
- Required tasks first. Extras (subgroup comparisons, complex models, cloud deployment, extra monitoring) are optional.
- No paid services, no account upgrades. Lack of cloud credits does not lower the score. Cloud steps that could not be tested must be listed.
- No automatic scaling, full cloud monitoring or managed scheduler required.
- AI use is allowed, must be declared per part, and the candidate must understand and be able to modify everything.

## 7. How the work will be judged

Written criteria come from the brief. Implicit criteria are what an experienced ML lead at a medical device startup will look for.

| Criterion | What proves it in this repo |
|---|---|
| No leakage | 24 h cutoff test at the boundary, forbidden-column test, pipelines fitted on train only, test scored once, choices logged from validation |
| Reproducibility | `make reproduce` from raw files, checksums, committed split IDs, pinned lockfile, seed in config, identical metrics on rerun |
| Traceability | Every prediction returns model version, training data checksum and code commit; `metadata.json` per model |
| Safety reasoning | Explicit behaviour for missing and out-of-range inputs, abstention when no vital is available, threshold justified by clinical trade-off, calibration reported |
| Honest evaluation | Baselines next to every metric, bootstrap confidence intervals, missing-vitals analysis, limitations stated plainly |
| Engineering quality | Small readable modules, typed functions, docstrings, tests, green CI, tiny dependency set |
| Operations thinking | Structured logs without patient data, monitoring check with a baseline, documented release and rollback, least-privilege IAM, budget alert |
| Communication | README a reviewer can follow in 10 minutes, model card, ADRs, time log, honest AI usage |

## 8. What makes a reviewer say "this candidate is strong"

These items cost little time and separate a careful submission from an average one. Each one is specified in the other specs.

- One command rebuilds everything, and a fresh clone works on the first try.
- The feature code is a single module shared by training and the API, so training and serving cannot drift apart.
- The 24:00 boundary is tested at 24:00 and 24:01.
- Every metric is printed next to its naive baseline and with a 95 % confidence interval.
- The threshold is chosen for a target sensitivity on validation, with the resulting alert load reported.
- Class weights are not used, to keep probabilities calibrated; the threshold handles the imbalance. The reason is written down.
- The served model is chosen on validation results, never on test results.
- The API abstains when all three vitals are missing instead of returning a number built on nothing, and says why.
- Missingness is treated as information (RespRate absence relates to ventilation practice), and this is checked with data rather than assumed.
- Decisions are recorded as short ADRs.
- Logs never contain patient values.
- Terraform follows least privilege, pins versions, keeps state remote and versioned, and includes a budget alert.
- The selection bias of the 48 hour inclusion rule is explained in concrete terms.

## 9. Out of scope

Lab variables, deep learning, automatic retraining, autoscaling, a managed scheduler, a frontend, authentication beyond what the infra spec describes, MLflow or any experiment tracker, paid cloud services.

## 10. Glossary

| Term | Meaning in this project |
|---|---|
| Record | One ICU stay in set A, identified by `RecordID` |
| Cutoff | Minute 1440 after ICU admission, inclusive |
| Vitals | `HR` (heart rate, bpm), `RespRate` (breaths per minute), `Temp` (degrees Celsius) |
| Admission fields | `Age`, `Gender`, `ICUType`, recorded at 00:00 |
| PR-AUC | Area under the precision-recall curve, estimated with average precision |
| Brier score | Mean squared error between predicted probability and outcome, lower is better |
| Data-quality status | `ok`, `partial` or `insufficient`, returned by the API with every response |
| Model version | Semantic version of a trained model folder, for example `1.0.0` |
| ADR | Architecture Decision Record, a short file in `docs/decisions/` |
