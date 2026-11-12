# Releasing

Merging a pull request from `release/X.Y.Z` into `main` is the release. That merge publishes the package and creates tag `vX.Y.Z` plus a GitHub Release. Nothing in this flow auto-merges.

## Cut a release

1. Write the changes under `## [Unreleased]` in `CHANGELOG.md`. A heading written as `## Unreleased` is also accepted.
2. In GitHub, open Actions → **Prepare release** → Run workflow. Run it from `main`.
3. Set the version input to `X.Y.Z`, `patch`, `minor`, or `major`.
4. The workflow bumps the version manifests, moves that Unreleased section to `## [X.Y.Z] - YYYY-MM-DD`, and opens a pull request titled `Release X.Y.Z`. The pull request body is that changelog section. Review it and merge it.

The same pull request can be opened without the workflow. From a clean `main`:

```bash
version="$(python scripts/release_tools.py prepare --spec 1.2.3 --notes-file /tmp/release-notes.md)"
git checkout -b "release/${version}"
git add pyproject.toml docs/conf.py CHANGELOG.md
git commit -m "chore: prepare release ${version}"
git push -u origin "HEAD:release/${version}"
gh pr create --base main --head "release/${version}" \
  --title "Release ${version}" \
  --body-file /tmp/release-notes.md
```

Use `--spec patch` (or `minor` or `major`) instead of `1.2.3` to bump from the current version. Do not enable auto-merge.

Version manifests:

- `pyproject.toml`, `[project].version`
- `docs/conf.py`, `release`

If `CHANGELOG.md` has no Unreleased section, Prepare release still opens the pull request and warns that the new section is empty. Add the notes on that branch before merging.

## What runs

### Prepare release

`workflow_dispatch` on `.github/workflows/prepare-release.yml`. It runs the version and changelog check and builds the sdist and wheel before it opens the pull request. It does not publish and it does not merge.

GitHub does not start `pull_request` workflows for a pull request that the Actions token opened. The prepare job is the check for that pull request. A pull request opened by a person still runs **Release check**.

### Release check

On every pull request into `main`, the **Release check** job in `.github/workflows/publish.yml` lints the release workflows, dry-runs the version and changelog checks, and builds the sdist and wheel (`twine check` included). On a `release/X.Y.Z` pull request it also checks that the branch name, every version manifest, and a dated changelog section all name that version.

A dated section looks like `## [0.2.2] - 2026-11-09`. Brackets around the version are optional.

### Publish to PyPI

When a `release/X.Y.Z` pull request from this repository merges into `main`, the same workflow publishes with PyPI trusted publishing (OIDC). The publish job uses the GitHub environment `release` and does not get permission to push tags. A following job creates tag `vX.Y.Z` and a GitHub Release whose notes are that changelog section.

Re-running a finished publish does not upload the package again. If the version is already on PyPI and this merge does not already have the GitHub release, the job fails and names the PyPI URL. A tag that already points at a different commit fails the same way.

Manual GitHub Releases and the old TestPyPI dispatch do not publish. Publishing happens only from this merge.

## One-time owner setup

1. Create a GitHub environment named `release` (Settings → Environments). A required reviewer is optional. The environment needs no secrets.
2. On PyPI, for the `scrapy-proxy-headers` project, set the trusted publisher to owner `proxymesh`, repository `scrapy-proxy-headers`, workflow `publish.yml`, and environment `release`. Publishing fails until this matches. The previous workflow used the environment name `pypi`.
3. Allow GitHub Actions to create pull requests (Settings → Actions → General → Workflow permissions → Allow GitHub Actions to create and approve pull requests). Dependabot auto-merge already needs this, so it may already be on.
4. After a publish through the `release` environment succeeds, delete the old `pypi` and `testpypi` environments if nothing else uses them. These workflows do not use a long-lived PyPI token. Delete a leftover `PYPI_API_TOKEN` or `PYPI_TOKEN` secret if one is stored.
5. Optional: require the **Release check** status check on `main`.

## Tags

Tags are `vX.Y.Z`. Existing tags already use that form (`v0.1.2` through `v0.2.2`) and are left as they are.
