# 008. API abstention when no vital is usable

Date: 2026-09-30
Status: accepted

## Context

The prediction API accepts raw measurements for the first 24 hours. After the cutoff and physiological bounds, a record may have no valid HR, RespRate, or Temp left. The F2 quality report lists **71** of 4000 records with all three vitals missing in the first 24 hours (`reports/data_quality.json`, field `records_with_all_vitals_missing_in_24h`). Packaged training reference `insufficient_rate` is about 0.018 (roughly 51 training rows). Such cases are rare but present; for them the model would score from admission fields alone, which is not the risk estimate the service is meant to provide.

## Decision

When data quality status is `insufficient` (zero of three vitals with a valid measurement in the window), the API returns HTTP 200 with `probability: null`, `risk_flag: null`, and a fixed warning that the model abstains. The request is valid; the service refuses to emit a numeric risk score that would look like a normal prediction.

## Alternatives considered

- Return 422: rejected; the payload is schema-valid and abstention is an intentional outcome.
- Predict from admission fields only: rejected; the score would rest on age, sex and ICU type only and would mislead consumers.

## Consequences

Clients must treat null probability as "cannot assess". Monitoring (F10) will track `insufficient` rate against training reference. If future data show a large share of real patients with no vitals, revisit with the human owner.
