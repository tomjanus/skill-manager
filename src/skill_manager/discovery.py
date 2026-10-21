"""Discovery of skills in the source directory and content hashing."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

SKILL_FILE_NAME = "SKILL.md"
FRONTMATTER_DELIMITER = "---"


@dataclass(frozen=True)
class Skill:
    """A discovered skill in the source directory."""

    name: str
    description: str
    path: Path


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


def discover_skills(skills_dir: Path) -> list[Skill]:
    """Return all valid skills directly under *skills_dir*, sorted by name.

    Only top-level directories containing a ``SKILL.md`` are considered.
    Hidden directories and non-directories are ignored.
    """
    if not skills_dir.is_dir():
        return []
    skills: list[Skill] = []
    for entry in sorted(skills_dir.iterdir(), key=lambda p: p.name):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        skill = read_skill(entry)
        if skill is not None:
            skills.append(skill)
    return skills


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
