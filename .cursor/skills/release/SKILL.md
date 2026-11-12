---
name: release
description: >-
  Prepares a version bump and changelog entry, opens a PR from branch
  release/VERSION toward main, and leaves the merge to a person. CI publishes
  to PyPI and creates the GitHub Release when that branch merges. Use when
  the user invokes /release, /release VERSION, asks for a release PR, version
  bump, or release automation.
---

# Release (`/release` and optional VERSION)

## When this applies

- User message starts with **`/release`** or **`/release VERSION`** (VERSION optional).
- User asks to cut a release, bump the package version, or open a release PR.

Do not publish, tag, or merge. See `RELEASING.md` for the owner setup and what CI does after merge.

## Preconditions

- Working tree clean (`git status`); stash or commit unrelated work first.
- `gh` CLI authenticated (`gh auth status`).
- Remote `origin` is GitHub.
- Do not enable auto-merge on the release PR.

## Version selection

1. Read the current version from `pyproject.toml` under `[project]` → `version`.
2. If **VERSION was provided**: pass that string as `--spec` (`X.Y.Z`).
3. If **VERSION was omitted**: pass `--spec patch`.

`docs/conf.py` `release` is the other version manifest. `scripts/release_tools.py` updates both, and moves `CHANGELOG.md` `## [Unreleased]` (or `## Unreleased`) to `## [X.Y.Z] - YYYY-MM-DD`.

## Git identity (this repo)

Configure once if needed:

```bash
git config user.email "cursor@proxymesh.com"
git config user.name "Cursor"
```

## Steps

1. **Start from `origin/main`** without committing on `main`:

   ```bash
   git fetch origin main
   git switch --detach origin/main
   ```

2. **Prepare the tree.** `SPEC` is the provided VERSION, or `patch`.

   ```bash
   NEW_VERSION="$(python scripts/release_tools.py prepare \
     --spec "${SPEC}" --notes-file /tmp/release-notes.md)"
   ```

3. **Branch, commit, and push** (never push to `main`):

   ```bash
   git switch -c "release/${NEW_VERSION}"
   git add pyproject.toml docs/conf.py CHANGELOG.md
   git commit -m "chore: prepare release ${NEW_VERSION}"
   git push -u origin "HEAD:release/${NEW_VERSION}"
   ```

4. **Open the PR** into `main`. Do not run `gh pr merge` and do not pass `--auto`.

   ```bash
   gh pr create --base main --head "release/${NEW_VERSION}" \
     --title "Release ${NEW_VERSION}" \
     --body-file /tmp/release-notes.md
   ```

5. **Stop.** A person merges after **Release check** is green. Merging runs **Publish to PyPI**, which publishes with trusted publishing and creates tag `v${NEW_VERSION}` plus a GitHub Release.

The Actions workflow **Prepare release** does steps 2–4 when someone runs it from `main`. Prefer that workflow when a person is cutting the release. Use the commands above when you are doing it from this checkout.

## Quick reference

| Input              | `--spec`   | Branch                         |
|--------------------|------------|--------------------------------|
| `/release`         | `patch`    | `release/` plus the new patch  |
| `/release 1.4.0`   | `1.4.0`    | `release/1.4.0`                |
