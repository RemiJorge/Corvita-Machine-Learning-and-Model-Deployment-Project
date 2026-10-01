# 012. Analysis notebook and Jupyter dev dependencies

Date: 2026-10-01
Status: accepted

## Context

Reviewers and interviewers need a single read-only walkthrough of cohort statistics, data quality, and test-set results without running the full training pipeline. Committed artifacts under `reports/` already hold the numbers and figures; duplicating that logic in a script would drift from `icu.features` and `icu.evaluate`.

## Decision

Add `notebooks/analysis.ipynb` as a documentation artifact that loads JSON reports and optional processed parquet for simple plots. Add `jupyter`, `nbconvert`, and `ipykernel` only to the `dev` dependency group in `pyproject.toml`, wired via `make notebook`. Do not install them in the production Docker image.

## Alternatives considered

- Sphinx or static HTML only: no inline plots from local parquet without a separate build step.
- Notebook in CI: rejected because PhysioNet data are not in Git and execution would be flaky on every push.
- Ship Jupyter in Docker: increases image size and attack surface for a demo API that does not need notebooks.

## Consequences

Contributors run `uv sync` to get notebook tools. GitHub can render the notebook with committed cell outputs. Training, tuning, and feature engineering stay in `src/icu/` only.
