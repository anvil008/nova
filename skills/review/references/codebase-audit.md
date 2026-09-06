# Codebase audit

Use this review mode when the request concerns an area or repository rather than a supplied diff. Establish the area and source revision before scanning. Report which paths, interfaces, and lenses were covered; a partial audit cannot establish a clean bill of health for the entire codebase.

Existing failures help interpret findings. Where useful, ask an integrator for the documented baseline checks on the untouched source. Record pre-existing failures and checks that could not run. A red baseline is evidence about the starting state, not permission to repair unrelated code.

A defect needs concrete inputs or state that cause a wrong result, crash, corruption, leak, or security failure. Trace whether that scenario is reachable. Missing defensive checks for impossible states and personal style preferences are not defects. Scope structural observations separately and explain their practical cost.

Use the shared review merge and independent verification protocol. A reviewer that did not originate a candidate tries to refute its scenario against the real code; preserve the evidence for refuted candidates. Reproduction commands and experiments must leave the source unchanged and remain within the request's permitted environment.

Deliver the report before choosing remedies. Offer `/build` for selected verified findings unless review and fix was already authorized. In an authorized fix campaign, carry each concrete failure scenario into build's acceptance criteria and independent test-first implementation. Unknown behavior or an unobservable oracle remains unresolved; do not substitute speculative code changes. Keep unrelated cleanup outside the fix scope.
