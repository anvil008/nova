# Shared skills with native plugin delivery

## Status

Accepted for the repository rewrite on 2026-09-07. Personal installation and publication remain separate actions. Supersedes earlier requirements for a pure orchestrator, mandatory role handoffs, guard/control-plane execution, and maintained per-harness skill copies, including the conflicting portions of ADRs 0007, 0025, 0027, 0028, and 0029. Earlier records remain historical evidence.

## Context

Workcell's previous runtime coupled reusable engineering expertise to multiple generated instruction trees, mandatory specialist handoffs, guard state, and a large packaging/bootstrap surface. The replacement skills were developed and reviewed in templates, with the main conversation retaining task ownership.

## Decision

Promote the shared skills to skills/, persistent guidance to instructions/, optional native helpers to agents/, and the advisory runner to hooks/. Keep future utilities in tools/ when shared; skill-specific scripts stay with their skill.

Build one self-contained native plugin per harness. Packaging copies common sources unchanged and supplies only native manifest, helper, and hook-format differences. Generated bundles are disposable build outputs. Native managers own plugin installation and updates. No mandatory SDK runtime, control plane, acceptance seals, task sidecars, or intermediate helper PRs remain.

Each skill references the bundled common instructions. Persistent project adoption is explicit repo-setup work. Claude plugin-root CLAUDE.md is not auto-loaded. Codex optional helpers are explicit setup resources until plugin helper discovery is established. Agy hook commands are configured against the installed path rather than an assumed environment variable. Hook config is explicit and disabled by default.

## Consequences

One content edit serves all three harnesses. Packages can be relocated without source-checkout symlinks. Native differences are visible rather than hidden behind claimed parity. Optional Codex helper copies require separate updates. CLI discovery tests and hook tests can run without models, but behavior and account/model availability still require native trials. Existing personal installations are unchanged by the build.
