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
  scripts=()
  for s in "$ROOT"/scripts/hooks/tests/test_*.sh "$ROOT"/scripts/tests/test_*.sh; do
    if [[ -f "$s" ]]; then
      scripts+=("$s")
    fi
  done
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

pids=()
script_count=${#scripts[@]}

for i in "${!scripts[@]}"; do
  script="${scripts[$i]}"
  (
    set +e
    bash "$script" > "$tmp_dir/out.$i" 2>&1
    rc=$?
    echo "$rc" > "$tmp_dir/rc.$i"
    exit "$rc"
  ) &
  pids+=("$!")
done

# Wait for all background runs to complete without letting set -e abort parent
for i in "${!pids[@]}"; do
  pid="${pids[$i]}"
  set +e
  wait "$pid"
  wait_rc=$?
  set -e
  if [[ ! -s "$tmp_dir/rc.$i" ]]; then
    echo "$wait_rc" > "$tmp_dir/rc.$i"
  fi
done

failed_suites=0
total_passed=0
total_failed=0
suite_summaries=()
failed_suite_names=()

for i in "${!scripts[@]}"; do
  script="${scripts[$i]}"
  rel_path="${script#"$ROOT"/}"
  out="$tmp_dir/out.$i"
  rc="$(cat "$tmp_dir/rc.$i")"

  if [[ ! -f "$out" ]]; then
    touch "$out"
  fi

  if [[ "$rc" -gt 128 ]]; then
    echo "Suite was terminated by signal $((rc - 128)) (exit: $rc)" >> "$out"
  elif [[ "$rc" -eq 124 ]]; then
    echo "Suite timed out (exit: 124)" >> "$out"
  fi

  echo "================================================================================"
  echo "=== $rel_path (exit: $rc)"
  echo "================================================================================"
  cat "$out"

  # Extract pass/fail summary if present (e.g. "204 passed, 0 failed")
  summary="$(grep -E '[0-9]+ passed, [0-9]+ failed' "$out" | tail -n 1 || true)"
  has_summary=0
  passed=0
  failed=0

  if [[ -n "$summary" ]] && [[ "$summary" =~ ([0-9]+)[[:space:]]+passed,[[:space:]]+([0-9]+)[[:space:]]+failed ]]; then
    passed="${BASH_REMATCH[1]}"
    failed="${BASH_REMATCH[2]}"
    has_summary=1
  fi

  suite_failed=0
  if [[ "$rc" -ne 0 ]]; then
    suite_failed=1
  fi
  if [[ "$has_summary" -eq 0 ]]; then
    suite_failed=1
    failed=$((failed > 0 ? failed : 1))
    echo "ERROR: $rel_path produced no summary line (crashed or exited early)"
  elif [[ "$failed" -gt 0 ]]; then
    suite_failed=1
  fi

  total_passed=$((total_passed + passed))
  total_failed=$((total_failed + failed))

  summary_line="$rel_path: $passed passed, $failed failed (exit $rc)"
  echo "$summary_line"
  suite_summaries+=("$summary_line")

  if [[ "$suite_failed" -ne 0 ]]; then
    failed_suites=$((failed_suites + 1))
    failed_suite_names+=("$rel_path")
  fi
done

echo "================================================================================"
echo "=== Suite Summary:"
for s in "${suite_summaries[@]}"; do
  echo "$s"
done
echo "================================================================================"
echo "=== Test Summary: $script_count suites, $total_passed assertions passed, $total_failed failed"
if [[ "$failed_suites" -gt 0 ]]; then
  echo "=== FAILED: $failed_suites suite(s) failed"
  for name in "${failed_suite_names[@]}"; do
    echo "  - $name"
  done
  exit 1
else
  echo "=== All test suites passed."
  exit 0
fi
