from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skill_manager import manifest
from skill_manager.operations import (
    STATUS_EXTERNAL,
    STATUS_INSTALLED,
    STATUS_MISSING,
    STATUS_NOT_INSTALLED,
    STATUS_OUTDATED,
    STATUS_PARTIAL,
    Manager,
)
from skill_manager.platform import LinkError, is_link, remove_target
from tests.helpers import init_git, make_ui, write_skill


class ManagerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.source = self.root / "source"
        self.project = self.root / "project"
        self.source.mkdir()
        self.project.mkdir()
        init_git(self.project)
        self.env_file = self.root / "config" / ".env"
        self.env_file.parent.mkdir(parents=True)
        self.env_file.write_text(f"SKILLS_DIR={self.source}\n", encoding="utf-8")
        self.ui = make_ui()
        self.target = self.project / ".opencode" / "skills"
        self.manager = Manager(
            self.project, self.source, self.target, self.env_file, self.ui
        )

    def manifest_data(self) -> dict:
        return manifest.load_manifest(manifest.manifest_path(self.project))


class InitTests(ManagerTestCase):
    def test_creates_config_and_source_dir(self) -> None:
        self.manager.init()
        self.assertTrue(self.env_file.is_file())
        self.assertIn(
            f"SKILLS_DIR={self.source}", self.env_file.read_text(encoding="utf-8")
        )
        self.assertTrue(self.source.is_dir())


class AddTests(ManagerTestCase):
    def test_add_links_and_records_manifest(self) -> None:
        write_skill(self.source, "alpha", "Alpha skill.")
        self.manager.add(["alpha"], "link", force=False, yes=True, interactive=False)
        target = self.target / "alpha"
        self.assertTrue(is_link(target))
        entry = manifest.get_entry(self.manifest_data(), "alpha")
        self.assertEqual(entry["mode"], "link")

    def test_add_copy(self) -> None:
        write_skill(self.source, "alpha")
        self.manager.add(["alpha"], "copy", force=False, yes=True, interactive=False)
        target = self.target / "alpha"
        self.assertTrue(target.is_dir())
        self.assertFalse(is_link(target))
        self.assertEqual(
            manifest.get_entry(self.manifest_data(), "alpha")["mode"], "copy"
        )

    def test_add_is_idempotent(self) -> None:
        write_skill(self.source, "alpha")
        self.manager.add(["alpha"], "link", force=False, yes=True, interactive=False)
        self.ui.infos.clear()
        self.manager.add(["alpha"], "link", force=False, yes=True, interactive=False)
        self.assertTrue(any("up to date" in message for message in self.ui.infos))

    def test_add_unknown_name_errors(self) -> None:
        write_skill(self.source, "alpha")
        self.manager.add(["nope"], "link", force=False, yes=True, interactive=False)
        self.assertTrue(any("Unknown skill 'nope'" in e for e in self.ui.errors))

    def test_add_with_unknown_and_valid_name_returns_failure(self) -> None:
        write_skill(self.source, "alpha")
        ok = self.manager.add(
            ["nope", "alpha"], "link", force=False, yes=True, interactive=False
        )
        self.assertFalse(ok)
        self.assertTrue(is_link(self.target / "alpha"))

    def test_add_unmanaged_collision_refused_without_force(self) -> None:
        write_skill(self.source, "alpha")
        (self.target).mkdir(parents=True)
        (self.target / "alpha").mkdir()
        (self.target / "alpha" / "manual.txt").write_text("manual", encoding="utf-8")
        self.manager.add(["alpha"], "link", force=False, yes=True, interactive=False)
        self.assertFalse(is_link(self.target / "alpha"))
        self.assertTrue(any("not managed" in w for w in self.ui.warnings))

    def test_add_unmanaged_collision_replaced_with_force(self) -> None:
        write_skill(self.source, "alpha")
        (self.target).mkdir(parents=True)
        (self.target / "alpha").mkdir()
        self.manager.add(["alpha"], "link", force=True, yes=True, interactive=False)
        self.assertTrue(is_link(self.target / "alpha"))

    def test_add_updates_changed_copy(self) -> None:
        skill_dir = write_skill(self.source, "alpha", extra_files={"f.txt": "one"})
        self.manager.add(["alpha"], "copy", force=False, yes=True, interactive=False)
        (skill_dir / "f.txt").write_text("two", encoding="utf-8")
        self.manager.add(["alpha"], "copy", force=False, yes=True, interactive=False)
        self.assertEqual(
            (self.target / "alpha" / "f.txt").read_text(encoding="utf-8"), "two"
        )

    def test_failed_link_leaves_existing_copy_intact(self) -> None:
        write_skill(self.source, "alpha")
        self.manager.add(["alpha"], "copy", force=False, yes=True, interactive=False)
        original = (self.target / "alpha" / "SKILL.md").read_text(encoding="utf-8")
        with mock.patch("skill_manager.operations.link", side_effect=LinkError("boom")):
            self.manager.add(
                ["alpha"], "link", force=False, yes=True, interactive=False
            )
        self.assertTrue((self.target / "alpha").is_dir())
        self.assertFalse(is_link(self.target / "alpha"))
        self.assertEqual(
            (self.target / "alpha" / "SKILL.md").read_text(encoding="utf-8"), original
        )
        self.assertTrue(any("boom" in error for error in self.ui.errors))

    def test_leftover_staging_directory_is_ignored(self) -> None:
        write_skill(self.source, "alpha")
        self.manager.add(["alpha"], "link", force=False, yes=True, interactive=False)
        stale = self.target / ".alpha.skill-manager-staging"
        stale.mkdir()
        names = [view.name for view in self.manager.list_views()]
        self.assertEqual(names, ["alpha"])

    def test_add_verbose_warns_duplicates(self) -> None:
        write_skill(self.source, "dup", "Old description.")
        nested = self.source / "nested"
        write_skill(nested, "dup", "New description.")
        os.utime(nested / "dup" / "SKILL.md", (1_000_000_000, 1_000_000_000))
        os.utime(self.source / "dup" / "SKILL.md", (1, 1))

        self.manager.add(
            ["dup"], "link", force=False, yes=True, interactive=False, verbose=True
        )

        self.assertTrue(any("defined multiple times" in w for w in self.ui.warnings))


