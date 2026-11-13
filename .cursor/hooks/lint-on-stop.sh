#!/usr/bin/env bash
# Cursor stop hook: when scripts/lint.sh fails, send its output back to the
# agent as a follow-up. hooks.json caps the re-prompts with loop_limit.

set -euo pipefail

main() {
  local output
  if output="$(scripts/lint.sh 2>&1 </dev/null)"; then
    echo '{}'
    return
  fi
  python3 -c 'import json, sys
print(json.dumps({"followup_message": "scripts/lint.sh failed:\n" + sys.stdin.read()[-4000:]}))' \
    <<<"${output}"
}

main "$@"
