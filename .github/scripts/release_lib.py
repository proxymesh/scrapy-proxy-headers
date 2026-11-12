"""Bump version manifests and print the changelog notes for a release."""

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
DATED = re.compile(
    r"^## ((?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)) - (\d{4}-\d{2}-\d{2})\s*$"
)


def assignment(text, key):
    pattern = re.compile(
        rf"^(?P<pre>{key}\s*=\s*['\"])(?P<value>[^'\"]*)['\"]\s*$",
        re.MULTILINE,
    )
    found = list(pattern.finditer(text))
    if len(found) != 1:
        raise SystemExit(f"expected one {key} assignment, found {len(found)}")
    return found[0]


def parse_version(value):
    if VERSION.fullmatch(value) is None:
        raise SystemExit(f"version {value!r} must look like X.Y.Z")
    return tuple(int(part) for part in value.split("."))


def next_version(current, spec):
    spec = spec.strip()
    major, minor, patch = parse_version(current)
    name = spec.lower()
    if name == "patch":
        return f"{major}.{minor}.{patch + 1}"
    if name == "minor":
        return f"{major}.{minor + 1}.0"
    if name == "major":
        return f"{major + 1}.0.0"
    new = parse_version(spec)
    if new <= (major, minor, patch):
        raise SystemExit(f"version {spec} is not newer than {current}")
    return ".".join(str(part) for part in new)


def span(lines, pred):
    starts = [index for index, line in enumerate(lines) if pred(line)]
    if len(starts) != 1:
        raise SystemExit(f"expected one changelog heading, found {len(starts)}")
    start = starts[0]
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    return start, end


def check():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    docs = (ROOT / "docs" / "conf.py").read_text(encoding="utf-8")
    version = assignment(pyproject, "version").group("value")
    docs_version = assignment(docs, "release").group("value")
    parse_version(version)
    if docs_version != version:
        raise SystemExit(
            f"docs/conf.py release is {docs_version}; pyproject version is {version}."
        )
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    dates = [
        match.group(2)
        for line in changelog.splitlines()
        if (match := DATED.match(line.strip())) and match.group(1) == version
    ]
    for day in dates:
        datetime.strptime(day, "%Y-%m-%d")
    if len(dates) != 1:
        raise SystemExit(f"CHANGELOG.md needs one '## {version} - YYYY-MM-DD' section.")
    head = os.environ.get("GITHUB_HEAD_REF") or os.environ.get("HEAD_REF") or ""
    if head.startswith("release/") and head != f"release/{version}":
        raise SystemExit(f"branch {head} does not match version {version}.")
    print(f"Version {version} matches the manifests and CHANGELOG.md.")


def write_assignment(path, key, new):
    text = path.read_text(encoding="utf-8")
    match = assignment(text, key)
    path.write_text(
        text[: match.start("value")] + new + text[match.end("value") :],
        encoding="utf-8",
        newline="\n",
    )


def bump():
    spec = os.environ.get("VERSION_INPUT", "").strip()
    if not spec:
        raise SystemExit("Set version to X.Y.Z, patch, minor, or major.")
    py_path = ROOT / "pyproject.toml"
    docs_path = ROOT / "docs" / "conf.py"
    log_path = ROOT / "CHANGELOG.md"
    pyproject = py_path.read_text(encoding="utf-8")
    new = next_version(assignment(pyproject, "version").group("value"), spec)
    day = datetime.now(timezone.utc).date().isoformat()
    lines = log_path.read_text(encoding="utf-8").splitlines(keepends=True)
    start, end = span(lines, lambda line: line.strip() == "## Unreleased")
    body = "".join(lines[start + 1 : end])
    if not body.strip():
        raise SystemExit("The Unreleased section in CHANGELOG.md is empty.")
    heading = f"## {new} - {day}\n"
    lines[start] = "## Unreleased\n\n" + heading
    updated = "".join(lines)
    write_assignment(py_path, "version", new)
    write_assignment(docs_path, "release", new)
    log_path.write_text(updated, encoding="utf-8", newline="\n")
    notes_file = os.environ.get("NOTES_FILE")
    if notes_file:
        Path(notes_file).write_text(
            (heading + body).strip() + "\n",
            encoding="utf-8",
            newline="\n",
        )
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write(f"version={new}\n")
    print(new)


def notes():
    version = assignment(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
        "version",
    ).group("value")
    lines = (
        (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").splitlines(keepends=True)
    )

    def is_version(line):
        match = DATED.match(line.strip())
        return match is not None and match.group(1) == version

    start, end = span(lines, is_version)
    sys.stdout.write("".join(lines[start:end]).strip() + "\n")


def main(argv):
    command = argv[1] if len(argv) > 1 else ""
    if command == "bump":
        bump()
    elif command == "check":
        check()
    elif command == "notes":
        notes()
    else:
        raise SystemExit("usage: release_lib.py bump|check|notes")


if __name__ == "__main__":
    main(sys.argv)
