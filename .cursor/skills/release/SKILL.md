---
name: release
description: >-
  Prepares a version bump in pyproject.toml, opens a PR from branch release/VERSION
  toward main with auto-merge, and coordinates with CI that publishes a GitHub Release
  when that branch merges. Use when the user invokes /release, /release VERSION, asks
  for a release PR, version bump, or release automation.
---

# Release (`/release` and optional VERSION)

## When this applies

- User message starts with **`/release`** or **`/release VERSION`** (VERSION optional).
- User asks to cut a release, bump the package version, or open a release PR with auto-merge.

## Preconditions

- Working tree clean (`git status`); stash or commit unrelated work first.
- `gh` CLI authenticated (`gh auth status`).
- Remote `origin` is GitHub.
- Repository allows **auto-merge** (Settings → General → Pull Requests → Allow auto-merge). If auto-merge is unavailable, open the PR anyway and tell the user to merge manually after checks pass.

## Version selection

1. Read the current version from `pyproject.toml` under `[project]` → `version` (PEP 440 / semver `MAJOR.MINOR.PATCH`).
2. If **VERSION was provided**: set the new version to that string (must match `^\d+\.\d+\.\d+` unless the project already uses a different scheme—then follow existing `pyproject.toml` format).
3. If **VERSION was omitted**: bump the **patch** segment only (e.g. `0.2.1` → `0.2.2`). If the current value is not `x.y.z`, stop and ask the user for an explicit VERSION.

## Git identity (this repo)

Configure once if needed:

```bash
git config user.email "cursor@proxymesh.com"
git config user.name "Cursor"
```

## Steps

1. **Sync main**

   ```bash
   git fetch origin main
   ```

2. **Compute** `NEW_VERSION` (per rules above). **Branch name** is `release/${NEW_VERSION}` (no `v` prefix in the branch name).

3. **Create branch from latest main**

   ```bash
   git checkout -B "release/${NEW_VERSION}" origin/main
   ```

4. **Edit** `pyproject.toml`: set `version = "NEW_VERSION"` in `[project]`.

5. **Commit and push** (never push to `main`; push only the release branch)

   ```bash
   git add pyproject.toml
   git commit -m "chore: bump version to ${NEW_VERSION}"
   git push -u origin "release/${NEW_VERSION}"
   ```

6. **Open PR** into `main` with a short body (no Cursor boilerplate). Example:

   ```bash
   gh pr create --base main --head "release/${NEW_VERSION}" \
     --title "Release ${NEW_VERSION}" \
     --body "Bumps the package version to ${NEW_VERSION} for release."
   ```

7. **Enable auto-merge** after the PR exists. In non-interactive mode, `gh` requires an explicit merge strategy with `--auto` (use the repository default: usually **`--merge`** for a merge commit, or **`--squash`** / **`--rebase`** if that is what the repo uses).

   ```bash
   gh pr merge <PR_NUMBER_OR_URL> --auto --merge
   ```

   If `--auto` fails (permissions, auto-merge disabled, or pending checks), leave the PR open and report the error; the user can merge manually after CI passes. You can poll with `gh pr checks <PR_NUMBER_OR_URL> --watch` then retry `gh pr merge ... --auto --merge`, or merge manually.

## After merge

Merging the PR into `main` runs **Release on merge** (`.github/workflows/github_release_on_release_branch_merge.yml`), which creates a **GitHub Release** for tag `v{version}` from the merge commit. Because releases created with the default `GITHUB_TOKEN` do not trigger other workflows, **Publish to PyPI** (`publish.yml`) is also started via **`workflow_run`** when that release workflow finishes. Manual or API-created releases still match the `release: published` trigger on `publish.yml`.

## Quick reference

| Input              | Result                                      |
|--------------------|---------------------------------------------|
| `/release`         | Patch bump, branch `release/x.y.(z+1)`      |
| `/release 1.4.0`   | Version `1.4.0`, branch `release/1.4.0`     |
