from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from skill_manager import platform
from tests.helpers import write_skill


class LinkTests(unittest.TestCase):
    def test_link_creates_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = write_skill(root, "alpha")
            target = root / "target"
            platform.link(source, target)
            self.assertTrue(target.is_symlink())
            self.assertTrue(target.exists())

    def test_is_broken_link(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = write_skill(root, "alpha")
            target = root / "target"
            platform.link(source, target)
            source.rename(root / "moved")
            self.assertTrue(platform.is_broken_link(target))
            self.assertTrue(platform.target_exists(target))


class RemoveTargetTests(unittest.TestCase):
    def test_removes_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = write_skill(root, "alpha")
            target = root / "target"
            platform.copy_tree(source, target)
            platform.remove_target(target)
            self.assertFalse(target.exists())

    def test_removes_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = write_skill(root, "alpha")
            target = root / "target"
            platform.link(source, target)
            platform.remove_target(target)
            self.assertFalse(platform.target_exists(target))


class CopyTreeTests(unittest.TestCase):
    def test_copies_nested_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = write_skill(root, "alpha", extra_files={"sub/f.txt": "data"})
            target = root / "target"
            platform.copy_tree(source, target)
            self.assertTrue((target / "sub" / "f.txt").is_file())
            self.assertFalse(target.is_symlink())


if __name__ == "__main__":
    unittest.main()
