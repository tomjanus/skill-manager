from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skill_manager import manifest
from skill_manager.operations import (
    STATUS_EXTERNAL,
    STATUS_INSTALLED,
    STATUS_NOT_INSTALLED,
    STATUS_OUTDATED,
    Manager,
)
from skill_manager.platform import LinkError, is_link
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


if __name__ == "__main__":
    unittest.main()
