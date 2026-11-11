"""Discovery of skills in the source directory and content hashing."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

SKILL_FILE_NAME = "SKILL.md"
FRONTMATTER_DELIMITER = "---"


@dataclass(frozen=True)
class Skill:
    """A discovered skill in the source directory."""

    name: str
    description: str
    path: Path


@dataclass(frozen=True)
class DuplicateInfo:
    """Information about a skill name found at multiple paths.

    The *chosen* path is the newest one (by ``SKILL.md`` mtime); the
    *duplicates* are the other paths that were ignored.
    """

    name: str
    chosen: Path
    duplicates: list[Path] = field(default_factory=list)


@dataclass(frozen=True)
class Bundle:
    """A collection of skills under a single folder.

    A bundle is *not* itself a skill: its folder has no ``SKILL.md``. Its
    members are the discoverable skills beneath it (transitively).
    """

    name: str
    path: Path
    skills: tuple[Skill, ...] = ()


def parse_frontmatter(text: str) -> dict[str, str]:
    """Parse a minimal YAML frontmatter block from *text*.

    Only the simple ``key: value`` form is supported, which is all the
    Agent Skills spec requires for ``name`` and ``description``. Surrounding
    single or double quotes are stripped. Returns an empty mapping when no
    frontmatter block is present.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return {}

    metadata: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == FRONTMATTER_DELIMITER:
            break
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if not separator:
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            metadata[key] = value
    return metadata


def read_skill(skill_dir: Path) -> Skill | None:
    """Read a skill directory into a :class:`Skill`.

    Returns ``None`` when the directory does not contain a ``SKILL.md``
    file. The displayed name comes from the frontmatter ``name`` field,
    falling back to the directory name.
    """
    skill_file = skill_dir / SKILL_FILE_NAME
    if not skill_file.is_file():
        return None
    try:
        text = skill_file.read_text(encoding="utf-8")
    except OSError:
        return None
    metadata = parse_frontmatter(text)
    name = metadata.get("name") or skill_dir.name
    return Skill(name=name, description=metadata.get("description", ""), path=skill_dir)


def _skill_mtime(skill_dir: Path) -> float:
    """Return the mtime of the ``SKILL.md`` file in *skill_dir*."""
    skill_file = skill_dir / SKILL_FILE_NAME
    try:
        return skill_file.stat().st_mtime
    except OSError:
        return 0.0


def _collect_skills(
    skills_dir: Path, visited: set[str] | None = None
) -> list[tuple[Skill, float]]:
    """Recursively collect every skill under *skills_dir*.

    Follows directory symlinks and Windows junctions. Hidden directories
    (names starting with ``.``) are skipped. *visited* holds the realpaths
    of directories already walked, preventing infinite loops on cyclic
    symlinks. Returns a list of ``(Skill, mtime)`` pairs, one per
    ``SKILL.md`` found (duplicates by name are not yet removed).
    """
    if visited is None:
        visited = set()

    try:
        real = os.path.realpath(skills_dir)
    except OSError:
        return []
    if real in visited:
        return []
    visited.add(real)

    collected: list[tuple[Skill, float]] = []
    try:
        entries = sorted(skills_dir.iterdir(), key=lambda p: p.name)
    except OSError:
        return collected

    for entry in entries:
        if entry.name.startswith("."):
            continue
        try:
            if not entry.is_dir():
                continue
        except OSError:
            continue

        skill = read_skill(entry)
        if skill is not None:
            collected.append((skill, _skill_mtime(entry)))

        collected.extend(_collect_skills(entry, visited))

    return collected


def _deduplicate(
    skills_with_mtime: list[tuple[Skill, float]],
) -> tuple[list[Skill], list[DuplicateInfo]]:
    """Deduplicate skills by name, keeping the newest by ``SKILL.md`` mtime.

    Returns ``(deduped_skills, duplicates)`` sorted by skill name. When the
    same name appears at multiple paths, the newest ``SKILL.md`` wins and the
    others are recorded in :class:`DuplicateInfo`.
    """
    by_name: dict[str, list[tuple[Skill, float]]] = {}
    for skill, mtime in skills_with_mtime:
        by_name.setdefault(skill.name, []).append((skill, mtime))

    deduped: list[Skill] = []
    duplicates: list[DuplicateInfo] = []
    for name, entries in by_name.items():
        entries.sort(key=lambda item: item[1], reverse=True)
        chosen_skill, _chosen_mtime = entries[0]
        deduped.append(chosen_skill)
        if len(entries) > 1:
            dup_paths = [entry[0].path for entry in entries[1:]]
            duplicates.append(
                DuplicateInfo(name=name, chosen=chosen_skill.path, duplicates=dup_paths)
            )

    deduped.sort(key=lambda skill: skill.name)
    return deduped, duplicates


