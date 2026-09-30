# 010. Google Cloud as target cloud

Date: 2026-09-30
Status: accepted

## Context

The brief requires Terraform for a cloud deployment of the Dockerized API. The stack must be explainable in a review, stay within a demo budget, and use a Canadian region where practical for health-related workloads.

## Decision

Use Google Cloud in region `northamerica-northeast1` (Montréal) with Cloud Storage for artifacts, Artifact Registry for images, Cloud Run for the API, and Cloud Logging for container stdout. Infrastructure is defined in `infra/` with the `hashicorp/google` provider.

## Alternatives considered

- AWS (S3, ECR, ECS Fargate, CloudWatch): equivalent roles, not chosen to keep one provider and match the brief’s listed GCP option.
- Azure (Blob, ACR, Container Apps, Monitor): same trade-off.
- GKE or always-on VMs: higher cost and ops surface than Cloud Run scale-to-zero for a take-home demo.

## Consequences

Reviewers need a GCP project only for optional real deploy (O1). `terraform validate` and CI do not need an account. Equivalence tables and resource mapping live in `docs/infrastructure.md`.