class BundleAddTests(ManagerTestCase):
    def _make_bundle(self, name: str, members: list[str]) -> None:
        for member in members:
            skill_dir = self.source / name / member
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(
                f"---\nname: {member}\ndescription: {member} skill.\n---\n\n",
                encoding="utf-8",
            )

    def test_add_bundle_installs_entire_subtree(self) -> None:
        self._make_bundle("collection", ["alpha", "beta"])
        self.manager.add(
            ["collection"], "link", force=False, yes=True, interactive=False
        )
        self.assertTrue(is_link(self.target / "alpha"))
        self.assertTrue(is_link(self.target / "beta"))
        self.assertEqual(
            manifest.get_entry(self.manifest_data(), "alpha")["mode"], "link"
        )
        self.assertEqual(
            manifest.get_entry(self.manifest_data(), "beta")["mode"], "link"
        )
        self.assertTrue(any("Bundle 'collection'" in line for line in self.ui.infos))

    def test_add_bundle_up_to_date_skips(self) -> None:
        self._make_bundle("collection", ["alpha", "beta"])
        self.manager.add(
            ["collection"], "link", force=False, yes=True, interactive=False
        )
        self.ui.infos.clear()
        self.manager.add(
            ["collection"], "link", force=False, yes=True, interactive=False
        )
        self.assertTrue(any("up to date" in m for m in self.ui.infos))

    def test_add_bundle_copy_mode(self) -> None:
        self._make_bundle("collection", ["alpha", "beta"])
        self.manager.add(
            ["collection"], "copy", force=False, yes=True, interactive=False
        )
        self.assertTrue((self.target / "alpha").is_dir())
        self.assertFalse(is_link(self.target / "alpha"))
        self.assertTrue((self.target / "beta").is_dir())
        self.assertFalse(is_link(self.target / "beta"))

    def test_add_skill_from_bundle_individually(self) -> None:
        self._make_bundle("collection", ["alpha", "beta"])
        self.manager.add(["alpha"], "link", force=False, yes=True, interactive=False)
        self.assertTrue(is_link(self.target / "alpha"))
        self.assertFalse((self.target / "beta").exists())

    def test_add_bundle_does_not_reinstall_member(self) -> None:
        self._make_bundle("collection", ["alpha", "beta"])
        self.manager.add(
            ["collection", "alpha"], "link", force=False, yes=True, interactive=False
        )
        self.assertTrue(is_link(self.target / "alpha"))
        self.assertTrue(is_link(self.target / "beta"))
        data = self.manifest_data()
        self.assertIsNotNone(manifest.get_entry(data, "alpha"))
        self.assertIsNotNone(manifest.get_entry(data, "beta"))

    def test_interactive_picker_can_select_bundle_or_one_member(self) -> None:
        self._make_bundle("collection", ["alpha", "beta"])
        self.manager.ui = make_ui(chosen=[0])
        self.manager.add([], "link", force=False, yes=True, interactive=True)
        self.assertTrue(is_link(self.target / "alpha"))
        self.assertTrue(is_link(self.target / "beta"))

        self.manager.remove(["alpha", "beta"], yes=True, force=False)
        self.manager.ui = make_ui(chosen=[2])
        self.manager.add([], "link", force=False, yes=True, interactive=True)
        self.assertFalse((self.target / "alpha").exists())
        self.assertTrue(is_link(self.target / "beta"))


