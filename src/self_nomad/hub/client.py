"""Download or file-drop a pack. pack --check always runs before install or handoff."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urljoin, urlparse
from urllib.request import urlopen

from self_nomad.application import SelfNomad
from self_nomad.errors import ConflictError, PackError
from self_nomad.snapshot.models import PackSummary


def pull_pack(
    source: str,
    destination: Path,
    *,
    index_url: str | None = None,
) -> PackSummary:
    """Download or locate a .snpack, check it, then install. Check cannot be skipped."""
    archive = _resolve_archive(source, index_url=index_url)
    summary = SelfNomad.check_pack(archive)
    _installed, checked = SelfNomad.install_pack(archive, destination, initialize_git=False)
    if checked.content_digest != summary.content_digest:
        raise PackError("installed tree does not match the checked pack")
    return checked


def publish_pack(
    repo: Path,
    drop: Path,
    *,
    profile: str = "specialist",
    yes_personal: bool = False,
    include_long_term: bool = False,
) -> PackSummary:
    """Pack, check, and copy the archive to a file-drop path. No upload API."""
    if profile == "personal" and not yes_personal:
        raise ConflictError(
            "refusing to publish a personal-profile pack without --yes-personal"
        )
    if profile not in {"specialist", "personal"}:
        raise ConflictError("profile must be specialist or personal")
    packed = SelfNomad.open(repo).pack(
        drop,
        profile=profile,
        include_long_term_memory=include_long_term,
    )
    checked = SelfNomad.check_pack(drop, profile=profile)
    if checked.content_digest != packed.content_digest:
        raise PackError("file-drop failed pack --check")
    return checked


def _resolve_archive(source: str, *, index_url: str | None) -> Path:
    if source.startswith(("https://", "http://", "file:")):
        return _download(source)
    path = Path(source)
    if path.is_file():
        return path
    catalog = index_url or os.environ.get("SELF_NOMAD_INDEX_URL", "")
    if not catalog:
        raise ConflictError("pass a .snpack path or URL, or set SELF_NOMAD_INDEX_URL")
    return _pack_from_index(catalog, source)


def _pack_from_index(index_url: str, name: str) -> Path:
    payload = json.loads(_read_text(index_url))
    packages = payload.get("packages")
    if not isinstance(packages, list):
        raise PackError("index has no packages list")
    for entry in packages:
        if not isinstance(entry, dict) or entry.get("name") != name:
            continue
        pack = entry.get("pack")
        if not isinstance(pack, str) or not pack:
            break
        if pack.startswith(("https://", "http://", "file:")):
            return _download(pack)
        if _pack_ref_escapes(pack):
            raise PackError("pack path escapes the index")
        candidate = Path(pack)
        if candidate.is_file():
            return candidate
        if index_url.startswith(("https://", "http://")):
            return _download(_join_index_url(index_url, pack))
        located = _under_index_dir(index_url, pack)
        if located is not None:
            return located
        break
    raise PackError(f"index has no package named {name}")


def _pack_ref_escapes(pack: str) -> bool:
    """True when a relative index entry could leave the index directory."""
    normalized = pack.replace("\\", "/")
    if normalized.startswith("//"):
        return True
    return ".." in PurePosixPath(normalized).parts


def _join_index_url(index_url: str, pack: str) -> str:
    """Join a relative pack path to the directory that contains the index."""
    base = index_url if index_url.endswith("/") else index_url.rsplit("/", 1)[0] + "/"
    joined = urljoin(base, pack.replace("\\", "/"))
    base_parts = urlparse(base)
    joined_parts = urlparse(joined)
    base_path = base_parts.path if base_parts.path.endswith("/") else base_parts.path + "/"
    joined_path = unquote(joined_parts.path)
    same_origin = (
        joined_parts.scheme in {"https", "http"}
        and joined_parts.netloc == base_parts.netloc
        and joined_path.startswith(base_path)
        and ".." not in PurePosixPath(joined_path).parts
    )
    if not same_origin:
        raise PackError("pack path escapes the index")
    return joined


def _index_dir(index_url: str) -> Path:
    if index_url.startswith("file:"):
        return _file_url_path(index_url).parent
    return Path(index_url).parent


def _under_index_dir(index_url: str, pack: str) -> Path | None:
    root = _index_dir(index_url).resolve()
    candidate = (root / pack).resolve()
    if candidate.is_file() and candidate.is_relative_to(root):
        return candidate
    return None


def _download(url: str) -> Path:
    target = Path(tempfile.mkdtemp(prefix="self-nomad-hub-")) / "download.snpack"
    if url.startswith("file:"):
        target.write_bytes(_file_url_path(url).read_bytes())
        return target
    with urlopen(url, timeout=60) as response, target.open("wb") as handle:  # noqa: S310
        handle.write(response.read())
    return target


def _read_text(url: str) -> str:
    if url.startswith("file:"):
        return _file_url_path(url).read_text(encoding="utf-8")
    with urlopen(url, timeout=60) as response:  # noqa: S310
        payload = bytes(response.read())
        return payload.decode("utf-8")


def _file_url_path(url: str) -> Path:
    return Path(unquote(urlparse(url).path))
