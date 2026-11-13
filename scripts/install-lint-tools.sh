#!/usr/bin/env bash
# Install the pinned lint tools into ~/.local/bin (linux x86_64).
# CI and .cursor/environment.json both run this script.

set -euo pipefail

readonly BIN_DIR="${HOME}/.local/bin"
readonly GH="https://github.com"

err() {
  echo "$*" >&2
}

# Download a URL to a file and check its sha256.
fetch() {
  local url="$1"
  local sha="$2"
  local dest="$3"
  curl -fsSL -o "${dest}" "${url}"
  echo "${sha}  ${dest}" | sha256sum -c --quiet - || {
    err "checksum mismatch: ${url}"
    exit 1
  }
}

install_actionlint() {
  local version="1.7.12"
  local sha="8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8"
  fetch \
    "${GH}/rhysd/actionlint/releases/download/v${version}/actionlint_${version}_linux_amd64.tar.gz" \
    "${sha}" "${TMP}/actionlint.tar.gz"
  tar -xzf "${TMP}/actionlint.tar.gz" -C "${BIN_DIR}" actionlint
}

install_shellcheck() {
  local version="0.11.0"
  local sha="b7af85e41cc99489dcc21d66c6d5f3685138f06d34651e6d34b42ec6d54fe6f6"
  fetch \
    "${GH}/koalaman/shellcheck/releases/download/v${version}/shellcheck-v${version}.linux.x86_64.tar.gz" \
    "${sha}" "${TMP}/shellcheck.tar.gz"
  tar -xzf "${TMP}/shellcheck.tar.gz" -C "${TMP}"
  install -m 755 "${TMP}/shellcheck-v${version}/shellcheck" "${BIN_DIR}"
}

install_shfmt() {
  local version="3.14.1"
  local sha="76e77641faa025814b77f153b29796b8e6fa2fca03e0c76a691608b86c7ea7bf"
  fetch \
    "${GH}/mvdan/sh/releases/download/v${version}/shfmt_v${version}_linux_amd64" \
    "${sha}" "${TMP}/shfmt"
  install -m 755 "${TMP}/shfmt" "${BIN_DIR}/shfmt"
}

install_python_tools() {
  python3 -m pip install --user --quiet --break-system-packages \
    "ruff==0.17.5" "zizmor==1.32.0"
}

main() {
  TMP="$(mktemp -d)"
  trap 'rm -rf "${TMP}"' EXIT
  mkdir -p "${BIN_DIR}"
  install_actionlint
  install_shellcheck
  install_shfmt
  install_python_tools
}

main "$@"
