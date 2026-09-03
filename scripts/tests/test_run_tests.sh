#!/usr/bin/env bash
# Tests for scripts/run-tests.sh — the parallel shell test runner.
# Covers all-green suites, suites with failing assertions, suites exiting early,
# and handling killed/signaled suites.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
RUN_TESTS="$ROOT/scripts/run-tests.sh"

TMP="$(mktemp -d)"; trap 'rm -rf -- "$TMP"' EXIT
pass=0; fail=0
ok(){ printf 'ok   %s\n' "$1"; pass=$((pass+1)); }
no(){ printf 'FAIL %s\n' "$1"; fail=$((fail+1)); }
check(){ if "$@"; then ok "$name"; else no "$name"; fi; }

contains(){
  local file="$1" pattern="$2"
  grep -Eq "$pattern" "$file"
}

# --- Case 1: All green suites ------------------------------------------------
cat <<'EOF' > "$TMP/green_a.sh"
#!/usr/bin/env bash
echo "green_a running"
printf '\n2 passed, 0 failed\n'
exit 0
EOF

cat <<'EOF' > "$TMP/green_b.sh"
#!/usr/bin/env bash
echo "green_b running"
printf '\n3 passed, 0 failed\n'
exit 0
EOF

chmod +x "$TMP"/green_*.sh

set +e
bash "$RUN_TESTS" "$TMP/green_a.sh" "$TMP/green_b.sh" > "$TMP/case1.out" 2>&1
c1_rc=$?
set -e

name="case1: all green suites exit 0"
check [ "$c1_rc" -eq 0 ]

name="case1: all green output includes per-suite summary lines"
check contains "$TMP/case1.out" "green_a\.sh: 2 passed, 0 failed \(exit 0\)"
check contains "$TMP/case1.out" "green_b\.sh: 3 passed, 0 failed \(exit 0\)"

name="case1: all green output includes overall pass message"
check contains "$TMP/case1.out" "All test suites passed"

# --- Case 2: One suite with an injected failing assertion -------------------
cat <<'EOF' > "$TMP/failing_assertion.sh"
#!/usr/bin/env bash
echo "failing_assertion running"
echo "FAIL: assertion_xyz failed: expected foo got bar"
printf '\n1 passed, 1 failed\n'
exit 1
EOF
chmod +x "$TMP/failing_assertion.sh"

set +e
bash "$RUN_TESTS" "$TMP/green_a.sh" "$TMP/failing_assertion.sh" > "$TMP/case2.out" 2>&1
c2_rc=$?
set -e

name="case2: suite with failing assertion exits non-zero"
check [ "$c2_rc" -ne 0 ]

name="case2: suite with failing assertion prints captured log with error"
check contains "$TMP/case2.out" "FAIL: assertion_xyz failed: expected foo got bar"

name="case2: suite with failing assertion names failing suite and reports exit rc"
check contains "$TMP/case2.out" "failing_assertion\.sh: 1 passed, 1 failed \(exit 1\)"

name="case2: suite with failing assertion reported in failed suites list"
check contains "$TMP/case2.out" "FAILED: 1 suite\(s\) failed"
check contains "$TMP/case2.out" "failing_assertion\.sh"

# --- Case 3: One suite exits early via exit 3 before summary ----------------
cat <<'EOF' > "$TMP/early_exit.sh"
#!/usr/bin/env bash
echo "early_exit started doing work"
exit 3
EOF
chmod +x "$TMP/early_exit.sh"

set +e
bash "$RUN_TESTS" "$TMP/green_a.sh" "$TMP/early_exit.sh" > "$TMP/case3.out" 2>&1
c3_rc=$?
set -e

name="case3: early exit suite causes runner to exit non-zero"
check [ "$c3_rc" -ne 0 ]

name="case3: early exit suite prints captured log"
check contains "$TMP/case3.out" "early_exit started doing work"

name="case3: early exit suite named with failure and exit 3"
check contains "$TMP/case3.out" "early_exit\.sh.*exit 3"

name="case3: early exit suite counted as failed suite"
check contains "$TMP/case3.out" "FAILED: 1 suite\(s\) failed"

# --- Case 4: Suite killed by signal (e.g. SIGKILL / 137) ---------------------
cat <<'EOF' > "$TMP/killed.sh"
#!/usr/bin/env bash
echo "about to be killed"
kill -9 $$
EOF
chmod +x "$TMP/killed.sh"

set +e
bash "$RUN_TESTS" "$TMP/killed.sh" > "$TMP/case4.out" 2>&1
c4_rc=$?
set -e

name="case4: killed suite causes runner to exit non-zero"
check [ "$c4_rc" -ne 0 ]

name="case4: killed suite names suite in failure summary"
check contains "$TMP/case4.out" "killed\.sh"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[[ $fail -eq 0 ]]
