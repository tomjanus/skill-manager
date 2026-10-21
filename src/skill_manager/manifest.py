"""The per-project manifest that records which skills are selected.

The manifest lives at the project root as ``.skill-manager.json`` and is
intended to be committed, so a project's skill selection is reproducible on
another machine via ``skill-manager sync``.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

MANIFEST_FILE_NAME = ".skill-manager.json"
MANIFEST_VERSION = 1
MODE_LINK = "link"
MODE_COPY = "copy"


class ManifestError(RuntimeError):
    """Raised when the manifest cannot be read or parsed."""


def manifest_path(project_root: Path) -> Path:
    """Return the manifest path for *project_root*."""
    return project_root / MANIFEST_FILE_NAME


def empty_manifest() -> dict[str, Any]:
    """Return a fresh, empty manifest."""
    return {"version": MANIFEST_VERSION, "skills": {}}


def load_manifest(path: Path) -> dict[str, Any]:
    """Load the manifest at *path*, returning an empty manifest if absent.

    Raises :class:`ManifestError` when the file exists but is not valid
    JSON or does not have the expected shape.
    """
    if not path.is_file():
        return empty_manifest()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"Could not read manifest {path}: {exc}") from exc

    if not isinstance(data, dict) or not isinstance(data.get("skills"), dict):
        raise ManifestError(
            f"Manifest {path} is malformed; expected an object with a 'skills' map."
        )
    data.setdefault("version", MANIFEST_VERSION)
    return data


def save_manifest(path: Path, data: dict[str, Any]) -> None:
    """Atomically write *data* to *path* as JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temp_name)
        raise


def get_entry(data: dict[str, Any], name: str) -> dict[str, Any] | None:
    """Return the manifest entry for *name*, or ``None``."""
    entry = data.get("skills", {}).get(name)
    return entry if isinstance(entry, dict) else None


def set_entry(data: dict[str, Any], name: str, mode: str, content_hash: str) -> None:
    """Record *name* in the manifest with its mode and content hash."""
    data.setdefault("skills", {})[name] = {"mode": mode, "hash": content_hash}


def remove_entry(data: dict[str, Any], name: str) -> bool:
    """Remove *name* from the manifest. Returns ``True`` if it was present."""
    skills = data.setdefault("skills", {})
    if name in skills:
        del skills[name]
        return True
    return False