class ConflictResolutionTests(ManagerTestCase):
    def _write_conflict_skill(self, rel: str, name: str, description: str) -> None:
        skill_dir = self.source / rel
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {description}\n---\n\n",
            encoding="utf-8",
        )

    def test_add_conflict_requires_interactive_source_choice(self) -> None:
        self._write_conflict_skill("a-bundle/dup", "dup", "From A.")
        self._write_conflict_skill("a-bundle/a-only", "a-only", "A only.")
        self._write_conflict_skill("b-bundle/dup", "dup", "From B.")
        self._write_conflict_skill("b-bundle/b-only", "b-only", "B only.")
        os.utime(
            self.source / "b-bundle" / "dup" / "SKILL.md",
            (1_000_000_000, 1_000_000_000),
        )
        os.utime(self.source / "a-bundle" / "dup" / "SKILL.md", (1, 1))
        ok = self.manager.add(["dup"], "link", force=False, yes=True, interactive=False)
        self.assertFalse(ok)
        self.assertFalse((self.target / "dup").exists())
        self.assertTrue(any("interactive terminal" in e for e in self.ui.errors))

    def test_add_conflicting_skill_prompts_interactive(self) -> None:
        self._write_conflict_skill("a-bundle/dup", "dup", "From A.")
        self._write_conflict_skill("a-bundle/a-only", "a-only", "A only.")
        self._write_conflict_skill("b-bundle/dup", "dup", "From B.")
        self._write_conflict_skill("b-bundle/b-only", "b-only", "B only.")
        os.utime(
            self.source / "a-bundle" / "dup" / "SKILL.md",
            (1_000_000_000, 1_000_000_000),
        )
        os.utime(self.source / "b-bundle" / "dup" / "SKILL.md", (1, 1))
        ui = make_ui(chosen_one=1)
        manager = Manager(self.project, self.source, self.target, self.env_file, ui)
        manager.add(["dup"], "link", force=False, yes=True, interactive=True)
        installed = (self.target / "dup" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("description: From B.", installed)
        self.assertIn("multiple sources", ui.selections[0])
        self.assertEqual(len(ui.selection_choices[0]), 2)
        self.assertTrue(any("From A." in option for option in ui.selection_choices[0]))
        self.assertTrue(any("From B." in option for option in ui.selection_choices[0]))
        self.assertTrue(
            any("[a-bundle]" in option for option in ui.selection_choices[0])
        )
        self.assertTrue(
            any("[b-bundle]" in option for option in ui.selection_choices[0])
        )

    def test_cancelled_source_choice_does_not_install_default(self) -> None:
        self._write_conflict_skill("a/dup", "dup", "From A.")
        self._write_conflict_skill("b/dup", "dup", "From B.")
        with mock.patch.object(self.manager.ui, "choose_one", return_value=None):
            ok = self.manager.add(
                ["dup"], "link", force=False, yes=True, interactive=True
            )
        self.assertFalse(ok)
        self.assertFalse((self.target / "dup").exists())


class ListTreeTests(ManagerTestCase):
    def _make_bundle(self, name: str, members: list[str]) -> None:
        for member in members:
            skill_dir = self.source / name / member
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(
                f"---\nname: {member}\ndescription: {member} skill.\n---\n\n",
                encoding="utf-8",
            )

    def test_list_data_reports_partial_bundle(self) -> None:
        self._make_bundle("collection", ["alpha", "beta"])
        self.manager.add(
            ["collection"], "link", force=False, yes=True, interactive=False
        )
        remove_target(self.target / "beta")

        views, tree_roots = self.manager.list_data()
        root = tree_roots[0]
        self.assertEqual(root.view.name, "collection")
        self.assertEqual(root.view.status, STATUS_PARTIAL)
        statuses = {node.view.name: node.view.status for node in root.children}
        self.assertEqual(statuses["alpha"], STATUS_INSTALLED)
        self.assertEqual(statuses["beta"], STATUS_MISSING)

    def test_list_data_installed_bundle(self) -> None:
        self._make_bundle("collection", ["alpha", "beta"])
        self.manager.add(
            ["collection"], "link", force=False, yes=True, interactive=False
        )
        views, tree_roots = self.manager.list_data()
        root = tree_roots[0]
        self.assertEqual(root.view.status, STATUS_INSTALLED)


class RemoveTests(ManagerTestCase):
    def test_remove_deletes_target_and_manifest(self) -> None:
        write_skill(self.source, "alpha")
        self.manager.add(["alpha"], "link", force=False, yes=True, interactive=False)
        self.manager.remove(["alpha"], yes=True, force=False)
        self.assertFalse((self.target / "alpha").exists())
        self.assertIsNone(manifest.get_entry(self.manifest_data(), "alpha"))

    def test_remove_refuses_unmanaged_without_force(self) -> None:
        (self.target).mkdir(parents=True)
        (self.target / "external").mkdir()
        self.manager.remove(["external"], yes=True, force=False)
        self.assertTrue((self.target / "external").exists())


class SyncTests(ManagerTestCase):
    def test_sync_repoints_link_to_newest_duplicate_source(self) -> None:
        first = self.source / "first" / "dup"
        second = self.source / "second" / "dup"
        for skill_dir, description in ((first, "First."), (second, "Second.")):
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                f"---\nname: dup\ndescription: {description}\n---\n",
                encoding="utf-8",
            )
        os.utime(first / "SKILL.md", (1_000_000_000, 1_000_000_000))
        os.utime(second / "SKILL.md", (1, 1))
        self.manager.ui = make_ui(chosen_one=0)
        self.manager.add(["dup"], "link", force=False, yes=True, interactive=True)
        self.assertEqual((self.target / "dup").resolve(), first.resolve())

        os.utime(first / "SKILL.md", (1, 1))
        os.utime(second / "SKILL.md", (1_000_000_000, 1_000_000_000))
        views = {view.name: view for view in self.manager.list_views()}
        self.assertEqual(views["dup"].status, STATUS_OUTDATED)
        self.manager.sync(yes=True, force=False)
        self.assertEqual((self.target / "dup").resolve(), second.resolve())

    def test_sync_updates_changed_copy(self) -> None:
        skill_dir = write_skill(self.source, "alpha", extra_files={"f.txt": "one"})
        self.manager.add(["alpha"], "copy", force=False, yes=True, interactive=False)
        (skill_dir / "f.txt").write_text("two", encoding="utf-8")
        self.manager.sync(yes=True, force=False)
        self.assertEqual(
            (self.target / "alpha" / "f.txt").read_text(encoding="utf-8"), "two"
        )

    def test_sync_reports_up_to_date(self) -> None:
        write_skill(self.source, "alpha")
        self.manager.add(["alpha"], "link", force=False, yes=True, interactive=False)
        self.ui.infos.clear()
        self.manager.sync(yes=True, force=False)
        self.assertTrue(any("up to date" in message for message in self.ui.infos))

    def test_sync_restores_missing_link(self) -> None:
        write_skill(self.source, "alpha")
        self.manager.add(["alpha"], "link", force=False, yes=True, interactive=False)
        (self.target / "alpha").unlink()
        self.manager.sync(yes=True, force=False)
        self.assertTrue(is_link(self.target / "alpha"))

    def test_sync_removes_missing_source(self) -> None:
        skill_dir = write_skill(self.source, "alpha")
        self.manager.add(["alpha"], "link", force=False, yes=True, interactive=False)
        import shutil

        shutil.rmtree(skill_dir)
        self.manager.sync(yes=True, force=False)
        self.assertFalse((self.target / "alpha").exists())
        self.assertIsNone(manifest.get_entry(self.manifest_data(), "alpha"))


