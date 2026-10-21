from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from skill_manager import config


class ExpandPathTests(unittest.TestCase):
    def test_expands_home(self) -> None:
        self.assertEqual(config.expand_path("~/skills"), Path.home() / "skills")

    def test_expands_env_var(self) -> None:
        import os

        os.environ["SKILL_MANAGER_TEST_DIR"] = "/tmp/somewhere"
        try:
            self.assertEqual(
                config.expand_path("$SKILL_MANAGER_TEST_DIR/x"),
                Path("/tmp/somewhere/x"),
            )
        finally:
            del os.environ["SKILL_MANAGER_TEST_DIR"]


class ReadEnvFileTests(unittest.TestCase):
    def test_missing_file_is_empty(self) -> None:
        self.assertEqual(config.read_env_file(Path("/nonexistent/.env")), {})

    def test_parses_quotes_comments_and_blanks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(
                "# comment\n\nSKILLS_DIR='~/skills'\nOTHER=\"a=b\"\nPLAIN=value\n",
                encoding="utf-8",
            )
            values = config.read_env_file(path)
        self.assertEqual(values["SKILLS_DIR"], "~/skills")
        self.assertEqual(values["OTHER"], "a=b")
        self.assertEqual(values["PLAIN"], "value")


class ResolveSkillsDirTests(unittest.TestCase):
    def test_cli_wins(self) -> None:
        result = config.resolve_skills_dir("/cli", Path("/nonexistent"), {})
        self.assertEqual(result, Path("/cli"))

    def test_env_file_beats_default(self) -> None:
        result = config.resolve_skills_dir(
            None, Path("/nonexistent"), {"SKILLS_DIR": "/env"}
        )
        self.assertEqual(result, Path("/env"))

    def test_default(self) -> None:
        result = config.resolve_skills_dir(None, Path("/nonexistent"), {})
        self.assertEqual(result, Path.home() / "skills")


class ResolveTargetDirTests(unittest.TestCase):
    def test_cli_wins(self) -> None:
        result = config.resolve_target_dir(
            "/cli", Path("/nonexistent"), Path("/proj"), {}
        )
        self.assertEqual(result, Path("/cli"))

    def test_env_var_beats_default(self) -> None:
        result = config.resolve_target_dir(
            None,
            Path("/nonexistent"),
            Path("/proj"),
            {"SKILLS_TARGET_DIR": "/env-target"},
        )
        self.assertEqual(result, Path("/env-target"))

    def test_default_is_opencode_skills(self) -> None:
        result = config.resolve_target_dir(
            None, Path("/nonexistent"), Path("/proj"), {}
        )
        self.assertEqual(result, Path("/proj/.opencode/skills"))


class WriteDefaultEnvFileTests(unittest.TestCase):
    def test_creates_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config" / ".env"
            self.assertTrue(config.write_default_env_file(path, Path("~/skills")))
            self.assertIn("SKILLS_DIR=~/skills", path.read_text(encoding="utf-8"))
            self.assertFalse(config.write_default_env_file(path, Path("~/skills")))


if __name__ == "__main__":
    unittest.main()
