"""Project-level helpers: locating the project root and scanning targets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .platform import is_link


def find_project_root(start: Path, override: Path | None = None) -> Path:
    """Return the project root for *start*.

    An explicit *override* wins. Otherwise the nearest enclosing git
    worktree is used (``.git`` may be a directory or a file, as in linked
    worktrees). When no git repository is found, *start* is returned.
    """
    if override is not None:
        return override.resolve()

    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists():
            return candidate
    return current


@dataclass(frozen=True)
class TargetInfo:
    """A directory entry found in the project's target skills folder."""

    name: str
    path: Path
    is_link: bool
    exists: bool

    @property
    def mode(self) -> str | None:
        """Return ``"link"``/``"copy"`` based on the filesystem, else ``None``."""
        if self.is_link:
            return "link"
        if self.exists:
            return "copy"
        return None

    @property
    def is_broken_link(self) -> bool:
        return self.is_link and not self.exists


def scan_target(target_dir: Path) -> dict[str, TargetInfo]:
    """Return a mapping of skill name to :class:`TargetInfo` for *target_dir*.

    Only directories and links (symbolic links or Windows junctions) are
    considered; loose files such as opencode's ``skills-lock.json`` are
    ignored.
    """
    targets: dict[str, TargetInfo] = {}
    if not target_dir.is_dir():
        return targets
    for entry in sorted(target_dir.iterdir(), key=lambda p: p.name):
        if entry.name.startswith("."):
            continue
        if is_link(entry):
            targets[entry.name] = TargetInfo(
                name=entry.name, path=entry, is_link=True, exists=entry.exists()
            )
        elif entry.is_dir():
            targets[entry.name] = TargetInfo(
                name=entry.name, path=entry, is_link=False, exists=True
            )
    return targets
