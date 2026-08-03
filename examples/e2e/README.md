# End-to-end intake walkthrough

Connects agent request → preview → submit → validate → operator review →
approve → apply. Uses placeholder paths; substitute absolute paths locally.
**No credentials or session files.**

## Files

| File | Role |
| --- | --- |
| [request.json](request.json) | Valid `ProposalRequest` v1 |
| [commands.sh](commands.sh) | Shell transcript (bash) |

## Flow

```text
intake preview → intake submit → proposal validate
  → operator review → approve → apply
```

MCP agents may perform preview/submit/validate via `self-nomad-mcp`. Approve
and apply remain CLI/operator only.

## Validate the request alone

```bash
# schema check (docs/package schemas must match)
uv run python scripts/export_proposal_request_schema.py --check
python - <<'PY'
from pathlib import Path
from self_nomad.intake import load_proposal_request
load_proposal_request(Path("examples/e2e/request.json").read_bytes())
print("request OK")
PY
```
