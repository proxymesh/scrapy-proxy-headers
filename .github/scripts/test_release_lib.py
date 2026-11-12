"""Bump plus notes, and a release branch that does not match the version."""

import os
import unittest
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import release_lib


def tree(root):
    (root / "docs").mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\nversion = "0.2.2"\n', encoding="utf-8"
    )
    (root / "docs" / "conf.py").write_text("release = '0.2.2'\n", encoding="utf-8")
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## Unreleased\n\n- Note\n\n## 0.2.2 - 2026-11-09\n",
        encoding="utf-8",
    )


class ReleaseLibTests(unittest.TestCase):
    def test_bump_and_notes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            tree(root)
            release_lib.ROOT = root
            os.environ["VERSION_INPUT"] = "patch"
            os.environ["GITHUB_OUTPUT"] = str(root / "out")
            os.environ.pop("NOTES_FILE", None)
            os.environ.pop("GITHUB_HEAD_REF", None)
            os.environ["HEAD_REF"] = ""
            release_lib.bump()
            release_lib.check()
            with patch("sys.stdout", StringIO()) as stdout:
                release_lib.notes()
            self.assertIn("## 0.2.3 - ", stdout.getvalue())
            self.assertIn("- Note", stdout.getvalue())

    def test_branch_mismatch(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            tree(root)
            release_lib.ROOT = root
            os.environ.pop("GITHUB_HEAD_REF", None)
            os.environ["HEAD_REF"] = "release/9.9.9"
            with self.assertRaises(SystemExit):
                release_lib.check()


if __name__ == "__main__":
    unittest.main()
