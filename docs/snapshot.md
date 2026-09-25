# Snapshot packs

`self-nomad pack` writes a history-free archive. `self-nomad pack --check`
verifies one. `self-nomad install` turns a verified archive into a new local
repository. `self-nomad validate --strict` is the tree check those commands
run. `self-nomad restore` copies mapped files into a runtime directory.

The archive is not a Git clone. Working history, proposal records, and intake
receipts stay on the operator machine ([ADR 0007](decisions/0007-publishable-package-profile.md)).

## Format

- Format id: `self-nomad-pack-v1`
- Gzip tar (`.snpack` by convention)
- No `.git` member, no symlinks or hard links, no absolute paths, no `..`
- Sidecar `self-nomad.pack.json` is additive. A schema 1 tree loads without it
- JSON Schema: [self-nomad-pack-v1.schema.json](schema/self-nomad-pack-v1.schema.json)

Archive ceilings, independent of repository policy:

| Cap | Value |
| --- | --- |
| Members | 4096 |
| Bytes per member | 8 MiB |
| Uncompressed total | 64 MiB |

A member over the repository `maximum_file_bytes` still fails validation even
when it is under the archive ceiling.

## Profiles

Specialist is the default.

| Class | Specialist | Personal |
| --- | --- | --- |
| `user_profile` (`identity/user.md`) | always omitted | included |
| `daily_memory` (`memory/daily/`) | always omitted | included |
| `long_term_memory` | omitted unless `--include-long-term-memory` | included |
| persona, instructions, identity, skills, tool notes, knowledge, workflows, evals | included when present | included when present |

`pack --check` accepts a personal archive only with `--profile personal`.
The default check expects specialist.

## Shareable long-term memory

`--include-long-term-memory` on a specialist pack does **not** copy
`memory/MEMORY.md`. That file is the personal dump. The only long-term file
a specialist pack may contain is `memory/PUBLISH.md`, and only when the flag
is set. `init` writes a short stub there. If the stub is missing, the flag
fails closed. This is a file allow-list, not a claim that individual facts
inside `PUBLISH.md` were reviewed.

## `content_digest`

The digest is SHA-256 over the staged authoritative tree after export, not
over the sidecar and not over `.git`.

UTF-8 text is stored with LF newlines (`\r\n` and bare `\r` become `\n`)
before hashing. Bytes that are not UTF-8, or that contain NUL, are stored
unchanged. The same logical text therefore hashes the same on this host
whether the working tree used LF or CRLF. The sidecar's `created_at` is not
part of the digest, so packing the same tree twice yields the same digest.

## `pack --check --json`

The result object includes `profile`, `omitted`, `content_digest`, `skills`,
and `packer_version`, plus the full sidecar as `summary`. A registry indexer
can copy those fields without reading the tree a second time.

`pack --list` prints the same sidecar fields and the member names. It does
not validate the tree or the digest. Use `--check` before trusting an archive.

## Threat cases that fail closed

`pack --check` and `install` reject:

- path escape (`../`, `foo/../../etc/passwd`)
- a planted `.git` member
- symlinks and other special files
- member, count, or uncompressed-size bombs
- high-confidence secret patterns in authoritative files
- a file over policy `maximum_file_bytes`
- a specialist archive that still contains `identity/user.md`, `memory/MEMORY.md`, or `memory/daily/*`
- a digest that does not match the archived tree (including after a bit flip)
- a sidecar whose `self.id`, `self.name`, `self.description`, or skill names do not match the archived manifest and skill tree (those fields are recomputed; the digest does not cover the sidecar)
- `install` into a destination that already has files

Secret scanning remains high-confidence only. It is not general data-loss prevention.
