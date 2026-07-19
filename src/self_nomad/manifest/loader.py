from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from self_nomad.errors import ManifestError
from self_nomad.manifest.schema import Manifest


def load_yaml(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as stream:
            return yaml.safe_load(stream)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ManifestError(f"cannot load {path.name}: {exc}") from exc


def load_manifest(path: Path) -> Manifest:
    raw = load_yaml(path)
    if not isinstance(raw, dict):
        raise ManifestError("self-nomad.yaml must contain a YAML mapping")
    try:
        return Manifest.model_validate(raw)
    except ValidationError as exc:
        raise ManifestError(f"invalid self-nomad.yaml: {exc}") from exc

