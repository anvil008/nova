# Local integration and one publication PR

## Status

Accepted.

## Context

Child results remained in workspaces, while separate publication branches and superseded PRs accumulated. Remote PR protection was confused with the timing of verified local integration. Agy lacked the parent reminder installed in Codex/Claude.

## Decision

The parent integrates each ready, verified task result into local main promptly and safely synchronizes the primary checkout. Intermediate JJ work stays local. Each authorized publication uses one integration bookmark and PR for accumulated results, preserving newer local descendants when reconciling a remote squash/rebase merge. Completion includes verifying remote branch cleanup; superseded PR branches require integration evidence and no active consumers before deletion.

Hooks remain advisory and bounded. They never merge, push, delete branches, or treat child exit as verification. Codex/Claude retain their child-stop reminder. Agy observes successful invoke_subagent calls through PostToolUse and continues once on a normal fully idle Stop, consuming a conversation-scoped marker first. No undocumented SubagentStop or SessionEnd contract is assumed. Automatic Flow tracking stays disabled.

## Consequences

Local main may lead remote main. Parents must serialize integration, preserve active work, and account for squash/rebase commit mappings. Remote main still receives changes only through PRs. Agy reminders can follow read-only delegation and require the parent to determine whether integration is needed. Unconsumed Agy markers may survive until the same conversation resumes. Hooks cannot guarantee delivery or replace review; workflow instructions and final evidence remain authoritative.
