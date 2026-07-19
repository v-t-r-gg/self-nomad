# Adapter authoring

An adapter implements `RuntimeAdapter` and must keep inspection separate from
mutation. It detects zero or more explicit runtime candidates, builds import
and restore `TransferPlan` values, validates runtime constraints, and applies
only a previously displayed restore plan.

Mappings use one of `exact`, `adapted`, `lossy`, `unsupported`,
`runtime_owned`, or `excluded_sensitive`. Never silently omit an artifact.
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

Current contracts are based on the official [Hermes memory and profile
documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory/)
and [OpenClaw workspace documentation](https://docs.openclaw.ai/agent-workspace).
