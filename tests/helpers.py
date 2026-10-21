"""Shared helpers for the skill-manager test suite."""

from __future__ import annotations

from pathlib import Path

from skill_manager.ui import FakeUI


def write_skill(
    root: Path,
    name: str,
    description: str = "A test skill.",
    body: str = "# Body\n",
    extra_files: dict[str, str] | None = None,
) -> Path:
    """Create a skill directory with a ``SKILL.md`` and optional extra files."""
    skill_dir = Path(root) / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    frontmatter = f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n"
    (skill_dir / "SKILL.md").write_text(frontmatter, encoding="utf-8")
    for relative, content in (extra_files or {}).items():
        target = skill_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return skill_dir


def init_git(root: Path) -> None:
    """Create a ``.git`` directory so *root* looks like a git worktree."""
    (Path(root) / ".git").mkdir(parents=True, exist_ok=True)


def make_ui(confirm_answer: bool = True, chosen: list[int] | None = None) -> FakeUI:
    return FakeUI(confirm_answer=confirm_answer, chosen=chosen)
