# Releasing

Merging a pull request from `release/X.Y.Z` into `main` publishes the package and creates tag `vX.Y.Z` plus a GitHub Release. Nothing in this flow auto-merges.

## Cut a release

1. On `main`, write the notes under `## Unreleased` in `CHANGELOG.md` and merge them.
2. Actions → **Prepare release** → **Run workflow** on `main`.
3. Set **version** to `X.Y.Z`, or to `patch`, `minor`, or `major`.
4. The workflow bumps `pyproject.toml` and `docs/conf.py`, moves Unreleased to `## X.Y.Z - YYYY-MM-DD`, runs the release checks, and builds the sdist and wheel. It then opens a pull request titled `Release X.Y.Z` from `release/X.Y.Z`. The body is that changelog section.
5. Merge the pull request into `main`.

A pull request opened with `GITHUB_TOKEN` does not start `pull_request` workflows, so Prepare release runs the checks before it pushes. A release pull request opened by hand uses the same publish path: branch `release/X.Y.Z`, both version manifests, and a dated changelog section.

## What runs

### Prepare release

`.github/workflows/prepare-release.yml` on `workflow_dispatch`, from `main`, runner `ubuntu-24.04`.

Version manifests:

- `pyproject.toml` field `version`
- `docs/conf.py` field `release`

The Unreleased section must already contain the notes. The script does not invent an empty section.

### Release check

`.github/workflows/release-check.yml` runs on pull requests to `main`. It checks that the version manifests match and that `CHANGELOG.md` has `## X.Y.Z - YYYY-MM-DD` for that version. A `release/*` branch name must match the version. It builds the sdist and wheel.

Don't make Release check a required check: release PRs are opened with GITHUB_TOKEN, so it doesn't run on them unless you close and reopen the PR.

### Publish

A push to `main` runs `.github/workflows/publish.yml`. The **lookup** job reads the pull request for that commit (`merged_at` set, base `main`, same repository, head `release/X.Y.Z`). Any other push leaves the version output empty. The **publish** job then builds the package and uploads it to PyPI with trusted publishing (OIDC). A version that is already on PyPI fails the upload. The **github-release** job runs `gh release view vX.Y.Z` or creates that release on `$GITHUB_SHA` with title `vX.Y.Z`. The notes are the changelog section.

## One-time owner setup

Do this before the next `release/*` merge. This change does not edit repository or PyPI settings.

1. On PyPI, confirm the existing trusted publisher for scrapy-proxy-headers has:
   - Owner: `proxymesh`
   - Repository: `scrapy-proxy-headers`
   - Workflow: `publish.yml`
   - Environment: blank
   If Environment is set (for example `pypi`), edit it to blank.
2. Allow GitHub Actions to create pull requests (Settings → Actions → General → Workflow permissions). Dependabot auto-merge already needs that.
3. After the first successful trusted publish, delete the old `pypi` and `testpypi` GitHub environments if they still exist, and delete any PyPI token secret stored on the repository.

## Tags

Tags are `vX.Y.Z`. Existing tags `v0.1.2` through `v0.2.2` already use that form and stay as they are.