def discover_skills(skills_dir: Path) -> list[Skill]:
    """Return all valid skills under *skills_dir*, sorted by name.

    Walks nested folders, follows directory symlinks and Windows junctions,
    skips hidden directories, and guards against symlink cycles. Skill names
    come from the frontmatter ``name`` field (falling back to the directory
    name). When a name is defined multiple times, the newest ``SKILL.md``
    (by mtime) wins.
    """
    if not skills_dir.is_dir():
        return []
    collected = _collect_skills(skills_dir)
    deduped, _duplicates = _deduplicate(collected)
    return deduped


def discover_skills_with_duplicates(
    skills_dir: Path,
) -> tuple[list[Skill], list[DuplicateInfo]]:
    """Return deduped skills plus duplicate info for verbose reporting.

    Like :func:`discover_skills` but also returns every skill name found at
    multiple paths, with the newest path chosen and the rest listed as
    duplicates. Used when ``--verbose`` is given.
    """
    if not skills_dir.is_dir():
        return [], []
    collected = _collect_skills(skills_dir)
    return _deduplicate(collected)


def discover_bundles(skills_dir: Path) -> list[Bundle]:
    """Return the bundle folders under *skills_dir*.

    A folder is a bundle when it has no ``SKILL.md`` at its root and contains
    at least two distinct discoverable skill names beneath it (transitively). Only the
    highest-level qualifying folder is returned, so bundles never nest. The
    skills directory root itself is never a bundle, and a folder with a
    ``SKILL.md`` is always an individual skill, never a bundle.
    """
    if not skills_dir.is_dir():
        return []
    collected = _collect_skills(skills_dir)

    candidates: set[Path] = set()
    for skill, _ in collected:
        for ancestor in skill.path.parents:
            # Only consider folders strictly beneath the skills dir; the
            # skills dir itself and anything above it can never be a bundle.
            if skills_dir not in ancestor.parents:
                continue
            if not ancestor.is_dir():
                continue
            if (ancestor / SKILL_FILE_NAME).is_file():
                continue
            member_names = {
                skill.name for skill, _ in collected if ancestor in skill.path.parents
            }
            if len(member_names) >= 2:
                candidates.add(ancestor)

    # Keep only maximal candidates (not strictly contained in another),
    # so bundles never nest.
    maximal = [
        cand
        for cand in candidates
        if not any(other != cand and other in cand.parents for other in candidates)
    ]

    # De-duplicate bundles that resolve to the same real directory (symlinks).
    seen: set[str] = set()
    bundles: list[Bundle] = []
    for cand in sorted(maximal, key=lambda p: p.name):
        try:
            real = os.path.realpath(cand)
        except OSError:
            continue
        if real in seen:
            continue
        seen.add(real)
        member_skills = tuple(
            skill for skill, _ in collected if cand in skill.path.parents
        )
        bundles.append(Bundle(name=cand.name, path=cand, skills=member_skills))

    bundles.sort(key=lambda b: b.name)
    return bundles


def discover_all_candidates(
    skills_dir: Path,
) -> dict[str, list[Skill]]:
    """Return every discoverable skill grouped by name, without dedup.

    When a name is defined at multiple source paths, every candidate is
    listed so the caller can let the user choose which source to install.
    """
    if not skills_dir.is_dir():
        return {}
    collected = _collect_skills(skills_dir)
    by_name: dict[str, list[Skill]] = {}
    for skill, _ in collected:
        by_name.setdefault(skill.name, []).append(skill)
    for name in by_name:
        by_name[name].sort(key=lambda skill: skill.path.as_posix())
    return dict(sorted(by_name.items()))


def content_hash(path: Path) -> str:
    """Return a stable SHA-256 hash of the file tree rooted at *path*.

    The hash covers each file's relative POSIX path and bytes, sorted by
    path, so it is independent of filesystem ordering and mtime.
    """
    digest = hashlib.sha256()
    if not path.exists():
        return digest.hexdigest()

    files = sorted(
        (p for p in path.rglob("*") if p.is_file()),
        key=lambda p: p.relative_to(path).as_posix(),
    )
    for file_path in files:
        relative = file_path.relative_to(path).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        try:
            digest.update(file_path.read_bytes())
        except OSError:
            digest.update(b"<unreadable>")
        digest.update(b"\0")
    return digest.hexdigest()
