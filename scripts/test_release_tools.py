#!/usr/bin/env python3
"""Dry-run the version, changelog, and publish decisions."""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

import release_tools


REPO = Path(__file__).resolve().parents[1]

PYPROJECT = """\
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "scrapy-proxy-headers"
version = "0.2.2"
dependencies = [
    "scrapy>=2.17.0,<2.20",
]
"""

DOCS = """\
project = 'Scrapy Proxy Headers'
release = '0.2.2'
"""

# Same heading shape as release 0.2.2 (PR #19).
CHANGELOG_022 = """\
# Changelog

## [0.2.2] - 2026-11-09

### Security

- Reject a CR or LF in a CONNECT proxy_headers name or value.
"""


def write_tree(
    root: Path,
    changelog: str = CHANGELOG_022,
    docs: str = DOCS,
) -> None:
    """Write a tiny package tree under ``root``."""
    (root / "docs").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        PYPROJECT, encoding="utf-8", newline="\n"
    )
    (root / "docs" / "conf.py").write_text(
        docs, encoding="utf-8", newline="\n"
    )
    (root / "CHANGELOG.md").write_text(
        changelog, encoding="utf-8", newline="\n"
    )
    (root / "requirements.txt").write_text(
        "scrapy>=2.17.0,<2.20\n",
        encoding="utf-8",
        newline="\n",
    )


