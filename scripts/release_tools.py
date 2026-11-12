#!/usr/bin/env python3
"""Prepare a release and check that its version manifests agree.

Manifests are ``pyproject.toml`` ``[project].version`` and ``docs/conf.py``
``release``. A release section is ``## [X.Y.Z] - YYYY-MM-DD``. Brackets on
the version are optional. ``## Unreleased`` is accepted too.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PACKAGE = "scrapy-proxy-headers"
_VERSION = re.compile(r"\d+\.\d+\.\d+")
_DATED = re.compile(
    r"^## \[?(?P<version>\d+\.\d+\.\d+)\]? - "
    r"(?P<date>\d{4}-\d{2}-\d{2})[ \t]*$",
    re.MULTILINE,
)
_UNRELEASED = re.compile(r"^## \[?Unreleased\]?[ \t]*$", re.MULTILINE)
_PROJECT = re.compile(r"(?ms)^\[project\][ \t]*\n.*?(?=^\[|\Z)")
_VERSION_ASSIGN = re.compile(
    r"^(version[ \t]*=[ \t]*)(?P<quote>['\"])"
    r"(?P<value>[^'\"]*)(?P=quote)",
    re.MULTILINE,
)
_RELEASE_ASSIGN = re.compile(
    r"^(release[ \t]*=[ \t]*)(?P<quote>['\"])"
    r"(?P<value>[^'\"]*)(?P=quote)",
    re.MULTILINE,
)
_USER_AGENT = "scrapy-proxy-headers-release"


class ReleaseError(Exception):
    """A release manifest, changelog, or registry check failed."""


@dataclass(frozen=True)
class Plan:
    """What the publish job should do for one merge."""

    token: str
    message: str
    ok: bool


def read_text(path: Path) -> str:
    """Read ``path`` as UTF-8 text with Unix newlines."""
    data = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return data.decode("utf-8")


def write_text(path: Path, text: str) -> None:
    """Write ``text`` as UTF-8 with a trailing newline."""
    if not text.endswith("\n"):
        text += "\n"
    path.write_bytes(text.encode("utf-8"))


def parse_version(value: str) -> str:
    """Return canonical ``X.Y.Z`` or raise ``ReleaseError``."""
    text = value.strip()
    if not _VERSION.fullmatch(text):
        raise ReleaseError(f"Version {value!r} is not X.Y.Z.")
    parts = text.split(".")
    if any(len(part) > 1 and part.startswith("0") for part in parts):
        raise ReleaseError(f"Version {text} has a leading zero.")
    return text


def version_from_branch(branch: str) -> str:
    """Return the version from a ``release/X.Y.Z`` branch name."""
    match = re.fullmatch(r"release/(\d+\.\d+\.\d+)", branch.strip())
    if match is None:
        raise ReleaseError(
            f"Branch {branch!r} is not release/X.Y.Z (no v prefix)."
        )
    return parse_version(match.group(1))


def read_pyproject_version(root: Path) -> str:
    """Return ``[project].version`` from ``pyproject.toml``."""
    path = root / "pyproject.toml"
    if not path.is_file():
        raise ReleaseError("pyproject.toml is missing.")
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    try:
        version = data["project"]["version"]
    except KeyError as exc:
        raise ReleaseError(
            "pyproject.toml has no [project].version."
        ) from exc
    return parse_version(str(version))


def read_docs_release(root: Path) -> str:
    """Return the Sphinx ``release`` assignment in ``docs/conf.py``."""
    path = root / "docs" / "conf.py"
    if not path.is_file():
        raise ReleaseError("docs/conf.py is missing.")
    match = _RELEASE_ASSIGN.search(read_text(path))
    if match is None:
        raise ReleaseError("docs/conf.py has no release = assignment.")
    return parse_version(match.group("value"))


def dated_sections(changelog: str, version: str) -> list[re.Match[str]]:
    """Return changelog headings for ``version``."""
    wanted = parse_version(version)
    return [
        match
        for match in _DATED.finditer(changelog)
        if match.group("version") == wanted
    ]


def section_text(changelog: str, version: str) -> str:
    """Return the dated changelog section, including its heading."""
    found = dated_sections(changelog, version)
    if not found:
        raise ReleaseError(
            "CHANGELOG.md has no dated section "
            f"'## [{version}] - YYYY-MM-DD' for {version}."
        )
    if len(found) > 1:
        raise ReleaseError(
            f"CHANGELOG.md has more than one section for {version}."
        )
    start = found[0].start()
    trailing = re.search(r"(?m)^## ", changelog[found[0].end():])
    if trailing is None:
        end = len(changelog)
    else:
        end = found[0].end() + trailing.start()
    return changelog[start:end].strip("\n") + "\n"


def check_release(root: Path, version: str) -> None:
    """Raise ``ReleaseError`` when manifests or the changelog disagree."""
    expected = parse_version(version)
    errors: list[str] = []
    try:
        found = read_pyproject_version(root)
    except ReleaseError as exc:
        errors.append(str(exc))
    else:
        if found != expected:
            errors.append(
                f"pyproject.toml version is {found}, expected {expected}."
            )
    try:
        docs_release = read_docs_release(root)
    except ReleaseError as exc:
        errors.append(str(exc))
    else:
        if docs_release != expected:
            errors.append(
                f"docs/conf.py release is {docs_release}, expected {expected}."
            )
    changelog_path = root / "CHANGELOG.md"
    if not changelog_path.is_file():
        errors.append("CHANGELOG.md is missing.")
    else:
        try:
            section_text(read_text(changelog_path), expected)
        except ReleaseError as exc:
            errors.append(str(exc))
    if errors:
        raise ReleaseError("\n".join(errors))


def bump_version(current: str, spec: str) -> str:
    """Return ``spec`` when it is X.Y.Z, or the next patch, minor, or major."""
    text = spec.strip()
    lowered = text.lower()
    if lowered not in {"patch", "minor", "major"}:
        return parse_version(text)
    major, minor, patch = (
        int(part) for part in parse_version(current).split(".")
    )
    if lowered == "patch":
        patch += 1
    elif lowered == "minor":
        minor += 1
        patch = 0
    else:
        major += 1
        minor = 0
        patch = 0
    return f"{major}.{minor}.{patch}"


def _replace_assignment(
    pattern: re.Pattern[str],
    text: str,
    new_value: str,
    label: str,
) -> str:
    match = pattern.search(text)
    if match is None:
        raise ReleaseError(f"{label} has no version assignment.")
    quote = match.group("quote")
    replacement = f"{match.group(1)}{quote}{new_value}{quote}"
    start = match.start()
    end = match.end()
    return text[:start] + replacement + text[end:]


def _set_pyproject_version(text: str, new_version: str, current: str) -> str:
    table = _PROJECT.search(text)
    if table is None:
        raise ReleaseError("pyproject.toml has no [project] table.")
    match = _VERSION_ASSIGN.search(table.group(0))
    if match is None:
        raise ReleaseError(
            "pyproject.toml [project] has no version assignment."
        )
    if match.group("value") != current:
        raise ReleaseError(
            "pyproject.toml version assignment is "
            f"{match.group('value')}, [project].version is {current}."
        )
    updated = _replace_assignment(
        _VERSION_ASSIGN,
        table.group(0),
        new_version,
        "pyproject.toml",
    )
    start = table.start()
    end = table.end()
    return text[:start] + updated + text[end:]


def _insert_block(changelog: str, block: str) -> str:
    title = re.match(r"(?s)\A(\s*# Changelog[ \t]*\n+)", changelog)
    if title is None:
        return block + changelog.lstrip("\n")
    prefix = title.group(1)
    if not prefix.endswith("\n\n"):
        prefix = prefix.rstrip("\n") + "\n\n"
    rest = changelog[title.end():].lstrip("\n")
    return prefix + block + rest


def move_unreleased(changelog: str, version: str, day: str) -> tuple[str, str]:
    """Move Unreleased to a dated section.

    Returns the updated changelog and the release-notes section.
    """
    parse_version(version)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise ReleaseError(f"Date {day!r} is not YYYY-MM-DD.")
    if dated_sections(changelog, version):
        raise ReleaseError(
            f"CHANGELOG.md already has a section for {version}."
        )
    headings = list(_UNRELEASED.finditer(changelog))
    if len(headings) > 1:
        raise ReleaseError(
            "CHANGELOG.md has more than one Unreleased section."
        )
    dated = f"## [{version}] - {day}"
    if not headings:
        print(
            "::warning::CHANGELOG.md has no Unreleased section. "
            f"The {version} notes are empty.",
            file=sys.stderr,
        )
        block = f"## [Unreleased]\n\n{dated}\n\n"
        return _insert_block(changelog, block), f"{dated}\n"
    heading = headings[0]
    body_start = heading.end()
    if changelog[body_start:body_start + 1] == "\n":
        body_start += 1
    next_heading = re.search(r"(?m)^## ", changelog[body_start:])
    if next_heading is None:
        body_end = len(changelog)
    else:
        body_end = body_start + next_heading.start()
    body = changelog[body_start:body_end].strip("\n")
    before = changelog[:heading.start()].rstrip("\n")
    after = changelog[body_end:].lstrip("\n")
    parts = ["## [Unreleased]", "", dated]
    if body:
        parts.extend(["", body])
    block = "\n".join(parts) + "\n\n"
    updated = (before + "\n\n" if before else "") + block + after
    if body:
        notes = f"{dated}\n\n{body}\n"
    else:
        notes = f"{dated}\n"
    return updated, notes


def prepare(root: Path, spec: str, day: str | None = None) -> tuple[str, str]:
    """Bump the manifests and changelog.

    Returns the new version and the release-notes section.
    """
    current = read_pyproject_version(root)
    version = bump_version(current, spec)
    when = day or datetime.now(timezone.utc).date().isoformat()
    changelog_path = root / "CHANGELOG.md"
    if not changelog_path.is_file():
        raise ReleaseError("CHANGELOG.md is missing.")
    changelog, notes = move_unreleased(
        read_text(changelog_path), version, when
    )
    pyproject_path = root / "pyproject.toml"
    docs_path = root / "docs" / "conf.py"
    pyproject = _set_pyproject_version(
        read_text(pyproject_path), version, current
    )
    docs = _replace_assignment(
        _RELEASE_ASSIGN, read_text(docs_path), version, "docs/conf.py"
    )
    write_text(pyproject_path, pyproject)
    write_text(docs_path, docs)
    write_text(changelog_path, changelog)
    check_release(root, version)
    return version, notes


def plan_publish(
    *,
    on_pypi: bool,
    release_exists: bool,
    release_target: str,
    merge_sha: str,
    run_attempt: int,
    version: str,
) -> Plan:
    """Decide whether to upload, create the GitHub release, or fail."""
    version = parse_version(version)
    if run_attempt < 1:
        raise ReleaseError(f"Run attempt {run_attempt} is invalid.")
    tag = f"v{version}"
    project_url = f"https://pypi.org/project/{PACKAGE}/{version}/"
    same_commit = bool(release_target) and release_target == merge_sha
    if release_exists and same_commit and on_pypi:
        return Plan(
            "already-done",
            (
                f"{tag} is already on PyPI and the GitHub release points "
                "at this merge. Nothing to do."
            ),
            True,
        )
    if release_exists and same_commit and not on_pypi:
        return Plan(
            "publish-only",
            (
                f"GitHub release {tag} already points at this merge. "
                "Publishing the missing package."
            ),
            True,
        )
    if release_exists and not same_commit:
        target = release_target or "(unknown)"
        return Plan(
            "fail-tag-taken",
            (
                f"Tag {tag} already exists and points at {target}, "
                f"not merge {merge_sha}. Refusing to publish."
            ),
            False,
        )
    if on_pypi and run_attempt == 1:
        return Plan(
            "fail-already-on-pypi",
            (
                f"{PACKAGE} {version} is already on PyPI ({project_url}) "
                f"and there is no GitHub release {tag} for this merge. "
                "Refusing to upload it again."
            ),
            False,
        )
    if on_pypi and run_attempt > 1:
        return Plan(
            "release-only",
            (
                f"{PACKAGE} {version} is already on PyPI from an earlier "
                "attempt. Skipping the upload and creating the GitHub release."
            ),
            True,
        )
    return Plan(
        "publish-and-release",
        f"Publishing {PACKAGE} {version} and creating GitHub release {tag}.",
        True,
    )


def _request_bytes(url: str, headers: dict[str, str]) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers=headers)
    last: Exception | None = None
    for _attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return int(response.status), response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return 404, b""
            last = exc
            if exc.code < 500:
                break
        except urllib.error.URLError as exc:
            last = exc
    raise ReleaseError(f"Request failed: {last}") from last


def _pypi_has_release(version: str) -> bool:
    url = f"https://pypi.org/pypi/{PACKAGE}/{version}/json"
    status, _body = _request_bytes(url, {"User-Agent": _USER_AGENT})
    if status == 404:
        return False
    if status != 200:
        raise ReleaseError(f"PyPI returned HTTP {status} for {version}.")
    return True


def _github_release_target(repo: str, tag: str) -> str | None:
    token = os.environ["GH_TOKEN"]
    url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
    status, body = _request_bytes(
        url,
        {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": _USER_AGENT,
        },
    )
    if status == 404:
        return None
    payload = json.loads(body)
    target = payload.get("target_commitish") or ""
    return str(target)


def _selected_version(args: argparse.Namespace) -> str:
    if bool(args.version) == bool(args.branch):
        raise ReleaseError("Pass exactly one of --version or --branch.")
    if args.branch:
        return version_from_branch(args.branch)
    return parse_version(args.version)


def _cmd_check(args: argparse.Namespace) -> int:
    version = _selected_version(args)
    check_release(Path(args.root), version)
    print(
        f"Release {version} matches the manifests and CHANGELOG.md.",
        file=sys.stderr,
    )
    print(version)
    return 0


def _cmd_prepare(args: argparse.Namespace) -> int:
    version, notes = prepare(Path(args.root), args.spec, day=args.date)
    if args.notes_file:
        write_text(Path(args.notes_file), notes)
    print(version)
    return 0


def _cmd_notes(args: argparse.Namespace) -> int:
    version = _selected_version(args)
    changelog = read_text(Path(args.root) / "CHANGELOG.md")
    sys.stdout.write(section_text(changelog, version))
    return 0


def _cmd_decide(_args: argparse.Namespace) -> int:
    version = parse_version(os.environ["VERSION"])
    merge_sha = os.environ["MERGE_SHA"]
    run_attempt = int(os.environ["RUN_ATTEMPT"])
    repo = os.environ["GITHUB_REPOSITORY"]
    target = _github_release_target(repo, f"v{version}")
    plan = plan_publish(
        on_pypi=_pypi_has_release(version),
        release_exists=target is not None,
        release_target=target or "",
        merge_sha=merge_sha,
        run_attempt=run_attempt,
        version=version,
    )
    if not plan.ok:
        raise ReleaseError(plan.message)
    print(plan.message, file=sys.stderr)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"decision={plan.token}\n")
    print(plan.token)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="Check manifests for one version")
    check.add_argument("--version")
    check.add_argument("--branch")
    check.set_defaults(func=_cmd_check)

    prepare_cmd = sub.add_parser(
        "prepare", help="Bump manifests and changelog"
    )
    prepare_cmd.add_argument(
        "--spec", required=True, help="X.Y.Z, patch, minor, or major"
    )
    prepare_cmd.add_argument("--date", help="YYYY-MM-DD (default: today, UTC)")
    prepare_cmd.add_argument(
        "--notes-file", help="Write the changelog section here"
    )
    prepare_cmd.set_defaults(func=_cmd_prepare)

    notes = sub.add_parser("notes", help="Print one changelog section")
    notes.add_argument("--version")
    notes.add_argument("--branch")
    notes.set_defaults(func=_cmd_notes)

    decide = sub.add_parser(
        "decide",
        help="Choose upload or GitHub release from the environment",
    )
    decide.set_defaults(func=_cmd_decide)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run a release subcommand. Return a process exit code."""
    args = _parser().parse_args(argv)
    try:
        return int(args.func(args))
    except ReleaseError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
