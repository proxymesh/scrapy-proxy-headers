"""Tests for version bump and changelog notes."""

import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

import release_version

PYPROJECT = """\
[project]
name = "scrapy-proxy-headers"
version = "0.2.2"
dependencies = [
    "scrapy>=2.17.0,<2.20",
]
"""
DOCS = "release = '0.2.2'\n"
CHANGELOG = """\
# Changelog

## [Unreleased]

- First

## [0.2.2] - 2026-11-09

- Old
"""


def tree(root: Path, changelog: str = CHANGELOG) -> None:
    (root / "docs").mkdir()
    (root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8", newline="\n")
    (root / "docs" / "conf.py").write_text(DOCS, encoding="utf-8", newline="\n")
    (root / "CHANGELOG.md").write_text(changelog, encoding="utf-8", newline="\n")


class ReleaseVersionTests(unittest.TestCase):
    def test_prepare_moves_unreleased_and_bumps_both_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tree(root)
            version, release_notes = release_version.prepare(
                root, "patch", "2026-11-12"
            )
            self.assertEqual(version, "0.2.3")
            self.assertEqual(release_notes, "## 0.2.3 - 2026-11-12\n\n- First\n")
            self.assertIn(
                'version = "0.2.3"',
                (root / "pyproject.toml").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "scrapy>=2.17.0,<2.20",
                (root / "pyproject.toml").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                (root / "docs" / "conf.py").read_text(encoding="utf-8"),
                "release = '0.2.3'\n",
            )
            text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
            self.assertIn("## Unreleased\n\n## 0.2.3 - 2026-11-12\n\n- First\n", text)
            self.assertIn("## [0.2.2] - 2026-11-09", text)
            release_version.check(root, "0.2.3")
            self.assertIn("- First", release_version.notes_for(text, "0.2.3"))
            self.assertIn("- Old", release_version.notes_for(text, "0.2.2"))

    def test_missing_unreleased_section_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tree(root, "# Changelog\n\n## [0.2.2] - 2026-11-09\n\n- Old\n")
            with redirect_stderr(io.StringIO()) as stderr:
                version, release_notes = release_version.prepare(
                    root, "minor", "2026-11-12"
                )
            self.assertEqual(version, "0.3.0")
            self.assertEqual(release_notes, "## 0.3.0 - 2026-11-12\n")
            self.assertIn("no Unreleased section", stderr.getvalue())

    def test_check_rejects_a_docs_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tree(root)
            (root / "docs" / "conf.py").write_text(
                "release = '0.2.1'\n", encoding="utf-8"
            )
            with self.assertRaises(SystemExit):
                release_version.check(root, None)

    def test_non_release_branch_only_compares_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tree(root, "# Changelog\n\n## Unreleased\n\n- Pending\n")
            code = release_version.main(
                ["check", "--root", tmp, "--branch", "cursor/other"]
            )
            self.assertEqual(code, 0)
            with self.assertRaises(SystemExit):
                release_version.main(
                    ["check", "--root", tmp, "--branch", "release/0.2.2"]
                )


if __name__ == "__main__":
    unittest.main()
