"""Bump the package version and move or print changelog notes."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn

import tomllib

_VERSION = re.compile(r"\d+\.\d+\.\d+")
_DATED = re.compile(
    r"^## \[?(?P<version>\d+\.\d+\.\d+)\]? - (?P<date>\d{4}-\d{2}-\d{2})[ \t]*$",
    re.MULTILINE,
)
_UNRELEASED = re.compile(r"^## \[?Unreleased\]?[ \t]*$", re.MULTILINE)
_ASSIGN = re.compile(
    r"^(?P<key>version|release)[ \t]*=[ \t]*(?P<quote>['\"])(?P<value>[^'\"]*)(?P=quote)",
    re.MULTILINE,
)


def die(message: str) -> NoReturn:
    print(f"::error::{message}", file=sys.stderr)
    raise SystemExit(1)


def read_text(path: Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return data.decode()


def write_text(path: Path, text: str) -> None:
    if not text.endswith("\n"):
        text += "\n"
    path.write_bytes(text.encode())


def canonical(value: object) -> str:
    text = str(value).strip()
    if _VERSION.fullmatch(text) is None:
        die(f"Version {value!r} is not X.Y.Z.")
    if any(len(part) > 1 and part.startswith("0") for part in text.split(".")):
        die(f"Version {text} has a leading zero.")
    return text


def manifest_version(root: Path, kind: str) -> str:
    if kind == "version":
        with (root / "pyproject.toml").open("rb") as handle:
            return canonical(tomllib.load(handle)["project"]["version"])
    for match in _ASSIGN.finditer(read_text(root / "docs" / "conf.py")):
        if match.group("key") == "release":
            return canonical(match.group("value"))
    die("docs/conf.py has no release assignment.")


def notes_for(changelog: str, version: str) -> str:
    found = [m for m in _DATED.finditer(changelog) if m.group("version") == version]
    if len(found) != 1:
        die(f"CHANGELOG.md needs one dated section for {version}.")
    match = found[0]
    nxt = re.search(r"(?m)^## ", changelog[match.end() :])
    end = match.end() + nxt.start() if nxt else len(changelog)
    return changelog[match.start() : end].strip("\n") + "\n"


def check(root: Path, version: str | None) -> None:
    py_version = manifest_version(root, "version")
    docs = manifest_version(root, "release")
    expected = canonical(version) if version else py_version
    if py_version != expected or docs != expected:
        die(
            f"pyproject.toml is {py_version}, docs/conf.py is {docs}, expected {expected}."
        )
    if version:
        notes_for(read_text(root / "CHANGELOG.md"), expected)


def bump_version(current: str, spec: str) -> str:
    kind = spec.strip().lower()
    if kind not in {"patch", "minor", "major"}:
        return canonical(spec)
    major, minor, patch = (int(part) for part in canonical(current).split("."))
    if kind == "patch":
        patch += 1
    elif kind == "minor":
        minor, patch = minor + 1, 0
    else:
        major, minor, patch = major + 1, 0, 0
    return f"{major}.{minor}.{patch}"


def replace_version(text: str, key: str, new: str) -> str:
    for match in _ASSIGN.finditer(text):
        if match.group("key") != key:
            continue
        quote = match.group("quote")
        line = text[match.start() : match.end()]
        prefix_len = line.index(quote)
        updated = line[:prefix_len] + quote + new + quote
        return text[: match.start()] + updated + text[match.end() :]
    die(f"No {key} assignment.")


def move_unreleased(changelog: str, version: str, day: str) -> tuple[str, str]:
    if any(m.group("version") == version for m in _DATED.finditer(changelog)):
        die(f"CHANGELOG.md already has a section for {version}.")
    dated = f"## {version} - {day}"
    headings = list(_UNRELEASED.finditer(changelog))
    if len(headings) > 1:
        die("CHANGELOG.md has more than one Unreleased section.")
    notes = f"{dated}\n"
    if not headings:
        print(
            f"::warning::CHANGELOG.md has no Unreleased section. {version} notes are empty.",
            file=sys.stderr,
        )
        block = f"## Unreleased\n\n{dated}\n\n"
        title = re.match(r"(?s)\A(\s*# Changelog[ \t]*\n+)", changelog)
        rest = changelog if title is None else changelog[title.end() :]
        prefix = "" if title is None else title.group(1)
        return prefix + block + rest.lstrip("\n"), notes
    heading = headings[0]
    start = heading.end()
    if changelog[start : start + 1] == "\n":
        start += 1
    nxt = re.search(r"(?m)^## ", changelog[start:])
    end = start + nxt.start() if nxt else len(changelog)
    body = changelog[start:end].strip("\n")
    block = f"## Unreleased\n\n{dated}\n\n"
    if body:
        block = f"## Unreleased\n\n{dated}\n\n{body}\n\n"
        notes = f"{dated}\n\n{body}\n"
    updated = changelog[: heading.start()].rstrip("\n") + "\n\n" + block
    return updated + changelog[end:].lstrip("\n"), notes


def prepare(root: Path, spec: str, day: str | None) -> tuple[str, str]:
    version = bump_version(manifest_version(root, "version"), spec)
    when = day or datetime.now(timezone.utc).date().isoformat()
    changelog, release_notes = move_unreleased(
        read_text(root / "CHANGELOG.md"), version, when
    )
    pyproject = read_text(root / "pyproject.toml")
    table = re.search(r"(?ms)^\[project\][^\[]*", pyproject)
    if table is None:
        die("pyproject.toml has no [project] table.")
    pyproject = (
        pyproject[: table.start()]
        + replace_version(table.group(0), "version", version)
        + pyproject[table.end() :]
    )
    write_text(root / "pyproject.toml", pyproject)
    docs = replace_version(read_text(root / "docs" / "conf.py"), "release", version)
    write_text(root / "docs" / "conf.py", docs)
    write_text(root / "CHANGELOG.md", changelog)
    return version, release_notes


def version_from_args(args: argparse.Namespace) -> str | None:
    if args.branch:
        match = re.fullmatch(r"release/(\d+\.\d+\.\d+)", args.branch.strip())
        return None if match is None else canonical(match.group(1))
    return canonical(args.version) if args.version else None


def main(argv: list[str] | None = None) -> int:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--root", default=".")
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_cmd = sub.add_parser("prepare", parents=[shared])
    prepare_cmd.add_argument("--spec", required=True)
    prepare_cmd.add_argument("--date")
    prepare_cmd.add_argument("--notes-file")
    notes = sub.add_parser("notes", parents=[shared])
    notes.add_argument("--version", required=True)
    check_cmd = sub.add_parser("check", parents=[shared])
    check_cmd.add_argument("--version")
    check_cmd.add_argument("--branch")
    args = parser.parse_args(argv)
    root = Path(args.root)
    if args.command == "prepare":
        version, release_notes = prepare(root, args.spec, args.date)
        if args.notes_file:
            write_text(Path(args.notes_file), release_notes)
        print(version)
    elif args.command == "notes":
        sys.stdout.write(
            notes_for(read_text(root / "CHANGELOG.md"), canonical(args.version))
        )
    else:
        check(root, version_from_args(args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
