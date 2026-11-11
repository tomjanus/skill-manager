from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from skill_manager.discovery import (
    DuplicateInfo,
    content_hash,
    discover_skills,
    discover_skills_with_duplicates,
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


class DiscoverSkillsRecursiveTests(unittest.TestCase):
    def test_finds_nested_skills(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root, "parent", "Parent skill.")
            child = root / "parent" / "child"
            write_skill(child, "child", "Child skill.")
            names = [skill.name for skill in discover_skills(root)]
        self.assertEqual(names, ["child", "parent"])

    def test_derives_name_from_frontmatter_not_dir_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            odd = root / "odd-dir-name"
            write_skill(odd, "renamed-skill", "A skill.")
            names = [skill.name for skill in discover_skills(root)]
        self.assertEqual(names, ["renamed-skill"])

    def test_skips_hidden_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root, "visible", "Visible.")
            hidden = root / ".hidden"
            write_skill(hidden, "hidden-skill", "Hidden.")
            names = [skill.name for skill in discover_skills(root)]
        self.assertEqual(names, ["visible"])

    def test_empty_dir_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(discover_skills(Path(tmp)), [])


class DiscoverSkillsSymlinkTests(unittest.TestCase):
    def test_follows_directory_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "real-repo"
            write_skill(real, "linked-skill", "A linked skill.")
            link = root / "link-to-repo"
            os.symlink(real, link)
            names = [skill.name for skill in discover_skills(root)]
        self.assertEqual(names, ["linked-skill"])

    def test_detects_symlink_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            loop = root / "loop"
            write_skill(loop, "loop-skill", "Loops.")
            cycle = loop / "back"
            os.symlink(root, cycle)
            names = [skill.name for skill in discover_skills(root)]
        self.assertEqual(names, ["loop-skill"])


class DiscoverSkillsDedupTests(unittest.TestCase):
    def test_keeps_newest_by_skill_md_mtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_dir = root / "old"
            new_dir = root / "new"
            write_skill(old_dir, "dup", "Old description.")
            write_skill(new_dir, "dup", "New description.")
            os.utime(new_dir / "dup" / "SKILL.md", (1_000_000_000, 1_000_000_000))
            os.utime(old_dir / "dup" / "SKILL.md", (1, 1))
            skills = discover_skills(root)
        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0].name, "dup")
        self.assertEqual(skills[0].description, "New description.")

    def test_reports_duplicates_when_verbose(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_dir = root / "old"
            new_dir = root / "new"
            write_skill(old_dir, "dup", "Old description.")
            write_skill(new_dir, "dup", "New description.")
            os.utime(new_dir / "dup" / "SKILL.md", (1_000_000_000, 1_000_000_000))
            os.utime(old_dir / "dup" / "SKILL.md", (1, 1))
            skills, duplicates = discover_skills_with_duplicates(root)
        self.assertEqual(len(skills), 1)
        self.assertEqual(len(duplicates), 1)
        dup = duplicates[0]
        assert isinstance(dup, DuplicateInfo)
        self.assertEqual(dup.name, "dup")
        self.assertEqual(dup.chosen, new_dir / "dup")
        self.assertIn(old_dir / "dup", dup.duplicates)


if __name__ == "__main__":
    unittest.main()
