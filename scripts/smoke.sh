#!/bin/bash
# End-to-end smoke test against the running game: doctor, then every read command with --json.
# Prints one line per command; exits non-zero at the first failure.
set -uo pipefail
cd "$(dirname "$0")/../fm"
run() {
  local out
  if out=$(uv run --quiet fm --json "$@" 2>/dev/null) &&
     printf '%s' "$out" | python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin).get("ok") else 1)'; then
    echo "ok   $*"
  else
    echo "FAIL $*"
    printf '%s\n' "$out" | head -c 400
    echo
    exit 1
  fi
}
run doctor
run game status
run club budget
run squad list
run squad watch
run squad depth
run staff search --role scout --top 5
run staff slots
run staff vacancies --top 2
run players search --max 50 --affordable
run players targets --max 200 --top 3
run training show
run training load
echo "smoke: all ok"
