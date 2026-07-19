from uuid import uuid4

import pytest
from pydantic import ValidationError

from self_nomad.manifest.schema import Manifest


def manifest_data() -> dict[str, object]:
    return {
        "schema_version": 1,
        "self": {"id": str(uuid4()), "name": "test"},
        "content": {"long_term_memory": "memory/MEMORY.md"},
        "policy": "policy/policy.yaml",
    }


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd", "a/./b", "a\\b", "a\x00b"])
def test_manifest_rejects_unsafe_paths(path: str) -> None:
    data = manifest_data()
    data["content"] = {"long_term_memory": path}
    with pytest.raises(ValidationError):
        Manifest.model_validate(data)


def test_manifest_rejects_unknown_keys() -> None:
    data = manifest_data()
    data["unexpected"] = True
    with pytest.raises(ValidationError):
        Manifest.model_validate(data)

