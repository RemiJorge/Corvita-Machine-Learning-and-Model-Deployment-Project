# 08. Documentation specification

F13 delivered the final README, model card, and `docs/demo.md`. F14 is fresh-clone rehearsal and human sign-off on `TIME_LOG.md` / `AI_USAGE.md`.

Reviewers will read the README first and may read little else. It must let them understand the project, run it, and find every answer the brief asks for in about 10 minutes. The pages in `docs/` hold the detail.

Every number in the documentation comes from a file in `reports/` or `models/`, copied after a real run. No number is typed from memory or estimated.

Style rules from `AGENTS.md` apply to every page: plain English, short sentences, concrete values, no em dashes, no marketing words, no decorative formatting.

## 1. Documents to produce

| File | Written in | Content |
|---|---|---|
| `README.md` | F0 (stub), F13 (final) | Entry point, see section 2 |
| `docs/data.md` | F1 to F3 | Source, license, manifest, parsing and cleaning rules, cutoff, quality report summary, selection bias |
| `docs/modeling.md` | F4 to F8 | Features, split, pipelines, tuning, threshold, evaluation method, reproducibility |
| `docs/model_card.md` | F7, final in F13 | Model summary required by the brief, see section 3 |
| `docs/api.md` | F9, F10 | Schemas, behaviours, examples with real responses, logging policy |
| `docs/operations.md` | F10 | Monitoring check, drift detection, retraining, release, rollback, incidents |
| `docs/infrastructure.md` | F12 | Architecture, resource by resource, access model, costs, recovery |
| `docs/demo.md` | F13 | Review script and live change drills |
| `docs/decisions/*.md` | When decided | ADRs |
| `infra/README.md` | F12 | Commands, outputs of init and validate, cost estimate, untested steps |
| `CHANGELOG.md` | Every feature | Keep a Changelog |
| `TIME_LOG.md` | Every session | Filled by the human owner |
| `AI_USAGE.md` | Every feature | Filled with the human owner |

## 2. README structure

```markdown
# ICU mortality risk from first-day vitals

<one paragraph: what it predicts, from what, why this project exists (Corvita take-home),
and the sentence that it is not a clinical tool and not for newborns>

<CI badge>

## Results at a glance
<table: both models, test PR-AUC, AUROC, sensitivity, specificity, Brier, each with 95 % CI,
baseline row; one sentence on which model is served and why (validation-based)>

## Quick start
<prerequisites with versions: Python 3.12, uv, Docker, Terraform, make>
<numbered commands: setup, data, reproduce, test, docker-run, three curl calls, monitor, tf-validate,
each with the expected result in one line>

## How it works
<data flow diagram as a short text block, 8 to 10 lines>
<one paragraph per stage with a link to the detailed doc>

## Input fields
<table: field, source, unit, cleaning rule, feature(s) produced>

## Reproducibility
<what is pinned (lockfile, seed, checksums, split files, model metadata)>
<expected differences across machines>

## API
<request and response example, the three data-quality statuses, abstention rule, error codes, link to docs/api.md>

## Monitoring and operations
<what is logged and what is never logged, the monitoring check and its exit codes,
drift, manual retraining, release, rollback in five short paragraphs with links>

## Cloud setup
<architecture table, access model table, secrets and state, retention, costs, removal, recovery,
untested steps, link to infra/README.md and docs/infrastructure.md>

## Limitations
<selection bias of the 48 h rule, single hospital system, adult data, age of the data,
three vitals only, small test set, calibration, no external validation>

## Path to real-world use
<external and prospective validation, population without the 48 h filter, clinical review of
the threshold, shadow deployment, regulatory context (software as a medical device,
IEC 62304, Health Canada), integration with hospital records (HL7 FHIR), monitoring with labels>

## Project management
<time spent per day and total, from TIME_LOG.md; unfinished items; link to CHANGELOG and ADRs>

## Use of AI tools
<summary per part from AI_USAGE.md, and the statement that every part was reviewed,
run and understood by the author>

## Repository layout
<tree, 15 lines max>
```

## 3. Model card (`docs/model_card.md`)

The brief asks for "a short model summary covering its purpose, results and limits". Keep it to one or two screens.

```markdown
# Model card: ICU in-hospital mortality, first 24 hours

- Model version: 1.0.0
- Served model: <type and hyperparameters>
- Trained on: PhysioNet Challenge 2012 set A, manifest SHA-256 <digest>, training split <n> records
- Code: <git commit>, package <version>

## Intended use
Demonstration of an end-to-end ML workflow for a hiring exercise. Not validated for clinical use.
Not applicable to newborns.

## Inputs
<fields and features, with the 24 h window>

## Outcome
In-hospital death during the stay.

## Performance on the test set (<n> records, <k> deaths)
<table with both models, CIs and baselines>
Operating threshold <t>, chosen on validation for sensitivity >= 0.80:
sensitivity <x>, specificity <y>, <z> alerts per 100 patients.

## Calibration
<one paragraph and the figure>

## Behaviour with missing vitals
<summary of subgroup and ablation results, abstention rule>

## Limitations
<same list as the README, one line each>

## Ethical and safety notes
Probabilities are estimates for a population unlike the one where they would be used. A clinician
decides; the model can abstain; logs contain no patient values.
```

## 4. `TIME_LOG.md` format

```markdown
| Date | Start | End | Hours | Feature | Notes |
|---|---|---|---|---|---|
| 2026-10-01 | 09:00 | 09:45 | 0.75 | F0 | Bootstrap, lockfile |

Total: <sum> h of 24 h.
Unfinished: <list or "none">.
```

Human time only (supervision, reading, running, writing). Agent runtime is not the candidate's work time, but the time spent waiting on it is.

## 5. `AI_USAGE.md` format

```markdown
| Part | Tool | What the AI did | What the author did |
|---|---|---|---|
| Specifications | Claude (chat) | Drafted the specs from the brief | Defined requirements, reviewed and edited every spec |
| Parsing (F2) | <coding agent> | Wrote parse.py and tests | Wrote the rules, reviewed the code line by line, checked outputs against raw files |
```

Honest and specific. The brief penalises work the candidate cannot explain, not the use of AI.

## 6. ADR list to have by F13

1. Physiological and admission bounds (with percentiles).
2. Handling of `-1` values.
3. Tie-breaking for the last value.
4. No class weights.
5. Threshold rule and target sensitivity.
6. No refit on train plus validation.
7. Served model choice (validation numbers).
8. Abstention when all vitals are missing.
9. Rejecting unknown parameters in the API.
10. Model baked into the image.
11. GCP as target cloud.
12. Public invoker for the demo only.

## 7. Docstring example

```python
def apply_cutoff(measurements: pd.DataFrame, cutoff_minutes: int) -> tuple[pd.DataFrame, int]:
    """Keep measurements recorded up to and including the cutoff.

    The cutoff is inclusive so that a value at 24:00 (minute 1440) is kept,
    as required by the brief.

    Args:
        measurements: Long table with at least a ``minute`` column.
        cutoff_minutes: Last minute to keep, inclusive.

    Returns:
        The filtered table and the number of rows removed.
    """
```

## 8. Changelog example

```markdown
# Changelog

All notable changes to this project are documented here.
The format follows Keep a Changelog and the project uses Semantic Versioning.

## [Unreleased]

## [0.4.0] - 2026-10-01
### Added
- F3: 24 hour cutoff (inclusive at minute 1440) shared by training and API.
- F3: admission and vitals tables in data/processed.
### Changed
- Quality report now counts measurements excluded by the cutoff.
```
