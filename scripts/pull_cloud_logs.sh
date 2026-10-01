#!/usr/bin/env bash
# Pull Cloud Run /predict request log payloads into logs/cloud_requests.jsonl.
# Prerequisites: gcloud CLI (authenticated), jq (optional step only; not required for make check).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${ROOT}/logs/cloud_requests.jsonl"
mkdir -p "${ROOT}/logs"

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required for pull_cloud_logs.sh. Install jq and retry." >&2
  exit 1
fi

gcloud logging read \
  'resource.type="cloud_run_revision" AND jsonPayload.path="/predict"' \
  --format=json \
  --limit=500 \
  | jq -c '.[].jsonPayload' > "${OUT}"

echo "Wrote $(wc -l < "${OUT}") lines to ${OUT}"
