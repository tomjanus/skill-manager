"""Core operations: init, list, add, remove, and sync."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import config, manifest
from .discovery import Skill, content_hash, discover_skills
from .platform import LinkError, copy_tree, link, remove_target, target_exists
from .project import TargetInfo, scan_target
from .ui import UI

STAGING_SUFFIX = ".skill-manager-staging"
STATUS_INSTALLED = "installed"
STATUS_OUTDATED = "outdated"
STATUS_BROKEN = "broken"
STATUS_MISSING = "missing"
STATUS_MISSING_SOURCE = "missing-source"
STATUS_NOT_INSTALLED = "not-installed"
STATUS_EXTERNAL = "external"


@dataclass(frozen=True)
class SkillView:
    """A merged view of a skill across source, target, and manifest."""

    name: str
    description: str
    status: str
    mode: str | None
    managed: bool
    source_path: Path | None
    target_path: Path | None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "mode": self.mode,
            "managed": self.managed,
            "source": str(self.source_path) if self.source_path else None,
            "target": str(self.target_path) if self.target_path else None,
        }


class Manager:
    """Performs skill operations for one project."""

    def __init__(
        self,
        project_root: Path,
        skills_dir: Path,
        target_dir: Path,
        env_file: Path,
        ui: UI,
    ) -> None:
        self.project_root = project_root
        self.skills_dir = skills_dir
        self.target_dir = target_dir
        self.env_file = env_file
        self.ui = ui
        self.manifest_path = manifest.manifest_path(project_root)

    # ------------------------------------------------------------------
    # init
    # ------------------------------------------------------------------
    def init(self) -> None:
        """Create the configuration file and source directory if missing."""
        skills_dir = self.skills_dir
        created_config = config.write_default_env_file(self.env_file, skills_dir)
        if not skills_dir.exists():
            skills_dir.mkdir(parents=True, exist_ok=True)
            self.ui.info(f"Created source skills directory: {skills_dir}")
        else:
            self.ui.info(f"Source skills directory: {skills_dir}")
        if created_config:
            self.ui.info(f"Created configuration file: {self.env_file}")
        else:
            self.ui.info(f"Configuration file: {self.env_file}")
        self.ui.info(
            "Done. Add skills to the source directory, then run "
            "'skill-manager add' inside a project."
        )

    # ------------------------------------------------------------------
    # list
    # ------------------------------------------------------------------
    def list_views(self) -> list[SkillView]:
        """Return merged skill views sorted by name."""
        available = {skill.name: skill for skill in discover_skills(self.skills_dir)}
        targets = scan_target(self.target_dir)
        data = manifest.load_manifest(self.manifest_path)

        names = set(available) | set(targets) | set(data.get("skills", {}))
        views: list[SkillView] = []
        for name in sorted(names):
            skill = available.get(name)
            target = targets.get(name)
            entry = manifest.get_entry(data, name)
            managed = entry is not None
            mode = entry.get("mode") if entry else (target.mode if target else None)
            views.append(
                SkillView(
                    name=name,
                    description=skill.description if skill else "",
                    status=_status(skill, target, entry),
                    mode=mode,
                    managed=managed,
                    source_path=skill.path if skill else None,
                    target_path=target.path if target else None,
                )
            )
        return views

    # ------------------------------------------------------------------
    # add
    # ------------------------------------------------------------------
    def add(
        self,
        names: list[str],
        mode: str,
        force: bool,
        yes: bool,
        interactive: bool,
    ) -> bool:
        """Add skills to the project, linking or copying them.

        Returns ``True`` when every requested skill ended up installed (or
        was already up to date).
        """
        available = {skill.name: skill for skill in discover_skills(self.skills_dir)}
        if not available:
            self.ui.warn(f"No skills found in {self.skills_dir}.")
            return False

        if not names:
            if not interactive:
                self.ui.error("No skill names given.")
                return False
            items = sorted(available.values(), key=lambda s: s.name)
            chosen = self.ui.choose_many(items, self._render_choice)
            names = [skill.name for skill in chosen]
            if not names:
                self.ui.info("No skills selected.")
                return True

        unknown = [name for name in names if name not in available]
        for name in unknown:
            self.ui.error(
                f"Unknown skill '{name}'. Available: {', '.join(sorted(available))}."
            )
        names = [name for name in names if name in available]
        if not names:
            return False

        data = manifest.load_manifest(self.manifest_path)
        changed = False
        ok = True
        for name in names:
            skill = available[name]
            target = self.target_dir / name
            entry = manifest.get_entry(data, name)

            if target_exists(target):
                if entry is None:
                    if not force:
                        self.ui.warn(
                            f"'{name}' already exists in the project and is not "
                            "managed by skill-manager; use --force to replace."
                        )
                        ok = False
                        continue
                elif self._is_current(skill, target, entry, mode):
                    self.ui.info(f"'{name}' is already up to date.")
                    continue
                elif (
                    not force
                    and not yes
                    and not self.ui.confirm(f"Update '{name}' in the project?")
                ):
                    ok = False
                    continue

            try:
                self._install(skill, target, mode)
            except LinkError as exc:
                self.ui.error(str(exc))
                self.ui.error("Hint: use --copy to copy instead of linking.")
                ok = False
                continue
            manifest.set_entry(data, name, mode, content_hash(skill.path))
            changed = True
            self.ui.info(f"Added '{name}' ({mode}).")

        if changed:
            manifest.save_manifest(self.manifest_path, data)
        return ok

    # ------------------------------------------------------------------
    # remove
    # ------------------------------------------------------------------
    def remove(self, names: list[str], yes: bool, force: bool) -> bool:
        """Remove skills from the project and the manifest.

        Returns ``True`` when every requested skill was removed.
        """
        data = manifest.load_manifest(self.manifest_path)
        changed = False
        ok = True
        for name in names:
            entry = manifest.get_entry(data, name)
            target = self.target_dir / name

            if entry is None:
                if target_exists(target):
                    if not force:
                        self.ui.warn(
                            f"'{name}' is not managed by skill-manager; "
                            "use --force to remove."
                        )
                        ok = False
                        continue
                else:
                    self.ui.warn(f"'{name}' is not installed.")
                    ok = False
                    continue
            elif not target_exists(target):
                manifest.remove_entry(data, name)
                changed = True
                self.ui.info(f"Removed '{name}' from the manifest.")
                continue
            elif not yes and not self.ui.confirm(f"Remove '{name}' from the project?"):
                ok = False
                continue

            remove_target(target)
            manifest.remove_entry(data, name)
            changed = True
            self.ui.info(f"Removed '{name}'.")

        if changed:
            manifest.save_manifest(self.manifest_path, data)
        return ok

    # ------------------------------------------------------------------
    # sync
    # ------------------------------------------------------------------
    def sync(self, yes: bool, force: bool) -> bool:
        """Reconcile installed skills with their source.

        Only skills already recorded in the manifest are considered. Copies
        whose source changed are updated (with confirmation); broken links
        are re-created; skills whose source disappeared are offered for
        removal.

        Returns ``True`` when the project matches the source folder.
        """
        available = {skill.name: skill for skill in discover_skills(self.skills_dir)}
        data = manifest.load_manifest(self.manifest_path)
        changed = False
        ok = True

        for name in sorted(data.get("skills", {})):
            entry = data["skills"][name]
            mode = entry.get("mode", manifest.MODE_LINK)
            target = self.target_dir / name
            skill = available.get(name)

            if skill is None:
                if target_exists(target):
                    question = (
                        f"Source skill '{name}' is missing. Remove it from the project?"
                    )
                    if force or yes or self.ui.confirm(question):
                        remove_target(target)
                        manifest.remove_entry(data, name)
                        changed = True
                        self.ui.info(f"Removed '{name}' (source missing).")
                    else:
                        ok = False
                else:
                    manifest.remove_entry(data, name)
                    changed = True
                continue

            if mode == manifest.MODE_LINK:
                if target.is_symlink() and target.exists():
                    self.ui.info(f"'{name}' is up to date.")
                    continue
                self._install(skill, target, mode)
                manifest.set_entry(data, name, mode, content_hash(skill.path))
                changed = True
                self.ui.info(f"Restored '{name}' (link).")
                continue

            # Copy mode.
            if not target_exists(target) or target.is_symlink():
                self._install(skill, target, mode)
                manifest.set_entry(data, name, mode, content_hash(skill.path))
                changed = True
                self.ui.info(f"Restored '{name}' (copy).")
                continue

            if content_hash(skill.path) == entry.get("hash"):
                self.ui.info(f"'{name}' is up to date.")
                continue

            if (
                force
                or yes
                or self.ui.confirm(f"Update '{name}' to the latest version?")
            ):
                self._install(skill, target, mode)
                manifest.set_entry(data, name, mode, content_hash(skill.path))
                changed = True
                self.ui.info(f"Updated '{name}'.")
            else:
                self.ui.info(f"Skipped '{name}'.")
                ok = False

        if changed:
            manifest.save_manifest(self.manifest_path, data)
        return ok

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _install(self, skill: Skill, target: Path, mode: str) -> None:
        """Install *skill* at *target*, replacing whatever is there.

        The new link or copy is staged next to the target and moved into
        place only once it has been created successfully, so a failure never
        destroys an existing working copy.
        """
        self.target_dir.mkdir(parents=True, exist_ok=True)
        staging = target.with_name(f".{target.name}{STAGING_SUFFIX}")
        if target_exists(staging):
            remove_target(staging)
        try:
            if mode == manifest.MODE_COPY:
                copy_tree(skill.path, staging)
            else:
                link(skill.path, staging)
        except BaseException:
            if target_exists(staging):
                remove_target(staging)
            raise
        if target_exists(target):
            remove_target(target)
        os.replace(staging, target)

    def _is_current(
        self, skill: Skill, target: Path, entry: dict[str, Any], mode: str
    ) -> bool:
        if entry.get("mode") != mode:
            return False
        if mode == manifest.MODE_COPY:
            if target.is_symlink() or not target.is_dir():
                return False
            recorded = entry.get("hash")
            return (
                content_hash(skill.path) == recorded
                and content_hash(target) == recorded
            )
        return target.is_symlink() and target.exists()

    @staticmethod
    def _render_choice(index: int, skill: Skill) -> str:
        description = skill.description
        if len(description) > 60:
            description = description[:57] + "..."
        return f"{skill.name:<24} {description}"


def _status(
    skill: Skill | None,
    target: TargetInfo | None,
    entry: dict[str, Any] | None,
) -> str:
    if skill is None:
        if target is not None and target.exists:
            return STATUS_EXTERNAL
        return STATUS_MISSING_SOURCE
    if target is None:
        return STATUS_MISSING if entry is not None else STATUS_NOT_INSTALLED
    if entry is None:
        return STATUS_EXTERNAL
    if target.is_broken_link:
        return STATUS_BROKEN
    if entry.get("mode") == manifest.MODE_COPY:
        recorded = entry.get("hash")
        if (
            content_hash(skill.path) != recorded
            or content_hash(target.path) != recorded
        ):
            return STATUS_OUTDATED
        return STATUS_INSTALLED
    return STATUS_INSTALLED


__all__ = [
    "Manager",
    "SkillView",
    "STATUS_INSTALLED",
    "STATUS_OUTDATED",
    "STATUS_BROKEN",
    "STATUS_MISSING",
    "STATUS_MISSING_SOURCE",
    "STATUS_NOT_INSTALLED",
    "STATUS_EXTERNAL",
]
