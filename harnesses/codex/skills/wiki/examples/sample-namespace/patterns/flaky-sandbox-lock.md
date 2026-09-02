# Flaky sandbox lock

One failure mode or successful strategy of this project. Evidence accumulates below;
nothing already written here is rewritten to say something different.

## Evidence

- 2026-08-31 — `2026-08-31-build-wave-1` — The integrator timed out waiting on /var/lock/checkout-api.lock with no other holder reported; a plain re-run went green, so the lock is stale rather than contended.
- 2026-08-31 — `2026-08-31-build-wave-2` — The same lock starved a second wave on a slower runner, so the fix belongs in the harness that takes the lock, not in a per-wave retry.
