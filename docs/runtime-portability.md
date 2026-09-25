# Runtime portability

Operator-facing guide for detection, import, restore, and exclusions.
Adapter implementation details live in [adapter-authoring.md](adapter-authoring.md).

Two families stay separate. Hermes and OpenClaw are personal agent homes.
`agents-md` is a project workspace. Claude-specific precedence is a different
adapter.

Hermes and OpenClaw layouts were verified against the self-nomad adapters as of
**2026-08-17**. Host conventions can change; re-check official docs before
production migrations. `agents-md` follows the AGENTS.md workspace convention.
Claude Code 2.1.277 (2026-09-18) reads `AGENTS.md` when `CLAUDE.md` is absent;
that precedence is not implemented by `agents-md`.

## Shared behavior

| Topic | Behavior |
| --- | --- |
| Preview default | `import` / `restore` plan without `--yes` |
| Import with `--yes` | Creates an isolated **proposal** (does not apply the target branch) |
| Restore with `--yes` | Transactional write to the runtime tree (stage → verify → backup → swap) |
| Secrets / sessions | Never portable; listed as exclusions |
| Unmapped classes | Always listed on the plan (`knowledge`, `workflows`, `evaluations`, …) |
| Backups | Under platform state for restore rollback |
| Symlinks | Rejected as artifact sources/targets |

```bash
self-nomad --repo ./agent detect --adapter hermes
self-nomad --repo ./agent diff --adapter hermes --direction import --path ~/.hermes
self-nomad --repo ./agent import --adapter hermes --from ~/.hermes
self-nomad --repo ./agent import --adapter hermes --from ~/.hermes --yes
self-nomad --repo ./agent restore --adapter openclaw --to ~/.openclaw/workspace
self-nomad --repo ./agent restore --adapter openclaw --to ~/.openclaw/workspace --yes
```

## Comparison table

| Artifact class | Hermes runtime path | OpenClaw runtime path | Canonical (repo) | Fidelity |
| --- | --- | --- | --- | --- |
| Persona | `SOUL.md` | `SOUL.md` | `identity/persona.md` | exact |
| Instructions | — (excluded) | `AGENTS.md` | `identity/instructions.md` | adapted (OpenClaw) |
| Identity | — (excluded) | `IDENTITY.md` | `identity/identity.md` | exact |
| User profile | `memories/USER.md` | `USER.md` | `identity/user.md` | exact |
| Long-term memory | `memories/MEMORY.md` | `MEMORY.md` | `memory/MEMORY.md` | exact |
| Daily memory | — (excluded) | `memory/` | `memory/daily` | exact |
| Skills | `skills/` | `skills/` | `skills/` | exact |
| Tool notes | — (excluded) | `TOOLS.md` | `tools/notes.md` | exact |
| Knowledge | — (excluded) | — (excluded) | `memory/knowledge` | unsupported |
| Workflows | — (excluded) | — (excluded) | `workflows` | unsupported / lossy |
| Evaluations | — (excluded) | — (excluded) | `evals` | unsupported |
| Bootstrap | — | `BOOTSTRAP.md` | — | **runtime-owned / exclude** |
| Config / `.env` / DBs | under Hermes home | under OpenClaw **state** dir | — | **runtime-owned** |
| Sessions | excluded | excluded | — | **runtime-owned** |

Canonical paths come from `self-nomad.yaml` `content.*` fields (defaults shown
in [repository-format.md](repository-format.md)).

## agents-md (project workspace)

**Detection:** the directory passed to `--path` / `--from`. A candidate needs
`AGENTS.md` or a non-empty `skills/` tree. A README-only repository is not a
candidate. The adapter does not scan the home directory.

| Runtime file | Canonical | Fidelity |
| --- | --- | --- |
| `AGENTS.md` | `identity/instructions.md` | adapted |
| `skills/` | `skills/` | exact |
| `SOUL.md` | `identity/persona.md` | exact |
| `IDENTITY.md` | `identity/identity.md` | exact |
| `USER.md` | `identity/user.md` | exact |
| `MEMORY.md` | `memory/MEMORY.md` | exact |
| `TOOLS.md` | `tools/notes.md` | exact |
| `memory/daily/` or a `memory/` tree of only `YYYY-MM-DD.md` notes | `memory/daily` | exact |

A `memory/` directory that mixes a dump with other files is not treated as
daily notes. It stays unmapped. Knowledge, workflows, and evaluations are
always listed as unmapped.

**Always excluded and reported:** `.env`, `.env.*`, `.claude/`, `.codex/`,
`.cursor/`, `node_modules`, `.git`, session `*.db` files, and GitHub token
files under `.github/` when those names appear. `AGENTS.md` is adapted, not a
byte-identical copy of a runtime instruction format.

```bash
self-nomad --repo ./agent detect --adapter agents-md --path ./workspace
self-nomad --repo ./agent import --adapter agents-md --from ./workspace
```

## Hermes

**Detection roots:** `$HERMES_HOME` or `~/.hermes`, plus `profiles/*` children
that look compatible (`SOUL.md`, `config.yaml`, `memories`, or `skills`).

**Imported / restored:** persona, long-term memory, user profile, skills (when
manifest paths are set and files exist).

**Always excluded and reported:** instructions, identity file, daily memory,
tool notes, knowledge, workflows, evaluations; `.env`, `state.db`,
configuration, cron, plugins, checkpoints, backups, logs, gateway state.

## OpenClaw

**Detection roots:** `$OPENCLAW_WORKSPACE_DIR` or
`~/.openclaw/workspace` (or `workspace-<profile>` when `OPENCLAW_PROFILE` is
not `default`).

**Important:** OpenClaw’s **state directory** is outside the portable workspace
boundary and is never an adapter input.

**Imported / restored:** AGENTS (adapted), SOUL, IDENTITY, USER, TOOLS, MEMORY,
daily `memory/`, skills.

**Always excluded and reported:** `BOOTSTRAP.md`, `BOOT.md`, `HEARTBEAT.md`
(lossy), canvas, configuration, credentials, sessions, agent databases;
knowledge (unsupported), workflows (lossy), evaluations (unsupported).

`AGENTS.md` is **adapted**: byte copy of `identity/instructions.md`, not a
claim that OpenClaw and self-nomad interpret the file the same way.

## Restore guarantees

1. Build and verify a complete sibling staged tree.
2. Copy replaced artifacts to restrictive local backup state.
3. Atomic directory swap into the live runtime path.
4. Re-verify live hashes.
5. Automatic rollback of the original directory on failure.

## Fidelity losses

- OpenClaw `AGENTS.md` ↔ instructions mapping is **adapted**, not
  byte-identical semantics.
- Knowledge, workflows, and evaluations have no lossless Hermes or OpenClaw
  mapping and are **always listed** as exclusions.
- Anything not listed in the plan is out of scope.

## Related

- [Getting started](getting-started.md) for proposal apply after import
- [Adapter authoring](adapter-authoring.md) for the kit and contract tests
- [Threat model](threat-model.md) for exclusions as a security boundary
