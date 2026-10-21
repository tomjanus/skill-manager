"""Filesystem primitives for linking and copying skills.

Symlinking is preferred, but on Windows ``os.symlink`` for a directory
requires either Administrator rights or Developer Mode. When that fails we
fall back to a directory *junction* (``mklink /J``), which needs neither.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

FILE_ATTRIBUTE_REPARSE_POINT = 0x400
IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003


class LinkError(RuntimeError):
    """Raised when a link or junction could not be created."""


def is_link(path: Path) -> bool:
    """Return ``True`` when *path* is a symbolic link or a Windows junction.

    ``Path.is_symlink()`` reports junctions as ``False``, so every place
    that has to know whether a target is a link must use this helper.
    """
    if path.is_symlink():
        return True
    if os.name != "nt":
        return False
    try:
        info = path.lstat()
    except OSError:
        return False
    attributes = int(getattr(info, "st_file_attributes", 0) or 0)
    if not attributes & FILE_ATTRIBUTE_REPARSE_POINT:
        return False
    tag = int(getattr(info, "st_reparse_tag", 0) or 0)
    return tag == IO_REPARSE_TAG_MOUNT_POINT


def target_exists(path: Path) -> bool:
    """Return ``True`` when *path* exists, including broken links."""
    return path.exists() or is_link(path)


def is_broken_link(path: Path) -> bool:
    """Return ``True`` when *path* is a link whose target is missing."""
    return is_link(path) and not path.exists()


def _create_junction(src: Path, dst: Path) -> None:
    """Create a Windows directory junction from *dst* to *src*."""
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(dst), str(src)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise LinkError(
            f"Could not create junction {dst} -> {src}: {result.stderr.strip()}"
        )


def link(src: Path, dst: Path) -> None:
    """Create a link at *dst* pointing to *src*.

    Uses a symbolic link when possible and falls back to a Windows junction.
    """
    try:
        os.symlink(src, dst, target_is_directory=src.is_dir())
    except OSError:
        if sys.platform == "win32":
            _create_junction(src.resolve(), dst)
            return
        raise LinkError(f"Could not create symlink {dst} -> {src}") from None


def copy_tree(src: Path, dst: Path) -> None:
    """Recursively copy the directory *src* to *dst*."""
    shutil.copytree(src, dst)


def remove_target(path: Path) -> None:
    """Remove a link, file, or directory tree at *path*.

    Links (symbolic links and Windows junctions) are unlinked rather than
    deleted recursively, so the skill source they point at is never touched.
    """
    if is_link(path) or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
