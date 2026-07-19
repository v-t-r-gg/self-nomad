from pathlib import Path

from self_nomad.errors import ManifestError


def contained_path(root: Path, relative: str, *, must_exist: bool = False) -> Path:
    root = root.resolve(strict=True)
    candidate = root.joinpath(*relative.split("/"))
    try:
        resolved = candidate.resolve(strict=must_exist)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ManifestError(f"path escapes repository: {relative}") from exc
    return resolved

