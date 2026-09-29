# 002. Physiological and admission bounds

Date: 2026-09-29
Status: accepted

## Context

After parsing set A (4000 records), `icu.quality` computed percentiles on values with `-1` already removed (see ADR 003). The report `reports/data_quality.json` from the F2 run shows:

| Field | Config bounds (inclusive) | p0.1 | p1 | p50 | p99 | p99.9 | n_out_of_bounds |
|---|---|---|---|---|---|---|---|
| HR | 20 to 300 | 40.0 | 51.0 | 86.0 | 137.0 | 162.0 | 16 |
| RespRate | 1 to 80 | 0.0 | 9.0 | 19.0 | 36.0 | 47.0 | 62 |
| Temp | 25.0 to 45.0 | 1.9 | 34.7 | 37.1 | 39.1 | 40.1 | 130 |
| Age | 15 to 120 | 17.0 | 20.0 | 67.0 | 90.0 | 90.0 | 0 |

Tail percentiles below the lower bound (RespRate p0.1 at 0, Temp p0.1 at 1.9) are recording errors or sentinel-like values, not plausible vitals. The chosen bounds clip a small number of rows (16 HR, 62 RespRate, 130 Temp) while keeping all observed clinical bulk (p1 through p99) inside the limits for HR and Temp; RespRate p1 is 9, above the lower bound of 1.

## Decision

Keep `physiological_bounds` and `admission_bounds.Age` in `config/config.yaml` unchanged for F2: HR [20, 300], RespRate [1, 80], Temp [25.0, 45.0], Age [15, 120]. Values outside these inclusive ranges become missing and are counted in the quality report.

## Alternatives considered

- Widen bounds to retain p0.1 values (for example RespRate from 0): rejected because 0 breaths per minute is not a usable measurement and would let the model learn from artifacts.
- Tighten bounds to p1/p99 only: rejected for F2; small OOB counts already show the current box matches the bulk of the data.

## Consequences

Training and the API will share the same bound checks in `icu.quality`. If future data drift pushes p99.9 outside config, update bounds only with a new ADR citing fresh percentiles from `data_quality.json`.
