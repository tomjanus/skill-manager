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


class LinkError(RuntimeError):
    """Raised when a link or junction could not be created."""


def target_exists(path: Path) -> bool:
    """Return ``True`` when *path* exists, including broken links."""
    return path.exists() or path.is_symlink()


def is_broken_link(path: Path) -> bool:
    """Return ``True`` when *path* is a link whose target is missing."""
    return path.is_symlink() and not path.exists()


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
    """Remove a link, file, or directory tree at *path*."""
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
