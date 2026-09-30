# 001. Reject unknown measurement parameters in the API

Date: 2026-09-30
Status: accepted

## Context

Clients send vital measurements as `{time, parameter, value}` tuples. Training uses exact names `HR`, `RespRate`, and `Temp`. A typo such as `Hr` would not match any vital column if it were dropped silently; the service would score the request as if heart rate were missing without telling the client.

## Decision

Pydantic validation on `PredictRequest` requires `parameter` to be one of the three allowed literals. Any other string returns HTTP 422 with a field error. The same rule applies to extra top-level JSON keys.

## Alternatives considered

- Coerce or ignore unknown parameters: rejected; hides client bugs and changes risk scores without an explicit warning.

## Consequences

Clients must send exact parameter names. Integration tests cover rejection of `Hr` and unknown top-level fields (`tests/test_api.py`).
