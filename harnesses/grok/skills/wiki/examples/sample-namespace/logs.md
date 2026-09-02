# Evolution log

One line per write to this namespace, oldest first. Appended by `wiki.py`; never
edited.

- 2026-08-31T18:15:01Z init sample-namespace (namespace)
- 2026-08-31T18:15:02Z record 2026-08-31-build-wave-1 (build-wave) — wave 1 accepted after the sandbox lock timed out once
- 2026-08-31T18:15:02Z record 2026-08-31-review-pass-2 (review-pass) — second review pass on the migration change-set
- 2026-08-31T18:15:02Z pattern flaky-sandbox-lock — 2026-08-31-build-wave-1 — The integrator timed out waiting on /var/lock/checkout-api.lock with no other holder reported; a plain re-run went green, so the lock is stale rather than contended.
- 2026-08-31T18:15:02Z pattern seed-the-fixture-before-the-migration — 2026-08-31-review-pass-2 — A migration test that creates its fixture after the migration runs passes vacuously; the review lens caught it, not the suite.
- 2026-08-31T18:15:19Z record 2026-08-31-build-wave-2 (build-wave) — wave 2 accepted; the same lock stalled the slower runner
- 2026-08-31T18:15:19Z pattern flaky-sandbox-lock — 2026-08-31-build-wave-2 — The same lock starved a second wave on a slower runner, so the fix belongs in the harness that takes the lock, not in a per-wave retry.
