# Contributing

Use Python 3.11 or newer and `uv`.

```bash
uv sync
uv run ruff check .
uv run mypy
uv run pytest
uv build
```

Every public behavior should include tests. Security-sensitive changes need a
negative test proving the unsafe case is rejected.

