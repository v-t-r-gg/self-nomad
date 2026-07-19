# Self Repository Format v1

`self-nomad.yaml` is the portable root manifest. Paths are repository-relative
POSIX paths; absolute paths, backslashes, NUL bytes, `.` and `..` components,
escaping symlinks, and special files are invalid. Only manifest-referenced
artifacts are authoritative.

The canonical artifact classes are identity and instructions, curated memory,
Agent Skills packages, tool notes, workflows, and deterministic evaluations.
Credentials, sessions, runtime databases, caches, logs, model data, and raw
transcripts are never portable by default.

Machine-specific runtime paths belong in the ignored
`.self-nomad.local.yaml` or the platform configuration directory, never in the
portable manifest.

