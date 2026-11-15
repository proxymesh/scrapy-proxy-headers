#!/usr/bin/env bash
# Check that pyproject.toml and docs/conf.py carry the same version, and that
# a release/X.Y.Z branch carries version X.Y.Z. scripts/lint.sh runs this;
# on pull requests the branch comes from GITHUB_HEAD_REF.

set -euo pipefail

err() {
  echo "$*" >&2
}

main() {
  cd "$(git rev-parse --show-toplevel)"
  local version docs branch
  version="$(sed -nE 's/^version = "([^"]+)"$/\1/p' pyproject.toml)"
  docs="$(sed -nE "s/^release = '([^']+)'$/\1/p" docs/conf.py)"
  branch="${GITHUB_HEAD_REF:-$(git rev-parse --abbrev-ref HEAD)}"
  if [[ -z "${version}" || "${docs}" != "${version}" ]]; then
    err "pyproject.toml version '${version}' != docs/conf.py release '${docs}'"
    exit 1
  fi
  if [[ "${branch}" == release/* && "${branch#release/}" != "${version}" ]]; then
    err "branch ${branch} != pyproject.toml version ${version}"
    exit 1
  fi
}

main "$@"
