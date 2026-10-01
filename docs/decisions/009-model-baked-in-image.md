# 009. Model artifacts baked into the Docker image

Date: 2026-09-30
Status: accepted

## Context

The API must serve a fixed scikit-learn pipeline with metadata (threshold, feature columns, training data digest). Deployments need a clear rollback story: which code and which model answered a given request.

## Decision

The production Docker image copies each packaged model folder needed at runtime (currently `models/1.0.0` and `models/1.0.1`, pipeline and `metadata.json`) at build time. An image tag therefore identifies application code plus the models baked in. Rollback is redeploying a previous image tag on Cloud Run, or setting `MODEL_VERSION` to another folder that was copied into the same image (for example `1.0.0` vs `1.0.1` locally).

## Alternatives considered

- Load the pipeline from Cloud Storage at startup: better for frequent retrains without rebuilding the image; deferred to `docs/infrastructure.md` as the scale-up option.
- Mount models as a volume at run time: rejected for the take-home demo; weakens immutability of the tag.

## Consequences

Each model promotion requires a new image build. Image size includes the joblib file (small for this project). `MODEL_VERSION` still allows switching among versions copied into the image.