class ListTests(ManagerTestCase):
    def test_statuses(self) -> None:
        write_skill(self.source, "linked")
        write_skill(self.source, "copied")
        write_skill(self.source, "missing")
        write_skill(self.source, "absent")
        self.manager.add(["linked"], "link", force=False, yes=True, interactive=False)
        self.manager.add(["copied"], "copy", force=False, yes=True, interactive=False)
        # Make the copy outdated.
        (self.source / "copied" / "SKILL.md").write_text(
            "---\nname: copied\ndescription: changed\n---\n", encoding="utf-8"
        )
        # External (unmanaged) target.
        (self.target).mkdir(parents=True, exist_ok=True)
        (self.target / "external").mkdir()

        views = {view.name: view for view in self.manager.list_views()}
        self.assertEqual(views["linked"].status, STATUS_INSTALLED)
        self.assertEqual(views["copied"].status, STATUS_OUTDATED)
        self.assertEqual(views["external"].status, STATUS_EXTERNAL)
        self.assertEqual(views["absent"].status, STATUS_NOT_INSTALLED)

    def test_list_views_verbose_warns_duplicates(self) -> None:
        write_skill(self.source, "dup", "Old description.")
        nested = self.source / "nested"
        write_skill(nested, "dup", "New description.")
        os.utime(nested / "dup" / "SKILL.md", (1_000_000_000, 1_000_000_000))
        os.utime(self.source / "dup" / "SKILL.md", (1, 1))

        self.manager.list_views(verbose=True)

        self.assertTrue(any("defined multiple times" in w for w in self.ui.warnings))
        self.assertTrue(any("newest source" in w for w in self.ui.warnings))


if __name__ == "__main__":
    unittest.main()
