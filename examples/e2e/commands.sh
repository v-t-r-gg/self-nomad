#!/usr/bin/env bash
# End-to-end intake → apply transcript (illustrative).
# Requires: uv, git, self-nomad on PATH or via `uv run`.
set -euo pipefail

REPO="${REPO:-/tmp/self-nomad-e2e}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REQUEST="$ROOT/examples/e2e/request.json"

rm -rf "$REPO"
uv run self-nomad init "$REPO" --name e2e-demo
uv run self-nomad --repo "$REPO" validate --strict

# Preview (zero write)
uv run self-nomad --repo "$REPO" --json intake --request "$REQUEST"

# Submit → materialized proposal
SUBMIT_JSON="$(uv run self-nomad --repo "$REPO" --json intake --request "$REQUEST" --submit)"
echo "$SUBMIT_JSON"
PROPOSAL_ID="$(python -c 'import json,sys; print(json.load(sys.stdin)["result"]["proposal_id"])' <<<"$SUBMIT_JSON")"

uv run self-nomad --repo "$REPO" review "$PROPOSAL_ID"
uv run self-nomad --repo "$REPO" validate "$PROPOSAL_ID"
uv run self-nomad --repo "$REPO" approve "$PROPOSAL_ID" --identifier operator

# Checked-out-target rule
git -C "$REPO" switch -c review-work
uv run self-nomad --repo "$REPO" apply "$PROPOSAL_ID"

git -C "$REPO" log --oneline -3
echo "e2e complete proposal_id=$PROPOSAL_ID"
