#!/usr/bin/env bash
# Orquestra QA, subida, testes e teardown, preservando a primeira falha.

set -u

runner="${1:-make}"

cleanup() {
  local status="$?"
  local teardown_status
  trap - EXIT
  "${runner}" infra-down
  teardown_status="$?"
  if (( status != 0 )); then
    exit "${status}"
  fi
  exit "${teardown_status}"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

"${runner}" infra-qa || exit "$?"
"${runner}" infra-up || exit "$?"
"${runner}" infra-local-test || exit "$?"
