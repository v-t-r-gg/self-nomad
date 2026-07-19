from pathlib import Path

from self_nomad.filesystem import atomic_write_text, sha256_file


def test_atomic_write_and_hash(tmp_path: Path) -> None:
    target = tmp_path / "value.txt"
    atomic_write_text(target, "portable\n")
    assert target.read_text() == "portable\n"
    assert sha256_file(target) == "3f8eb8d483dcd4a2b5d317b7a61b792c2eb2188a4e8291083a6a2561419268be"
