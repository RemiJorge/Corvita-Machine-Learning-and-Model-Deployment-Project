# AGENTS.md

Operating manual for every coding agent working in this repository. Read it in full before touching any file. The documents in `docs/process/specs/` (paths below as `specs/` relative to `docs/process/`) are the source of truth. If a request, a spec and the code disagree, stop and ask the human owner.

## Context

- Candidate take-home project for Corvita Biomedical (Toronto), role focused on ML, MLOps and cloud for NOA, the AI assistant of the ARK neonatal incubator.
- Task: predict in-hospital death from the first 24 hours of adult ICU data (PhysioNet Challenge 2012, set A), serve the model behind a FastAPI endpoint in Docker, test it, monitor it, and describe the cloud setup in Terraform.
- Human owner: Rémi Jorge. He supervises, runs every command himself, verifies each feature by hand, and must explain every line of code during a live review where he will also make a small change on the spot.
- The reviewers state that AI coding assistants are allowed, and that any work the candidate cannot explain or test counts as incomplete. Code that is short, obvious and well documented is therefore worth more than code that is clever.
- Budget: at most 24 hours of human time over three working days, including supervision.
- There is no minimum model score. The evaluation is about rigor, reproducibility, traceability, safety reasoning and clarity.

## Reading order

| Order | File | Read when |
|---|---|---|
| 1 | `specs/00_PROJECT_BRIEF.md` | Always, first |
| 2 | `specs/01_ARCHITECTURE_AND_CONVENTIONS.md` | Always, before writing code |
| 3 | `specs/02_ROADMAP.md` | Always, to find the current feature |
| 4 | `specs/03_DATA_SPEC.md` | Features F1 to F5 |
| 5 | `specs/04_MODELING_SPEC.md` | Features F4 to F8 |
| 6 | `specs/05_API_SPEC.md` | Features F9 and F10 |
| 7 | `specs/06_QUALITY_CI_MONITORING_SPEC.md` | Every feature (tests), F10 and F11 |
| 8 | `specs/07_INFRA_SPEC.md` | Feature F12 |
| 9 | `specs/08_DOCUMENTATION_SPEC.md` | Every feature (docs), F13 |
| 10 | `docs/demo.md` | F13 and F14 (live review script) |

## Non-negotiable rules

1. **One feature at a time.** Work only on the feature marked as current in `specs/02_ROADMAP.md`. Do not start the next one. Do not add anything that no spec asks for.
2. **No data leakage.** Outcome fields (`SAPS-I`, `SOFA`, `Length_of_stay`, `Survival`, `In-hospital_death`) are never model inputs. Nothing is fitted on validation or test data. The test set is scored once, after every choice is frozen. Measurements after minute 1440 never reach the model.
3. **Simplicity first.** Plain functions in small modules. No class unless it holds state that several functions need. No design patterns, plugin systems, registries or abstract base classes. A reviewer should understand any module in one read.
4. **Dependency whitelist.** Only the libraries listed in `specs/01_ARCHITECTURE_AND_CONVENTIONS.md`. Adding one needs the human owner's approval and an ADR in `docs/decisions/`.
5. **Determinism.** Every random operation uses the seed from `config/config.yaml`. Running the pipeline twice on the same machine gives identical split files and identical metrics.
6. **Configuration over constants.** Every tunable value (seed, cutoff, physiological bounds, hyperparameter grids, target sensitivity, monitoring thresholds, paths) lives in `config/config.yaml`. No magic numbers in code.
7. **English only.** Code, comments, docstrings, docs, commit messages, log messages.
8. **Nothing sensitive or heavy in Git.** No raw or processed data, no credentials, no `.env`, no Terraform state. Committed on purpose: split ID files, the small serialized model folders under `models/`, reports and figures.
9. **Tests ship with the feature.** Every feature adds or updates tests. `make check` passes before handing back.
10. **Docs ship with the feature.** Update the relevant page in `docs/`, `CHANGELOG.md` and the package version in `pyproject.toml`.
11. **Never claim without running.** Every statement that something works is backed by a command you ran, with its output pasted in the handoff report.
12. **Stop at the gate.** After each feature, write the handoff report and wait for the human owner. Do not continue on your own.

## Feature workflow

1. Create a branch `feature/Fx-short-name` from `main`.
2. Read the feature entry in `specs/02_ROADMAP.md` and every spec it references.
3. Post a short plan to the human: files to create or modify, functions with one-line purpose, tests to add. Keep it under 20 lines. Wait for a go if the plan deviates from the spec in any way.
4. Implement in small commits following Conventional Commits (see conventions spec).
5. Add tests. Run `make check` (lint, format check, tests).
6. Update docs, `CHANGELOG.md` under `[Unreleased]`, then move the entry to the new version and bump `pyproject.toml`.
7. Write the handoff report below and stop.
8. After human approval: the human merges into `main` and creates the tag `vX.Y.Z`. Agents do not run merge, commit, push, or tag unless the human explicitly asks for a commit in that session.

## Handoff report template

```markdown
## Feature Fx: <name>  (version X.Y.Z)

Status: ready for human verification

### What changed
- <file>: <one line>

### Commands run
<command>
<trimmed output>

### Human verification steps
<copied from the roadmap entry, with the expected result for each>

### Decisions taken
- <decision> (ADR: docs/decisions/NNN-title.md, if any)

### Limitations and open questions
- <item>
```

## Stop and ask when

- a spec is ambiguous or two specs contradict each other;
- the data does not match `specs/03_DATA_SPEC.md` (file names, columns, counts, formats);
- a test can only pass by weakening a rule written in a spec;
- a new dependency seems necessary;
- anything would touch a real cloud account, billing, or credentials;
- you are about to spend a long time on an optional item.

## Writing style for code comments and docs

- Plain technical English, short sentences, concrete values ("1440 minutes", "15 % of RecordIDs").
- Comments explain why, never what the next line obviously does.
- No em dashes or en dashes as punctuation. Use a colon, a comma, parentheses or a new sentence.
- No marketing vocabulary: robust, seamless, leverage, cutting-edge, state-of-the-art, comprehensive, crucial, powerful, elegant.
- No emojis. No bold used for decoration. No closing paragraph that repeats what was just said.
- Formatting only where it helps: commands in code blocks, schemas in tables, steps as numbered lists.

## Global definition of done

- [ ] `make check` passes locally.
- [ ] `make reproduce` rebuilds features, splits and metrics from the source files (from F8 on).
- [ ] Every public function has a docstring with arguments, return value and raised errors.
- [ ] No unused import, file, function, config key or dependency.
- [ ] Docs, changelog and version updated.
- [ ] Handoff report written with real command output.
