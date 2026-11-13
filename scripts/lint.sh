#!/usr/bin/env bash
# Run every repo lint check. CI, the stop hook and agents all run this.
# Install the tools first with scripts/install-lint-tools.sh.

set -euo pipefail

failed=()

err() {
  echo "$*" >&2
}

# Run a check and remember its name if it fails.
check() {
  local name="$1"
  shift
  "$@" || failed+=("${name}")
}

main() {
  export PATH="${HOME}/.local/bin:${PATH}"
  cd "$(git rev-parse --show-toplevel)"
  local -a sh_files
  mapfile -t sh_files < <(git ls-files -co --exclude-standard '*.sh')

  check actionlint actionlint
  # Skip legacy release workflows; zizmor only on workflows this branch changes.
  local -a wf=()
  local path base="origin/main"
  for path in .github/workflows/*; do
    if [[ "$path" == .github/workflows/publish.yml ]] ||
      [[ "$path" == .github/workflows/github_release_on_release_branch_merge.yml ]]; then
      continue
    fi
    if git rev-parse --verify --quiet "${base}" >/dev/null &&
      git cat-file -e "${base}:${path}" 2>/dev/null &&
      git diff --quiet "${base}" -- "$path"; then
      continue
    fi
    wf+=("$path")
  done
  if ((${#wf[@]} > 0)); then
    check zizmor zizmor --quiet --offline "${wf[@]}"
  fi
  check shellcheck shellcheck "${sh_files[@]}"
  check shfmt shfmt -d -i 2 -ci "${sh_files[@]}"
  check ruff ruff check

  if ((${#failed[@]} > 0)); then
    err "lint failed: ${failed[*]}"
    exit 1
  fi
}

main "$@"
