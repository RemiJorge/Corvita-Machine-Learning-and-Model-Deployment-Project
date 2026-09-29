# 003. Handling minus one

Date: 2026-09-29
Status: accepted

## Context

PhysioNet Challenge 2012 uses `-1` as a missing-value marker in descriptor rows (for example `Height`, `Weight`) and in time series parameters. The data spec requires treating it as missing everywhere before bounds checks and feature work.

On the full set A run (4000 records), `reports/data_quality.json` reports:

- HR, RespRate, Temp: `n_minus_one` = 0 each (no sentinel in those vitals in this extract).
- Gender: 3 records with missing gender after conversion (sentinel `-1` at admission).
- Other parameters (Height, Weight, labs, etc.) also contain `-1` in the long table; they are not modeled but are converted to NaN for consistency if present in parsed rows.

## Decision

In `icu.quality.apply_minus_one`, any measurement with `value == -1` becomes NaN. Counts are stored per parameter (`n_minus_one` for vitals in the quality report; descriptor missing counts reflect NaN after this step).

## Alternatives considered

- Keep `-1` as a numeric category: rejected; the dataset documentation defines it as missing and models would treat it as a real value.
- Impute `-1` with median vitals: rejected for F2; imputation belongs in modeling only if explicitly specified later.

## Consequences

Parsed `measurements.parquet` after quality holds NaN where `-1` appeared. F3 builds vitals and admission tables from these cleaned values. The API must call the same function so serving matches training.
