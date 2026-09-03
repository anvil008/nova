#!/usr/bin/env bash
# Runs shell test scripts concurrently and aggregates results.
# Preserves individual script output and reports per-suite pass/fail counts.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

# Discover scripts or accept explicit script list
if [[ $# -gt 0 ]]; then
  scripts=("$@")
else
  scripts=(
    "$ROOT"/scripts/hooks/tests/test_*.sh
    "$ROOT"/scripts/tests/test_*.sh
  )
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

pids=()
script_count=${#scripts[@]}

for i in "${!scripts[@]}"; do
  script="${scripts[$i]}"
  (
    bash "$script" > "$tmp_dir/out.$i" 2>&1
    echo $? > "$tmp_dir/rc.$i"
  ) &
  pids+=("$!")
done

# Wait for all background runs to complete
for pid in "${pids[@]}"; do
  wait "$pid"
done

failed_suites=0
total_passed=0
total_failed=0

for i in "${!scripts[@]}"; do
  script="${scripts[$i]}"
  rel_path="${script#"$ROOT"/}"
  rc="$(cat "$tmp_dir/rc.$i")"
  out="$tmp_dir/out.$i"

  echo "================================================================================"
  echo "=== $rel_path (exit: $rc)"
  echo "================================================================================"
  cat "$out"

  # Extract pass/fail summary if present (e.g. "204 passed, 0 failed")
  summary="$(grep -E '^[0-9]+ passed, [0-9]+ failed' "$out" | tail -n 1 || true)"
  if [[ -n "$summary" ]]; then
    passed="$(echo "$summary" | sed -E 's/^([0-9]+) passed.*/\1/')"
    failed="$(echo "$summary" | sed -E 's/.*, ([0-9]+) failed.*/\1/')"
    total_passed=$((total_passed + passed))
    total_failed=$((total_failed + failed))
  fi

  if [[ "$rc" -ne 0 ]]; then
    failed_suites=$((failed_suites + 1))
  fi
done

echo "================================================================================"
echo "=== Test Summary: $script_count suites, $total_passed assertions passed, $total_failed failed"
if [[ "$failed_suites" -gt 0 ]]; then
  echo "=== FAILED: $failed_suites suite(s) failed"
  exit 1
else
  echo "=== All test suites passed."
  exit 0
fi
