# 004. Tie-breaking for last vital value

Date: 2026-09-29
Status: accepted

## Context

Each vital feature set includes `*_last`, the measurement closest to the end of the first 24 hours. Two rows can share the same `minute` (duplicate timestamps in a record file, or multiple updates logged at one clock time). The data pipeline keeps distinct rows when they differ in any field and assigns `row_order` from file order during parse.

Training and the API must pick the same row when several measurements share the maximum minute in the window.

## Decision

For each vital and record, `*_last` is the `value` on the row with the highest `minute` in the vitals table. If several rows share that minute, take the row with the highest `row_order` (latest line in the source file).

Implementation sorts by `record_id`, `minute`, and `row_order`, then uses the last value per `record_id` group.

## Alternatives considered

- First row at the maximum minute: rejected; file order usually means later lines are more recent updates.
- Mean at the maximum minute: rejected; the brief defines `*_last` as a single measurement, not an aggregate at one timestamp.

## Consequences

Serving and training stay aligned as long as both use `compute_features` on the same vitals table shape. Unit tests cover the same-minute case with synthetic vitals because F2 drops exact duplicate rows in fixtures.
