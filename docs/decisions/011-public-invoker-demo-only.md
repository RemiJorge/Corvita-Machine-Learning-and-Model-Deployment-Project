# 011. Public Cloud Run invoker for demo only

Date: 2026-09-30
Status: accepted

## Context

Cloud Run requires the `roles/run.invoker` permission on each caller. Reviewers need a simple way to hit the demo URL with `curl` without provisioning hospital-side service accounts.

## Decision

Terraform variable `allow_public_invoker` defaults to `false`. When set to `true`, the stack adds `google_cloud_run_v2_service_iam_member` with member `allUsers` and role `roles/run.invoker`. Use this only for short-lived demos. Production would use authenticated callers (hospital integration service account, workforce identity, or an identity-aware proxy in front of the service).

## Alternatives considered

- Always require authenticated invokers: correct for production but blocks anonymous reviewer curls without extra setup.
- API keys inside the application: duplicates platform IAM, adds secret handling, out of scope for F12.

## Consequences

Some GCP organizations forbid `allUsers` bindings via policy; `infra/README.md` documents that risk. Default `false` keeps `terraform plan` safe for accounts with restrictive org policies until the human explicitly opts in.