class ReleaseToolTests(unittest.TestCase):
    def test_prepare_real_files_only_changes_versions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            for rel in ("pyproject.toml", "CHANGELOG.md", "docs/conf.py"):
                (root / rel).write_bytes((REPO / rel).read_bytes())
            before_py = (root / "pyproject.toml").read_text(encoding="utf-8")
            docs_path = root / "docs" / "conf.py"
            before_docs = docs_path.read_text(encoding="utf-8")
            before_log = (root / "CHANGELOG.md").read_text(encoding="utf-8")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                version, notes = release_tools.prepare(
                    root, "patch", day="2026-11-12"
                )
            self.assertEqual(version, "0.2.3")
            self.assertEqual(notes, "## [0.2.3] - 2026-11-12\n")
            self.assertIn("no Unreleased section", stderr.getvalue())
            after_py = (root / "pyproject.toml").read_text(encoding="utf-8")
            after_docs = docs_path.read_text(encoding="utf-8")
            self.assertEqual(
                after_py,
                before_py.replace('version = "0.2.2"', 'version = "0.2.3"', 1),
            )
            self.assertEqual(
                after_docs,
                before_docs.replace(
                    "release = '0.2.2'", "release = '0.2.3'", 1
                ),
            )
            text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
            self.assertIn("## [0.2.3] - 2026-11-12", text)
            self.assertIn(before_log.split("# Changelog", 1)[1].strip(), text)
            release_tools.check_release(root, "0.2.3")

    def test_release_022_shape_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_tree(root)
            release_tools.check_release(root, "0.2.2")
            branch_version = release_tools.version_from_branch(
                "release/0.2.2"
            )
            release_tools.check_release(root, branch_version)

    def test_live_tree_when_version_is_released(self) -> None:
        version = release_tools.read_pyproject_version(REPO)
        changelog = release_tools.read_text(REPO / "CHANGELOG.md")
        if not release_tools.dated_sections(changelog, version):
            self.skipTest(f"{version} has no dated changelog section")
        release_tools.check_release(REPO, version)
        self.assertEqual(release_tools.read_docs_release(REPO), version)

    def test_docs_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_tree(root, docs="release = '0.2.1'\n")
            with self.assertRaises(release_tools.ReleaseError) as raised:
                release_tools.check_release(root, "0.2.2")
        self.assertIn("docs/conf.py", str(raised.exception))

    def test_missing_date_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_tree(
                root,
                changelog="# Changelog\n\n## [0.2.2]\n\n- Note.\n",
            )
            with self.assertRaises(release_tools.ReleaseError) as raised:
                release_tools.check_release(root, "0.2.2")
        self.assertIn("dated section", str(raised.exception))

    def test_branch_name(self) -> None:
        self.assertEqual(
            release_tools.version_from_branch("release/1.4.0"), "1.4.0"
        )
        with self.assertRaises(release_tools.ReleaseError):
            release_tools.version_from_branch("release/v1.4.0")
        with self.assertRaises(release_tools.ReleaseError):
            release_tools.version_from_branch("cursor/release-flow")

    def test_prepare_moves_bracketed_unreleased(self) -> None:
        changelog = (
            "# Changelog\n\n"
            "## [Unreleased]\n\n"
            "- First\n\n"
            "## [0.2.2] - 2026-11-09\n\n"
            "- Old\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_tree(root, changelog=changelog)
            version, notes = release_tools.prepare(
                root, "patch", day="2026-11-12"
            )
            self.assertEqual(version, "0.2.3")
            self.assertEqual(
                notes,
                "## [0.2.3] - 2026-11-12\n\n- First\n",
            )
            text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
            self.assertEqual(
                text,
                "# Changelog\n\n"
                "## [Unreleased]\n\n"
                "## [0.2.3] - 2026-11-12\n\n"
                "- First\n\n"
                "## [0.2.2] - 2026-11-09\n\n"
                "- Old\n",
            )
            pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
            self.assertIn('version = "0.2.3"', pyproject)
            self.assertIn("scrapy>=2.17.0,<2.20", pyproject)
            docs = (root / "docs" / "conf.py").read_text(encoding="utf-8")
            self.assertEqual(
                docs,
                "project = 'Scrapy Proxy Headers'\nrelease = '0.2.3'\n",
            )
            requirements = (root / "requirements.txt").read_text(
                encoding="utf-8"
            )
            self.assertEqual(requirements, "scrapy>=2.17.0,<2.20\n")
            release_tools.check_release(root, "0.2.3")

    def test_prepare_accepts_plain_unreleased_heading(self) -> None:
        changelog = (
            "# Changelog\n\n"
            "## Unreleased\n\n"
            "Notes for the next release.\n\n"
            "## [0.2.2] - 2026-11-09\n\n"
            "- Old\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_tree(root, changelog=changelog)
            version, notes = release_tools.prepare(
                root, "0.3.0", day="2026-12-01"
            )
            self.assertEqual(version, "0.3.0")
            self.assertIn("Notes for the next release.", notes)
            text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
            self.assertIn("## [0.3.0] - 2026-12-01", text)
            self.assertIn("## [Unreleased]", text)

    def test_prepare_inserts_section_when_unreleased_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_tree(root)
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                version, notes = release_tools.prepare(
                    root, "minor", day="2026-11-12"
                )
            self.assertEqual(version, "0.3.0")
            self.assertEqual(notes, "## [0.3.0] - 2026-11-12\n")
            self.assertIn("no Unreleased section", stderr.getvalue())
            text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
            self.assertTrue(
                text.startswith(
                    "# Changelog\n\n## [Unreleased]\n\n"
                    "## [0.3.0] - 2026-11-12\n\n## [0.2.2] - 2026-11-09\n"
                )
            )
            release_tools.check_release(root, "0.3.0")

    def test_prepare_refuses_duplicate_section_and_bad_spec(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_tree(root)
            with self.assertRaises(release_tools.ReleaseError):
                release_tools.prepare(root, "0.2.2", day="2026-11-12")
            with self.assertRaises(release_tools.ReleaseError):
                release_tools.bump_version("0.2.2", "v0.2.3")
            with self.assertRaises(release_tools.ReleaseError):
                release_tools.bump_version("0.2.2", "1.2")
        self.assertEqual(release_tools.bump_version("0.2.2", "major"), "1.0.0")
        self.assertEqual(release_tools.bump_version("1.2.3", "minor"), "1.3.0")

    def test_prepare_normalizes_crlf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_tree(root)
            path = root / "pyproject.toml"
            path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
            release_tools.prepare(root, "patch", day="2026-11-12")
            self.assertNotIn(b"\r", path.read_bytes())

    def test_publish_plan(self) -> None:
        sha = "abc123"
        common = {"version": "0.2.3", "merge_sha": sha}
        done = release_tools.plan_publish(
            on_pypi=True,
            release_exists=True,
            release_target=sha,
            run_attempt=2,
            **common,
        )
        self.assertEqual(done.token, "already-done")
        self.assertTrue(done.ok)

        first = release_tools.plan_publish(
            on_pypi=False,
            release_exists=False,
            release_target="",
            run_attempt=1,
            **common,
        )
        self.assertEqual(first.token, "publish-and-release")

        taken = release_tools.plan_publish(
            on_pypi=True,
            release_exists=True,
            release_target="other",
            run_attempt=1,
            **common,
        )
        self.assertEqual(taken.token, "fail-tag-taken")
        self.assertFalse(taken.ok)
        self.assertIn("points at other", taken.message)

        exists = release_tools.plan_publish(
            on_pypi=True,
            release_exists=False,
            release_target="",
            run_attempt=1,
            **common,
        )
        self.assertEqual(exists.token, "fail-already-on-pypi")
        self.assertIn(
            "https://pypi.org/project/scrapy-proxy-headers/0.2.3/",
            exists.message,
        )

        retry = release_tools.plan_publish(
            on_pypi=True,
            release_exists=False,
            release_target="",
            run_attempt=2,
            **common,
        )
        self.assertEqual(retry.token, "release-only")

        missing_upload = release_tools.plan_publish(
            on_pypi=False,
            release_exists=True,
            release_target=sha,
            run_attempt=1,
            **common,
        )
        self.assertEqual(missing_upload.token, "publish-only")


if __name__ == "__main__":
    unittest.main()
