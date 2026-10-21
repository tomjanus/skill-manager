from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from skill_manager.cli import main
from tests.helpers import init_git, write_skill


class CliTestCase(unittest.TestCase):
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
        write_skill(self.source, "alpha", "Alpha skill.")
        write_skill(self.source, "beta", "Beta skill.")

    def run_cli(self, *args: str) -> int:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(
                [
                    "--skills-dir",
                    str(self.source),
                    "--env-file",
                    str(self.env_file),
                    "--root",
                    str(self.project),
                    *args,
                ]
            )
        self.output = out.getvalue()
        self.errors = err.getvalue()
        return code

    def target(self, name: str) -> Path:
        return self.project / ".opencode" / "skills" / name


class AddAndRemoveTests(CliTestCase):
    def test_add_then_list_then_remove(self) -> None:
        self.assertEqual(self.run_cli("add", "alpha"), 0)
        self.assertTrue(self.target("alpha").is_symlink())
        self.assertEqual(self.run_cli("remove", "alpha", "--yes"), 0)
        self.assertFalse(self.target("alpha").exists())

    def test_add_unknown_name_returns_nonzero(self) -> None:
        self.assertEqual(self.run_cli("add", "nope"), 1)

    def test_add_over_unmanaged_target_returns_nonzero(self) -> None:
        (self.project / ".opencode" / "skills" / "alpha").mkdir(parents=True)
        self.assertEqual(self.run_cli("add", "alpha"), 1)
        self.assertFalse(self.target("alpha").is_symlink())

    def test_add_with_force_replaces_unmanaged_target(self) -> None:
        (self.project / ".opencode" / "skills" / "alpha").mkdir(parents=True)
        self.assertEqual(self.run_cli("add", "alpha", "--force"), 0)
        self.assertTrue(self.target("alpha").is_symlink())

    def test_remove_unmanaged_requires_force(self) -> None:
        (self.project / ".opencode" / "skills" / "alpha").mkdir(parents=True)
        self.assertEqual(self.run_cli("remove", "alpha", "--yes"), 1)
        self.assertTrue(self.target("alpha").exists())
        self.assertEqual(self.run_cli("remove", "alpha", "--yes", "--force"), 0)
        self.assertFalse(self.target("alpha").exists())


class ListTests(CliTestCase):
    def test_list_json(self) -> None:
        self.run_cli("add", "alpha")
        self.assertEqual(self.run_cli("list", "--json"), 0)
        payload = json.loads(self.output)
        self.assertEqual(payload[0]["name"], "alpha")
        self.assertEqual(payload[0]["status"], "installed")
        self.assertEqual(payload[0]["mode"], "link")


class SyncTests(CliTestCase):
    def test_sync_updates_changed_copy(self) -> None:
        skill_dir = write_skill(self.source, "alpha", extra_files={"f.txt": "one"})
        self.run_cli("add", "alpha", "--copy")
        (skill_dir / "f.txt").write_text("two", encoding="utf-8")
        self.assertEqual(self.run_cli("sync", "--yes"), 0)
        self.assertEqual(
            (self.target("alpha") / "f.txt").read_text(encoding="utf-8"), "two"
        )


if __name__ == "__main__":
    unittest.main()
