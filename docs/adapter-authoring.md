# Adapter authoring

An adapter implements `RuntimeAdapter` and must keep inspection separate from
mutation. It detects zero or more explicit runtime candidates, builds import
and restore `TransferPlan` values, validates runtime constraints, and applies
only a previously displayed restore plan.

Use the **kit** in `self_nomad.adapters.kit` (`has_portable_content`,
`runtime_exclusions`, `unmapped_exclusions`, `transfer_plan`) so a third
runtime is a recipe, not a rewrite. Copy `self_nomad.adapters.example`
(`ExampleFilesAdapter`, name `example-files`) as a starting module. It is
**not** in `default_registry()`. Registered adapters are `hermes`, `openclaw`,
`agents-md`, `claude-code`, and the thin wrappers `codex`, `cursor`, and `copilot`.

Mappings use one of `exact`, `adapted`, `lossy`, `unsupported`,
`runtime_owned`, or `excluded_sensitive`. Never silently omit an artifact —
report knowledge, workflows, and evaluations even when they have no mapping.
Credentials, sessions, databases, caches, and runtime state must not become
canonical content.

Adapters do not run Git and do not decide proposal authorization. Imports are
materialized into controlled staging and handed to the proposal service.
Restore implementations recheck planned hashes, back up replaced files, use
an adjacent complete staging tree, verify before mutation, swap at the runtime
directory boundary, verify again, and automatically restore the original on
failure. Directory mappings replace rather than merge their destination.

Every adapter needs synthetic fixtures proving both inclusion and exclusion,
runtime-specific validation, conflict behavior, backup recovery, and fidelity
reporting. Sensitive fixtures use unmistakable sentinel values and tests must
prove those values never reach canonical staging.

Run the contract suite when adding an adapter:

```bash
uv run pytest tests/adapters/test_contract.py tests/integration/test_adapters.py
```

Current product adapters follow the official [Hermes memory and profile
documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory/)
and [OpenClaw workspace documentation](https://docs.openclaw.ai/agent-workspace)
(verify mappings before each release; host layouts may change).

## Implementation checklist

1. **Subclass `RuntimeAdapter`** with a unique `name`.
2. **Detect** zero or more roots; never invent paths.
3. **Plan import/restore** with explicit `Mapping` fidelity and exclusions for
   every known artifact class (no silent drops). Use `unmapped_exclusions` for
   classes without a runtime path.
4. **Never map** credentials, sessions, DBs, caches, or secret files to
   canonical content (`runtime_exclusions` with `EXCLUDED_SENSITIVE`).
5. **Validate** runtime constraints without mutating.
6. **Restore** only through the transactional helper path (stage → verify →
   backup → swap → verify → rollback).
7. **Register** product adapters in `default_registry()`. Leave kit samples
   unregistered.
8. **Fixtures** under `tests/fixtures/<adapter>/` with positive and negative
   cases (inclusions + exclusions).
9. **Tests** for conflict, backup recovery, fidelity reporting, and the
   contract module.
10. **Document** operator mappings in [runtime-portability.md](runtime-portability.md).
11. **Do not import** `GitBackend` or the proposal service from an adapter.

## Related

- [Runtime portability](runtime-portability.md)
- [Architecture](architecture.md)
- [Threat model](threat-model.md)
- [Compatibility](compatibility.md)
