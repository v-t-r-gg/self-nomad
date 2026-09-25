# Self repository format (schema version 1)

`self-nomad.yaml` is the portable root manifest. Paths are repository-relative
POSIX paths. Absolute paths, backslashes, NUL bytes, `.` / `..` components,
escaping symlinks, and special files are invalid. Only manifest-referenced
artifacts are authoritative.

## Generated tree (init defaults)

```text
self-nomad.yaml
policy/policy.yaml
identity/instructions.md
identity/persona.md
identity/identity.md
identity/user.md
memory/MEMORY.md
tools/notes.md
# optional dirs referenced by manifest:
# memory/daily, memory/knowledge, skills, workflows, evals
```

## Manifest fields

| Field | Meaning |
| --- | --- |
| `schema_version` | `1` |
| `self.id` | UUID identity |
| `self.name` | Human name (1–128 chars) |
| `self.description` | Optional |
| `content.*` | Canonical relative paths for artifact classes |
| `skill_format` | e.g. `agent-skills` |
| `policy` | Path to policy YAML (default `policy/policy.yaml`) |
| `adapters.<name>.enabled` | Adapter toggles |

### Default content paths

| Class | Default path |
| --- | --- |
| instructions | `identity/instructions.md` |
| persona | `identity/persona.md` |
| identity | `identity/identity.md` |
| user_profile | `identity/user.md` |
| long_term_memory | `memory/MEMORY.md` |
| daily_memory | `memory/daily` |
| knowledge | `memory/knowledge` |
| skills | `skills` |
| tool_notes | `tools/notes.md` |
| workflows | `workflows` |
| evaluations | `evals` |

## Policy defaults (`policy/policy.yaml`)

| Section | Default |
| --- | --- |
| `approval.default` | `required` (`allowed` unsupported in v0.1+) |
| `approval.protected_paths` | manifest, policy, core identity files |
| `limits.maximum_file_bytes` | `1048576` (1 MiB) |
| `limits.maximum_proposal_files` | `100` |
| `limits.maximum_request_bytes` | `4194304` (4 MiB) |
| `validation.strict_schema` | `true` |
| `validation.reject_symlinks` | `true` |
| `validation.scan_for_secrets` | `true` |
| `validation.execute_repository_tests` | **`false`** |

## Canonical artifact classes

Identity and instructions, curated memory, Agent Skills packages, tool notes,
workflows, and deterministic evaluations. Credentials, sessions, runtime
databases, caches, logs, model weights, and raw transcripts are never portable
by default.

## Hashing and validation

- Authoritative files contribute relative path + SHA-256 to the content digest.
- Symlinks, special files, denylisted credential filenames, and oversize files
  invalidate the repository.
- Empty directories and `.gitkeep` have no portable semantics.
- UTF-8 is required for proposal content sources.

## Local configuration

Machine-specific runtime paths belong in ignored `.self-nomad.local.yaml` or
the platform configuration directory — never in the portable manifest.

## Schema compatibility

Repository schema version **1** is current. Unsupported versions raise load
errors. Bumping the schema requires an explicit product decision and ADR.
Shareable snapshots versus a personal working tree are defined in
[ADR 0007](decisions/0007-publishable-package-profile.md); schema 1 does not
grow license, author, or package-version fields without that kind of decision.
`self-nomad pack` writes an additive `self-nomad.pack.json` sidecar inside the
archive; it is not part of the repository schema. Specialist packs may include
`memory/PUBLISH.md` instead of `memory/MEMORY.md`. The digest and profile rules
are in [snapshot.md](snapshot.md).
