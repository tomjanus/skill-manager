from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from skill_manager.discovery import (
    content_hash,
    discover_skills,
    parse_frontmatter,
    read_skill,
)
from tests.helpers import write_skill


class ParseFrontmatterTests(unittest.TestCase):
    def test_parses_name_and_description(self) -> None:
        text = "---\nname: alpha\ndescription: A skill.\n---\n\nBody\n"
        metadata = parse_frontmatter(text)
        self.assertEqual(metadata["name"], "alpha")
        self.assertEqual(metadata["description"], "A skill.")

    def test_strips_quotes(self) -> None:
        text = "---\nname: \"alpha\"\ndescription: 'A skill.'\n---\n"
        metadata = parse_frontmatter(text)
        self.assertEqual(metadata["name"], "alpha")
        self.assertEqual(metadata["description"], "A skill.")

    def test_no_frontmatter(self) -> None:
        self.assertEqual(parse_frontmatter("# Just a doc\n"), {})

    def test_description_with_colon(self) -> None:
        text = "---\nname: a\ndescription: use when: doing x\n---\n"
        self.assertEqual(parse_frontmatter(text)["description"], "use when: doing x")


class ReadSkillTests(unittest.TestCase):
    def test_uses_directory_name_when_no_frontmatter_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "fallback"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text("# No frontmatter\n", encoding="utf-8")
            skill = read_skill(skill_dir)
        self.assertIsNotNone(skill)
        assert skill is not None
        self.assertEqual(skill.name, "fallback")

    def test_missing_skill_file_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(read_skill(Path(tmp)))


class DiscoverSkillsTests(unittest.TestCase):
    def test_skips_invalid_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root, "good")
            write_skill(root, ".hidden")
            (root / "no_skill_file").mkdir()
            (root / "a_file.txt").write_text("x", encoding="utf-8")
            names = [skill.name for skill in discover_skills(root)]
        self.assertEqual(names, ["good"])


class ContentHashTests(unittest.TestCase):
    def test_stable_and_order_independent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root, "a", extra_files={"b.txt": "B", "a.txt": "A"})
            first = content_hash(root / "a")
            second = content_hash(root / "a")
            self.assertEqual(first, second)

    def test_changes_with_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = write_skill(root, "a", extra_files={"f.txt": "one"})
            first = content_hash(skill_dir)
            (skill_dir / "f.txt").write_text("two", encoding="utf-8")
            second = content_hash(skill_dir)
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
