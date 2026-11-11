"""Core operations: init, list, add, remove, and sync."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import config, manifest
from .discovery import (
    Bundle,
    Skill,
    _skill_mtime,
    content_hash,
    discover_all_candidates,
    discover_bundles,
    discover_skills,
    discover_skills_with_duplicates,
)
from .platform import LinkError, copy_tree, is_link, link, remove_target, target_exists
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
STATUS_PARTIAL = "partial"


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


@dataclass(frozen=True)
class SkillTreeNode:
    """A :class:`SkillView` nested with its child skill views."""

    view: SkillView
    children: tuple[SkillTreeNode, ...] = ()


@dataclass(frozen=True)
class AddIntent:
    """A selection made in the interactive ``add`` picker."""

    kind: str  # "bundle" -> install all members; "skill" -> install one skill
    name: str


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
        self._bundles: list[Bundle] = []
        self._bundles_by_name: dict[str, Bundle] = {}
        self._skill_to_bundle: dict[str, list[str]] = {}
        self._candidates: dict[str, list[Skill]] = {}

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
            "'simple-skill-manager add' inside a project."
        )

    # ------------------------------------------------------------------
    # list
    # ------------------------------------------------------------------
    def list_views(self, verbose: bool = False) -> list[SkillView]:
        """Return merged skill views sorted by name."""
        views, _ = self.list_data(verbose)
        return views

    def list_data(
        self, verbose: bool = False
    ) -> tuple[list[SkillView], list[SkillTreeNode]]:
        """Return flat views and bundle tree roots, warning duplicates once.

        The flat views are used for ``--available``/``--installed``/``--json``
        (they stay flat). The tree roots are used for the default ``list``
        rendering, which shows bundles as header rows with members nested
        underneath.
        """
        available, targets, data = self._sources(verbose)
        names = set(available) | set(targets) | set(data.get("skills", {}))
        views = [self._view(name, available, targets, data) for name in sorted(names)]

        bundles = discover_bundles(self.skills_dir)
        tree_roots: list[SkillTreeNode] = []
        represented_names: set[str] = set()
        for bundle in bundles:
            members = sorted(
                (
                    skill
                    for skill in available.values()
                    if bundle.path in skill.path.parents
                ),
                key=lambda skill: skill.name,
            )
            if not members:
                continue
            tree_roots.append(self._attach_bundle(bundle, members, targets, data))
            represented_names.update(skill.name for skill in members)

        tree_roots.extend(
            SkillTreeNode(view=view)
            for view in views
            if view.name not in represented_names
        )
        tree_roots.sort(key=lambda node: node.view.name)
        return views, tree_roots

    def _sources(
        self, verbose: bool = False
    ) -> tuple[dict[str, Skill], dict[str, TargetInfo], dict[str, Any]]:
        """Resolve available skills, targets and manifest, warning on duplicates."""
        if verbose:
            available_map, duplicates = discover_skills_with_duplicates(self.skills_dir)
            available = {skill.name: skill for skill in available_map}
            for dup in duplicates:
                ignored = ", ".join(str(p) for p in dup.duplicates)
                self.ui.warn(
                    f"Skill '{dup.name}' is defined multiple times; using the "
                    f"newest source '{dup.chosen}' and ignoring '{ignored}'."
                )
        else:
            available = {
                skill.name: skill for skill in discover_skills(self.skills_dir)
            }
        targets = scan_target(self.target_dir)
        data = manifest.load_manifest(self.manifest_path)
        return available, targets, data

    def _view(
        self,
        name: str,
        available: dict[str, Skill],
        targets: dict[str, TargetInfo],
        data: dict[str, Any],
    ) -> SkillView:
        skill = available.get(name)
        target = targets.get(name)
        entry = manifest.get_entry(data, name)
        managed = entry is not None
        mode = entry.get("mode") if entry else (target.mode if target else None)
        return SkillView(
            name=name,
            description=skill.description if skill else "",
            status=_status(skill, target, entry),
            mode=mode,
            managed=managed,
            source_path=skill.path if skill else None,
            target_path=target.path if target else None,
        )

    def _attach_bundle(
        self,
        bundle: Bundle,
        skills: list[Skill],
        targets: dict[str, TargetInfo],
        data: dict[str, Any],
    ) -> SkillTreeNode:
        """Attach a bundle's member skills as nested views."""
        member_nodes: list[SkillTreeNode] = []
        for skill in skills:
            target = targets.get(skill.name)
            entry = manifest.get_entry(data, skill.name)
            managed = entry is not None
            mode = entry.get("mode") if entry else (target.mode if target else None)
            view = SkillView(
                name=skill.name,
                description=skill.description,
                status=_status(skill, target, entry),
                mode=mode,
                managed=managed,
                source_path=skill.path,
                target_path=target.path if target else None,
            )
            member_nodes.append(SkillTreeNode(view=view, children=()))

        child_statuses = [node.view.status for node in member_nodes]
        bundle_managed = bool(member_nodes) and all(
            node.view.managed for node in member_nodes
        )
        bundle_view = SkillView(
            name=bundle.name,
            description=f"bundle of {len(member_nodes)} skill(s)",
            status=_bundle_status(child_statuses),
            mode=None,
            managed=bundle_managed,
            source_path=bundle.path,
            target_path=None,
        )
        return SkillTreeNode(view=bundle_view, children=tuple(member_nodes))

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
        verbose: bool = False,
    ) -> bool:
        """Add skills to the project, linking or copying them.

        Installing a *bundle* installs every member skill under its own name.
        When a skill name exists at multiple source paths, the user is asked
        which source to install (interactive only; otherwise the newest
        ``SKILL.md`` wins).

        Returns ``True`` when every requested skill ended up installed (or
        was already up to date).
        """
        bundles = discover_bundles(self.skills_dir)
        bundles_by_name = {bundle.name: bundle for bundle in bundles}
        candidates = discover_all_candidates(self.skills_dir)
        skill_to_bundle: dict[str, list[str]] = {}
        for bundle in bundles:
            for skill in bundle.skills:
                bundle_names = skill_to_bundle.setdefault(skill.name, [])
                if bundle.name not in bundle_names:
                    bundle_names.append(bundle.name)
        self._bundles = bundles
        self._bundles_by_name = bundles_by_name
        self._skill_to_bundle = skill_to_bundle
        self._candidates = candidates
        if verbose:
            _, duplicates = discover_skills_with_duplicates(self.skills_dir)
            for dup in duplicates:
                ignored = ", ".join(str(p) for p in dup.duplicates)
                self.ui.warn(
                    f"Skill '{dup.name}' is defined multiple times; newest source "
                    f"default is '{dup.chosen}', with other candidates at '{ignored}'."
                )
        if not candidates:
            self.ui.warn(f"No skills found in {self.skills_dir}.")
            return False

        all_names = set(candidates) | set(bundles_by_name)
        selected_bundle_names: list[str] = []
        requested_skill_names: list[str] = []
        input_ok = True
        if not names:
            if not interactive:
                self.ui.error("No skill names given.")
                return False
            chosen = self._interactive_pick(bundles, candidates)
            selected_bundle_names = [
                intent.name for intent in chosen if intent.kind == "bundle"
            ]
            for intent in chosen:
                if intent.kind == "bundle":
                    requested_skill_names.extend(
                        member.name for member in bundles_by_name[intent.name].skills
                    )
                else:
                    requested_skill_names.append(intent.name)
            if not requested_skill_names:
                self.ui.info("No skills selected.")
                return True
        else:
            unknown = [name for name in names if name not in all_names]
            for name in unknown:
                self.ui.error(f"Unknown skill '{name}'.")
            input_ok = not unknown
            names = [name for name in names if name in all_names]
            ambiguous = [
                name for name in names if name in bundles_by_name and name in candidates
            ]
            for name in ambiguous:
                self.ui.error(
                    f"'{name}' names both a bundle and a skill; use the interactive "
                    "picker to choose explicitly."
                )
            input_ok = input_ok and not ambiguous
            names = [name for name in names if name not in ambiguous]
            for name in names:
                if name in bundles_by_name:
                    selected_bundle_names.append(name)
                    requested_skill_names.extend(
                        member.name for member in bundles_by_name[name].skills
                    )
                else:
                    requested_skill_names.append(name)

            if not requested_skill_names:
                return False

        selected_bundle_names = list(dict.fromkeys(selected_bundle_names))

        unique_skill_names = list(dict.fromkeys(requested_skill_names))
        install_intents: dict[str, Skill] = {}
        resolution_ok = True
        for name in unique_skill_names:
            chosen_skill = self._choose_source(name, candidates, interactive)
            if chosen_skill is None:
                resolution_ok = False
            else:
                install_intents[name] = chosen_skill

        data = manifest.load_manifest(self.manifest_path)
        changed = False
        ok = resolution_ok and input_ok
        installed_ok: dict[str, bool] = {}
        for name, skill in install_intents.items():
            one_changed, one_ok = self._install_one(name, skill, mode, force, yes, data)
            changed = changed or one_changed
            ok = ok and one_ok
            installed_ok[name] = one_ok

        for bundle_name in selected_bundle_names:
            member_names = {
                member.name for member in bundles_by_name[bundle_name].skills
            }
            ready = sum(installed_ok.get(name, False) for name in member_names)
            self.ui.info(
                f"Bundle '{bundle_name}': {ready}/{len(member_names)} skills ready."
            )

        if changed:
            manifest.save_manifest(self.manifest_path, data)
        return ok

    def _interactive_pick(
        self, bundles: list[Bundle], candidates: dict[str, list[Skill]]
    ) -> list[AddIntent]:
        """Let the user pick bundles (all members) and/or individual skills."""
        choices: list[AddIntent] = []
        for bundle in sorted(bundles, key=lambda b: b.name):
            choices.append(AddIntent(kind="bundle", name=bundle.name))
        for name in sorted(candidates):
            choices.append(AddIntent(kind="skill", name=name))

        chosen = self.ui.choose_many(choices, self._render_intent)
        return list(chosen)

    def _choose_source(
        self,
        name: str,
        candidates: dict[str, list[Skill]],
        interactive: bool,
    ) -> Skill | None:
        """Pick the source to install for *name*.

        With a single candidate it is returned directly. With several
        candidates (the same name in multiple bundles/locations) the user is
        prompted interactively, defaulting to the newest ``SKILL.md``. In
        non-interactive mode, duplicate source choices are an error rather than
        an implicit selection.
        """
        options = candidates[name]
        if len(options) == 1:
            return options[0]
        ordered = sorted(
            options, key=lambda skill: _skill_mtime(skill.path), reverse=True
        )
        if not interactive:
            self.ui.error(
                f"Skill '{name}' has multiple sources; rerun add in an "
                "interactive terminal to choose one."
            )
            return None
        chosen = self.ui.choose_one(
            f"Skill '{name}' is defined at multiple sources. "
            "Choose which source to install:",
            ordered,
            self._render_source_choice,
            default=0,
        )
        if chosen is None:
            self.ui.warn(f"Source selection cancelled for skill '{name}'.")
        return chosen

    def _render_intent(self, index: int, intent: AddIntent) -> str:
        if intent.kind == "bundle":
            bundle = self._bundles_by_name[intent.name]
            member_count = len({skill.name for skill in bundle.skills})
            return f"📦 {intent.name:<24} (bundle, {member_count} skill(s))"
        member_bundles = self._skill_to_bundle.get(intent.name, [])
        bundle_label = ", ".join(member_bundles)
        tag = f"  [{bundle_label}]" if bundle_label else ""
        candidates = sorted(
            self._candidates[intent.name],
            key=lambda skill: _skill_mtime(skill.path),
            reverse=True,
        )
        return f"{intent.name:<24} {candidates[0].description}{tag}"

    def _render_source_choice(self, index: int, skill: Skill) -> str:
        bundle = self._bundle_of_path(skill.path)
        tag = f"  [{bundle}]" if bundle else ""
        return f"{skill.name:<24} {skill.description}{tag}"

    def _bundle_of_path(self, path: Path) -> str | None:
        for bundle in self._bundles:
            if bundle.path in path.parents:
                return bundle.name
        return None

    def _install_one(
        self,
        name: str,
        skill: Skill,
        mode: str,
        force: bool,
        yes: bool,
        data: dict[str, Any],
    ) -> tuple[bool, bool]:
        """Install a single skill. Returns ``(changed, ok)``."""
        target = self.target_dir / name
        entry = manifest.get_entry(data, name)

        if target_exists(target):
            if entry is None:
                if not force:
                    self.ui.warn(
                        f"'{name}' already exists in the project and is not "
                        "managed by skill-manager; use --force to replace."
                    )
                    return False, False
            elif self._is_current(skill, target, entry, mode):
                self.ui.info(f"'{name}' is already up to date.")
                return False, True
            elif (
                not force
                and not yes
                and not self.ui.confirm(f"Update '{name}' in the project?")
            ):
                return False, False

        try:
            self._install(skill, target, mode)
        except LinkError as exc:
            self.ui.error(str(exc))
            self.ui.error("Hint: use --copy to copy instead of linking.")
            return False, False
        manifest.set_entry(data, name, mode, content_hash(skill.path))
        changed = True
        self.ui.info(f"Added '{name}' ({mode}).")
        return changed, True

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
                if self._link_matches_skill(target, skill):
                    self.ui.info(f"'{name}' is up to date.")
                    continue
                self._install(skill, target, mode)
                manifest.set_entry(data, name, mode, content_hash(skill.path))
                changed = True
                self.ui.info(f"Restored '{name}' (link).")
                continue

            # Copy mode.
            if not target_exists(target) or is_link(target):
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
            if is_link(target) or not target.is_dir():
                return False
            recorded = entry.get("hash")
            return (
                content_hash(skill.path) == recorded
                and content_hash(target) == recorded
            )
        return self._link_matches_skill(target, skill)

    @staticmethod
    def _link_matches_skill(target: Path, skill: Skill) -> bool:
        """Return whether *target* links to the selected skill source."""
        if not is_link(target) or not target.exists():
            return False
        try:
            return target.resolve() == skill.path.resolve()
        except (OSError, RuntimeError):
            return False


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
    try:
        if target.path.resolve() != skill.path.resolve():
            return STATUS_OUTDATED
    except (OSError, RuntimeError):
        return STATUS_OUTDATED
    return STATUS_INSTALLED


def _bundle_status(child_statuses: list[str]) -> str:
    """Aggregate the statuses of a bundle's members into a bundle status."""
    if any(status == STATUS_BROKEN for status in child_statuses):
        return STATUS_BROKEN
    if any(status == STATUS_OUTDATED for status in child_statuses):
        return STATUS_OUTDATED
    installed = sum(1 for status in child_statuses if status == STATUS_INSTALLED)
    total = len(child_statuses)
    if installed == total:
        return STATUS_INSTALLED
    if installed > 0:
        return STATUS_PARTIAL
    return STATUS_NOT_INSTALLED


__all__ = [
    "Manager",
    "SkillView",
    "SkillTreeNode",
    "AddIntent",
    "Bundle",
    "STATUS_INSTALLED",
    "STATUS_OUTDATED",
    "STATUS_BROKEN",
    "STATUS_MISSING",
    "STATUS_MISSING_SOURCE",
    "STATUS_NOT_INSTALLED",
    "STATUS_EXTERNAL",
    "STATUS_PARTIAL",
]
