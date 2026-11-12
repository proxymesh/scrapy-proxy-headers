# Releasing

Merging a pull request from `release/X.Y.Z` into `main` publishes the package and creates tag `vX.Y.Z` plus a GitHub Release. Nothing in this flow auto-merges.

## Cut a release

1. Write the changes under `## Unreleased` in `CHANGELOG.md`. `## [Unreleased]` is also accepted.
2. In GitHub, open Actions → **Prepare release** → Run workflow, from `main`.
3. Set the version input to `X.Y.Z`, `patch`, `minor`, or `major`.
4. The workflow bumps the version manifests, moves that section to `## X.Y.Z - YYYY-MM-DD`, and opens a pull request titled `Release X.Y.Z`. Review it and merge it.

Version manifests are `pyproject.toml` `[project].version` and `docs/conf.py` `release`.

The same pull request can be opened by hand:

```bash
version="$(python scripts/release_version.py prepare --spec patch --notes-file /tmp/release-notes.md)"
git switch -c "release/${version}"
git add -- pyproject.toml docs/conf.py CHANGELOG.md
git commit -m "chore: prepare release ${version}"
git push -u origin "HEAD:release/${version}"
gh pr create --base main --head "release/${version}" \
  --title "Release ${version}" --body-file /tmp/release-notes.md
```

Do not enable auto-merge. If the changelog has no Unreleased section, the new notes are empty; add them on the release branch before merging.

## What runs

### Prepare release

`workflow_dispatch` on `.github/workflows/prepare-release.yml`. Before it pushes, it checks that both manifests and a dated changelog section name the new version, and it builds the sdist and wheel. It does not publish.

GitHub does not start `pull_request` workflows for a pull request that the Actions token opened, so this job is the check for that pull request.

### Release check

On every pull request into `main`, `.github/workflows/release-check.yml` runs the same version and changelog check and builds the package. A `release/X.Y.Z` head must have a dated section. Other branches only need the two manifests to match.

A dated section is `## X.Y.Z - YYYY-MM-DD`. An existing heading such as `## [0.2.2] - 2026-11-09` also counts.

### Publish

A push to `main` runs `.github/workflows/publish.yml`. It asks GitHub which pull request merged as that commit (`gh api repos/$GITHUB_REPOSITORY/commits/$GITHUB_SHA/pulls`). Any other push skips the upload. A `release/X.Y.Z` merge builds the package and publishes with PyPI trusted publishing. The publish job uses the `release` environment and cannot push tags. PyPI rejects a version that is already there. The next job creates tag `vX.Y.Z` and the GitHub Release from the changelog section (`gh release view` or `gh release create`).

## One-time owner setup

1. Create a GitHub environment named `release` (Settings → Environments). No secrets. Leave required reviewers off: this job starts on every push to `main` and exits before building when the commit is not a release merge.
2. On PyPI, for `scrapy-proxy-headers`, set the trusted publisher to owner `proxymesh`, repository `scrapy-proxy-headers`, workflow `publish.yml`, and environment `release`. The previous environment name was `pypi`.
3. Allow GitHub Actions to create pull requests (Settings → Actions → General → Workflow permissions). Dependabot auto-merge already needs this.
4. After one publish through `release` succeeds, delete the old `pypi` and `testpypi` environments if nothing else uses them. Delete a leftover PyPI token secret if one is stored. This flow does not use one.
5. Optional: require the **Release check** status check on `main`.

## Tags

Tags are `vX.Y.Z`. Existing tags already use that form (`v0.1.2` through `v0.2.2`) and are left as they are.
