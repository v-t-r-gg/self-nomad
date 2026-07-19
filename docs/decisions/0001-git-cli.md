# ADR 0001: Use the Git CLI

Status: accepted

Use Git through argument-array subprocess calls with `shell=False`, explicit
working directories, non-interactive environment settings, captured output,
and timeouts. This keeps worktree and ref-update behavior reproducible from the
user's Git installation.

