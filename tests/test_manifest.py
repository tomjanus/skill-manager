from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from skill_manager.manifest import (
    ManifestError,
    empty_manifest,
    get_entry,
    load_manifest,
    manifest_path,
    remove_entry,
    save_manifest,
    set_entry,
)


class ManifestTests(unittest.TestCase):
    def test_absent_manifest_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = load_manifest(Path(tmp) / "missing.json")
        self.assertEqual(data["skills"], {})
        self.assertEqual(data["version"], 1)

    def test_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".skill-manager.json"
            data = empty_manifest()
            set_entry(data, "alpha", "link", "abc")
            save_manifest(path, data)
            loaded = load_manifest(path)
        self.assertEqual(get_entry(loaded, "alpha"), {"mode": "link", "hash": "abc"})

    def test_remove_entry(self) -> None:
        data = empty_manifest()
        set_entry(data, "alpha", "copy", "h")
        self.assertTrue(remove_entry(data, "alpha"))
        self.assertFalse(remove_entry(data, "alpha"))
        self.assertIsNone(get_entry(data, "alpha"))

    def test_malformed_manifest_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".skill-manager.json"
            path.write_text("{ not json", encoding="utf-8")
            with self.assertRaises(ManifestError):
                load_manifest(path)

    def test_wrong_shape_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".skill-manager.json"
            path.write_text(json.dumps({"skills": []}), encoding="utf-8")
            with self.assertRaises(ManifestError):
                load_manifest(path)

    def test_manifest_path(self) -> None:
        self.assertEqual(manifest_path(Path("/p")), Path("/p/.skill-manager.json"))


if __name__ == "__main__":
    unittest.main()
