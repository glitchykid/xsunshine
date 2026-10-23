import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from xsunshine.core import prune
from xsunshine.filesystem import DirectoryTree


class DirectoryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = tempfile.TemporaryDirectory(prefix="xsunshine-test-")
        self.addCleanup(self.fixture.cleanup)
        self.root = Path(self.fixture.name)
        self.tree = DirectoryTree(self.root)

    def test_nested_unicode_and_bracket_names_are_removed_literally(self):
        (self.root / "пусто [1]" / "child").mkdir(parents=True)
        result = prune(self.tree, str(self.root), apply=True)
        self.assertEqual(result.deleted, 2)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_preview_changes_nothing(self):
        leaf = self.root / "parent" / "child"
        leaf.mkdir(parents=True)
        result = prune(self.tree, str(self.root))
        self.assertEqual(result.candidates, 2)
        self.assertTrue(leaf.is_dir())

    def test_zero_byte_and_hidden_files_are_content(self):
        directory = self.root / "keep"
        directory.mkdir()
        (directory / ".hidden").touch()
        (directory / "empty.txt").touch()
        self.assertEqual(prune(self.tree, str(self.root), apply=True).deleted, 0)
        self.assertEqual(len(list(directory.iterdir())), 2)

    def test_new_file_blocks_removal_after_inspection(self):
        directory = self.root / "changing"
        directory.mkdir()
        identity = self.tree.inspect(str(directory)).identity
        (directory / "arrived.txt").write_text("keep", encoding="utf-8")
        self.assertFalse(self.tree.remove_empty(str(directory), identity))
        self.assertTrue((directory / "arrived.txt").exists())

    def test_missing_scope_and_file_scope_report_errors(self):
        (self.root / "file").touch()
        for path in [self.root / "missing", self.root / "file"]:
            with self.subTest(path=path):
                result = prune(DirectoryTree(path), str(path), apply=True)
                self.assertEqual(result.errors, 1)

    def test_outside_scope_is_rejected(self):
        with self.assertRaises(ValueError):
            self.tree.remove_empty(str(self.root.parent), None)

    @unittest.skipUnless(os.name == "nt", "Windows junction behavior")
    def test_junctions_are_not_followed_even_in_explicit_scope(self):
        target = self.root / "target"
        (target / "empty").mkdir(parents=True)
        scope = self.root / "scope"
        scope.mkdir()
        junction = scope / "junction"
        # Both paths are isolated, generated test paths; cmd is only used to create a junction.
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(junction), str(target)],
            capture_output=True,
            text=True,
        )
        if result.returncode:
            self.skipTest("Junction creation unavailable: " + result.stderr)
        self.addCleanup(lambda: junction.rmdir() if junction.exists() else None)
        result = prune(DirectoryTree(scope), str(scope), apply=True)
        self.assertEqual(result.deleted, 0)
        self.assertGreaterEqual(result.skipped, 1)
        self.assertTrue((target / "empty").exists())
        result = prune(DirectoryTree(junction / "empty"), str(junction / "empty"), apply=True)
        self.assertEqual(result.deleted, 0)
        self.assertEqual(result.skipped, 1)


if __name__ == "__main__":
    unittest.main()
