"use strict";

const SOURCE = "source.html?path=";
const iconPaths = {
  flow:'<path d="M4 5h6v5H4zm10 9h6v5h-6zM7 10v6h7M10 7h7v7"/>',
  layers:'<path d="m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5"/>',
  people:'<circle cx="9" cy="7" r="3"/><path d="M3 20v-3a6 6 0 0 1 12 0v3m1-16a3 3 0 0 1 0 6m2 3a5 5 0 0 1 3 4v3"/>',
  shield:'<path d="m12 3 8 3v6c0 4-4 7-8 9-4-2-8-5-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/>',
  file:'<path d="M6 3h8l4 4v14H6V3Zm8 0v5h4M9 12h6m-6 4h6"/>',
  code:'<path d="m8 6-5 6 5 6m8-12 5 6-5 6M14 4l-4 16"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  branch:'<circle cx="6" cy="5" r="2"/><circle cx="18" cy="7" r="2"/><circle cx="6" cy="19" r="2"/><path d="M6 7v10m0-3h5a7 7 0 0 0 7-5"/>',
  box:'<path d="m12 3 9 5v9l-9 5-9-5V8l9-5Zm0 9 9-4M3 8l9 4v10M7 5l10 5"/>',
  search:'<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
  chart:'<path d="M4 3v17h17M8 16v-5m5 5V6m5 10V9"/>',
  launch:'<path d="m12 15-3-3 4-7 8-2-2 8-7 4Zm-3-3-5 1 1-5 8-3m-1 10-1 5 5-1 3-8M3 21l5-5"/>',
  terminal:'<path d="M3 4h18v16H3V4Zm4 5 3 3-3 3m6 0h4"/>',
};
const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${iconPaths[name] || iconPaths.box}</svg>`;
const esc = text => String(text).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const s = (path, line) => ({path, line});
const notes = {
  "1": "Implemented: GREEN binds the base and source digest. Source changes make it stale; a failed attempt removes previous GREEN. Regression tests exercise status and Stop.",
  "2": "Implemented: build_run.py duplicates each source onto the preceding candidate and advances the candidate bookmark explicitly. Original source commits survive; only acceptance advances integration.",
  "3": "Implemented: accepted local receipts satisfy dependencies while GitHub issues remain open. Resume checks the approved plan, repository identity, and integration bookmark.",
  "4": "Implemented: ownership checking proves disjointness or conservatively serializes. Candidate preparation also compares actual changed paths and rejects overlapping writes.",
  "5": "Implemented: builders retain their workspaces through acceptance. Receipts preserve source commits and fresh guard records before cleanup by the orchestrator.",
  "6": "Implemented: Codex execution uses --json. The grader receives tool events plus observed diffs and artifacts; traces persist even when grading fails. Live model evaluations remain an on-demand check."
};

const components = {
  "goal": {
    "title": "Goal & scope",
    "type": "human",
    "icon": "people",
    "tag": "Human input",
    "sub": "Intent + acceptance criteria",
    "text": "The developer requests a workflow outcome. Shared build reuses executable plans and selected findings, then chooses task scheduling and verification from the work.",
    "input": "Requested behavior, constraints, and prior authorization.",
    "output": "A scoped goal with the existing user decisions.",
    "rules": [
      "Ask only material unanswered questions; no interview quota.",
      "For a new plan, reuse or ask one plan versus multiple plan ideas. The orchestrator chooses team sizes."
    ],
    "sources": [
      {
        "path": "docs/developer-workflows.md",
        "line": 1
      },
      {
        "path": "skills/build/SKILL.md",
        "line": 1
      }
    ]
  },
  "planner": {
    "title": "Planner",
    "type": "agent",
    "icon": "file",
    "tag": "Planning agent",
    "sub": "Authors plans and owns research",
    "text": "Planner agents own assigned approaches, research questions, evidence synthesis, and final plan authorship. The orchestrator frames distinct directions, compares approaches, and reviews the result.",
    "input": "Goal, constraints, decisions, pinned source, artifact ownership, and the saved single-versus-multiple output choice.",
    "output": "Markdown plan, strict sidecar for full plans, optional requested HTML, and evidence with coverage gaps.",
    "rules": [
      "Reuse existing accepted plans and completed evidence on resume.",
      "Researchers remain read-only; use supported native nesting or orchestrator dispatch on the planner’s behalf.",
      "The orchestrator chooses useful planner and researcher counts within actual capacity and user-specified limits.",
      "No target implementation, human conversation, GitHub writes, or self-approval.",
      "Default to Markdown without a format question; an explicit visual request adds HTML."
    ],
    "sources": [
      {
        "path": "skills/plan/SKILL.md",
        "line": 1
      },
      {
        "path": "agents/bodies/planner.md",
        "line": 1
      },
      {
        "path": "skills/plan/references/planning-modes.md",
        "line": 1
      },
      {
        "path": "skills/plan/references/research.md",
        "line": 1
      }
    ]
  },
  "approval": {
    "title": "Human approval",
    "type": "human",
    "icon": "check",
    "tag": "Explicit decision",
    "sub": "Authorize the plan",
    "text": "The orchestrator presents the plan. Once the human approves it, the orchestrator creates or reconciles the milestone and GitHub issues.",
    "input": "The offline plan and its sidecar.",
    "output": "An approved milestone with durable issue markers.",
    "rules": [
      "Silence is never approval.",
      "Deployment needs a separate, fresh approval."
    ],
    "sources": [
      {
        "path": "skills/build/SKILL.md",
        "line": 26
      },
      {
        "path": "skills/plan/scripts/reconcile_github.py",
        "line": 1
      }
    ]
  },
  "queue": {
    "title": "Ready tasks",
    "type": "gate",
    "icon": "flow",
    "tag": "Deterministic selector",
    "sub": "Dependencies + ownership",
    "text": "build_run.py select uses the accepted plan and durable local receipts, with an optional GitHub snapshot. Local tracking uses task keys and null issue numbers; dependencies decide eligibility.",
    "input": "plan.sidecar.json + durable run ledger + optional GitHub state.",
    "output": "unblocked[], deferred[], done[], and currentWave.",
    "rules": [
      "Dependencies may be complete on GitHub or accepted locally. Local tracking rejects unknown external task dependencies.",
      "Uncertain glob intersections serialize; actual changed paths are checked again before integration.",
      "The orchestrator chooses concurrency and useful follow-ups without workflow quotas."
    ],
    "command": "python3 skills/build/scripts/build_run.py select\n  plan.sidecar.json --state <run> --snapshot <snapshot>",
    "notes": [
      3,
      4
    ],
    "sources": [
      {
        "path": "skills/build/scripts/build_run.py",
        "line": 1
      },
      {
        "path": "skills/build/scripts/waves.py",
        "line": 1
      }
    ]
  },
  "specifier": {
    "title": "Specifier",
    "type": "agent",
    "icon": "file",
    "tag": "Test author",
    "sub": "Write tests → RED → seal",
    "text": "Creates the issue's isolated Jujutsu workspace, writes its acceptance tests, proves RED, and seals the test files. The builder inherits this same workspace.",
    "input": "Issue, test oracles, ownership, branch, and base.",
    "output": "Sealed test digests, bound test command, workspace, and handoff.",
    "rules": [
      "No implementation beyond signature-only stubs needed to reach an assertion.",
      "An import or syntax failure is not honest RED.",
      "The builder starts only after the seal exists."
    ],
    "command": "tdd-guard seal --tests <paths>\n  --red-command <argv...>\ntdd-guard handoff --to builder",
    "sources": [
      {
        "path": "agents/bodies/specifier.md",
        "line": 1
      },
      {
        "path": "agents/handoff.md",
        "line": 5
      }
    ]
  },
  "baseline": {
    "title": "Baseline integrator",
    "type": "agent",
    "icon": "shield",
    "tag": "Refactor mode",
    "sub": "Existing GREEN → seal",
    "text": "For behavior-preserving refactor and perf work, an integrator proves the existing baseline GREEN and seals the untouched tests. This replaces the specifier's RED phase.",
    "input": "Pre-created workspace, baselineCommand, and sealedTests.",
    "output": "A kind: baseline seal and green baseline evidence.",
    "rules": [
      "Do not edit the tests.",
      "The builder receives mode: refactor.",
      "The later GREEN run must still postdate the baseline seal."
    ],
    "command": "tdd-guard seal --tests <paths>\n  --green-baseline <argv...>\ntdd-guard handoff --to builder",
    "sources": [
      {
        "path": "agents/bodies/integrator.md",
        "line": 32
      },
      {
        "path": "skills/refactor/SKILL.md",
        "line": 1
      }
    ]
  },
  "builder": {
    "title": "Builder",
    "type": "agent",
    "icon": "code",
    "tag": "Implementation agent",
    "sub": "Implement + focused GREEN",
    "text": "Implements one issue, exercises its runtime, requests independent review, and returns both a stable changeId and an immutable commitId. Its workspace remains available until acceptance.",
    "input": "Sealed tests, assigned workspace, ownership, and runtime hints.",
    "output": "Source commit, current GREEN command ID, runtime proof, review outcomes, and retained workspace.",
    "rules": [
      "Sealed acceptance tests remain protected.",
      "Run bound acceptance tests and relevant targeted regressions; integration owns the full required suite.",
      "Keep handoffs and findings outside the source tree."
    ],
    "command": "tdd-guard verify --green-command <argv...>\njj describe -m \"<summary>\"",
    "notes": [
      1,
      5
    ],
    "sources": [
      {
        "path": "agents/bodies/builder.md",
        "line": 1
      },
      {
        "path": "agents/handoff.md",
        "line": 1
      }
    ]
  },
  "reviewer": {
    "title": "Reviewer",
    "type": "agent",
    "icon": "search",
    "tag": "Independent assurance",
    "sub": "Fresh context · up to 2 passes",
    "text": "Reads the complete change-set through an assigned lens. Builders request fresh, read-only reviewers before committing their local handoff.",
    "input": "Change-set, review lens, and optional non-production runtime URL.",
    "output": "Findings with severity and evidence.",
    "rules": [
      "No edits to the code under review.",
      "Unresolved critical or high findings block the handoff.",
      "After independent review, unresolved blockers return to the orchestrator."
    ],
    "sources": [
      {
        "path": "agents/bodies/reviewer.md",
        "line": 1
      },
      {
        "path": "agents/bodies/builder.md",
        "line": 105
      }
    ]
  },
  "integrator": {
    "title": "Integrator",
    "type": "agent",
    "icon": "branch",
    "tag": "Combined verification",
    "sub": "Prepare + verify candidate",
    "text": "Prepares a separate candidate with build_run.py. Each source is duplicated onto the previous candidate, then the full required check set runs on the combined immutable commit.",
    "input": "Run ledger, source handoff paths, check argv arrays, and a fresh candidate workspace.",
    "output": "Prepared or failed receipt, candidate commit, source gates, command outputs, and durations.",
    "rules": [
      "No repair of code or tests to make the suite pass.",
      "A failing wave returns to the responsible builder.",
      "Does not merge main or decide completion."
    ],
    "command": "python3 skills/build/scripts/build_run.py prepare\n  <sidecar> --state <run> --sources <sources.json>\n  --checks <checks.json> --workspace <candidate>",
    "notes": [
      2
    ],
    "sources": [
      {
        "path": "skills/build/scripts/build_run.py",
        "line": 1
      },
      {
        "path": "docs/build-runs.md",
        "line": 1
      }
    ]
  },
  "orchestrator": {
    "title": "Orchestrator",
    "type": "human",
    "icon": "flow",
    "tag": "Main conversation",
    "sub": "Frame · delegate · review · accept",
    "text": "The main agent owns user intent, decisions, team sizing, coordination, approach comparison, and completion. It delegates plan authorship and accepts execution only from source-bound evidence.",
    "input": "Prepared receipt, independent review, runtime proof, and per-source guard evidence.",
    "output": "Accepted integration commit and durable local completion; later, the final PR.",
    "rules": [
      "Reads relevant source to frame and review work; authors decisions and run records.",
      "Delegates plans, product implementation, runnable tests, and independent verification.",
      "Accepts source-bound command evidence; a prose success claim is insufficient."
    ],
    "command": "python3 skills/build/scripts/build_run.py accept\n  <sidecar> --state <run> --receipt <id>",
    "notes": [
      1,
      3
    ],
    "sources": [
      {
        "path": "docs/adr/0028-planner-owned-research-and-three-harnesses.md",
        "line": 1
      },
      {
        "path": "skills/build/SKILL.md",
        "line": 1
      }
    ]
  },
  "publish": {
    "title": "Final PR & merge",
    "type": "artifact",
    "icon": "branch",
    "tag": "Single-PR path",
    "sub": "Verified final branch → main",
    "text": "The verified source becomes one final pull request. Bounded work needs no invented GitHub issue; milestones include their real closing references. Remote CI checks the exact PR head.",
    "input": "Accepted integration state and the planned issue list.",
    "output": "One final PR and, after acceptance, a merged main.",
    "rules": [
      "Only authorized merges proceed after remote checks.",
      "Builders return local commits; they do not open intermediate PRs.",
      "Complex builds may combine docs on a separate final branch without moving the accepted integration ledger."
    ],
    "notes": [
      3
    ],
    "sources": [
      {
        "path": "skills/build/SKILL.md",
        "line": 1
      }
    ]
  },
  "documenter": {
    "title": "Documenter",
    "type": "agent",
    "icon": "file",
    "tag": "Documentation agent",
    "sub": "Docs included before final verification",
    "text": "Updates documentation in its own scoped workspace and returns an immutable local commit. Complex builds combine it on a separate final branch and record finalization evidence.",
    "input": "Changed files, feature behavior, and docs-only ownership.",
    "output": "Documentation changes and docs-gate evidence.",
    "rules": [
      "Docs only; no implementation or runnable acceptance tests.",
      "The final combined source must be verified.",
      "Keep the accepted integration bookmark unchanged during docs finalization."
    ],
    "sources": [
      {
        "path": "docs/build-runs.md",
        "line": 1
      },
      {
        "path": "agents/bodies/documenter.md",
        "line": 1
      }
    ]
  },
  "deployer": {
    "title": "Deployer",
    "type": "agent",
    "icon": "launch",
    "tag": "Release agent",
    "sub": "Fresh approval → verify → rollback",
    "text": "Executes one approved release against a named target. It checks the rollback path before deployment, verifies the released surface, and returns evidence.",
    "input": "Approval naming who, when, target, and commit.",
    "output": "Release artifacts, deployment verification, and rollback evidence.",
    "rules": [
      "A merged PR is not deployment approval.",
      "No release without a known rollback path.",
      "The orchestrator owns tags, release decisions, and completion."
    ],
    "sources": [
      {
        "path": "agents/bodies/deployer.md",
        "line": 1
      },
      {
        "path": "skills/deploy/SKILL.md",
        "line": 1
      }
    ]
  },
  "researcher": {
    "title": "Researcher",
    "type": "agent",
    "icon": "search",
    "tag": "Investigation agent",
    "sub": "One area · read-only evidence",
    "text": "Investigates one assigned area and returns evidence for planning or synthesis. It is a supporting role rather than a required stage of every build.",
    "input": "An investigation question, scope, and sources.",
    "output": "A findings envelope with supporting evidence.",
    "rules": [
      "No target-project writes.",
      "Does not author the final research report or make the overall conclusion."
    ],
    "sources": [
      {
        "path": "agents/bodies/researcher.md",
        "line": 1
      }
    ]
  },
  "debugger": {
    "title": "Debugger",
    "type": "agent",
    "icon": "search",
    "tag": "Diagnostic agent",
    "sub": "Reproduce → isolate root cause",
    "text": "Uses experiments to reproduce a reported symptom and identify its cause. A builder receives the eventual fix assignment.",
    "input": "Symptom, reproduction hints, and target workspace.",
    "output": "Reproducer evidence and a demonstrated root cause.",
    "rules": [
      "Temporary instrumentation only; remove it before returning.",
      "Does not ship the fix."
    ],
    "sources": [
      {
        "path": "agents/bodies/debugger.md",
        "line": 1
      }
    ]
  },
  "profiler": {
    "title": "Profiler",
    "type": "agent",
    "icon": "chart",
    "tag": "Measurement agent",
    "sub": "Benchmarks + distributions",
    "text": "Measures performance under recorded conditions and returns distributions across multiple runs. This role supplies evidence for perf decisions.",
    "input": "Benchmark harness, workload, and measurement conditions.",
    "output": "Run counts, distributions, and comparable measurements.",
    "rules": [
      "No implementation edits.",
      "A single run is not sufficient performance evidence."
    ],
    "sources": [
      {
        "path": "agents/bodies/profiler.md",
        "line": 1
      }
    ]
  },
  "contracts": {
    "title": "Shared contracts",
    "type": "artifact",
    "icon": "file",
    "tag": "Canonical definitions",
    "sub": "10 roles · 19 skill contracts",
    "text": "The contract registry defines the cross-harness requirements. Agent bodies, metadata, model assignments, and workflow skills supply the shared source material.",
    "input": "contracts/, agents/bodies/, agents/agents.json, agents/models.json, skills/.",
    "output": "A common role roster, handoff shape, and workflow contract.",
    "rules": [
      "Synchronization and parity checks detect distribution drift.",
      "Shared instructions do not imply identical runtime enforcement."
    ],
    "sources": [
      {
        "path": "contracts/harness-contracts.json",
        "line": 1
      },
      {
        "path": "agents/handoff.md",
        "line": 1
      }
    ]
  },
  "agentSource": {
    "title": "Agent sources",
    "type": "artifact",
    "icon": "people",
    "tag": "Role definitions",
    "sub": "Bodies + capabilities + models",
    "text": "Canonical agent bodies include harness-specific sections. Metadata declares tool access and dispatch substitutions; model configuration is synchronized separately.",
    "input": "agents/bodies/*.md, agents/agents.json, agents/models.json.",
    "output": "Harness-native agent definitions.",
    "sources": [
      {
        "path": "agents/agents.json",
        "line": 1
      },
      {
        "path": "scripts/sync-agents.py",
        "line": 1
      }
    ]
  },
  "skillSource": {
    "title": "Workflow skills",
    "type": "artifact",
    "icon": "flow",
    "tag": "Dispatch contracts",
    "sub": "Developer entry points + reusable stages",
    "text": "Twelve public skills expose workflow outcomes and supporting operations. Build owns shared implementation, review, integration, documentation, and final verification; debug and refactor reuse it.",
    "input": "Canonical skills and their local scripts.",
    "output": "Harness-owned skill distributions.",
    "rules": [
      "The build loop is currently an instruction contract, not a continuously running scheduler service."
    ],
    "sources": [
      {
        "path": "docs/developer-workflows.md",
        "line": 1
      },
      {
        "path": "skills/build/SKILL.md",
        "line": 1
      },
      {
        "path": "skills/build/SKILL.md",
        "line": 1
      },
      {
        "path": "skills/refactor/SKILL.md",
        "line": 1
      }
    ]
  },
  "claude": {
    "title": "Claude Code",
    "type": "agent",
    "icon": "terminal",
    "tag": "Harness adapter",
    "sub": "Native hooks wired",
    "text": "Ships native agents, skills, plugin metadata, and tool-event hooks. The installed plugin is an owned copy of a staged distribution.",
    "input": "harnesses/claude/ + plugins/claude/.",
    "output": "Agent dispatch and PreToolUse, PostToolUse, Stop, and builder SubagentStop hooks.",
    "rules": [
      "Main-conversation identity is distinguished from subagents for merge policy."
    ],
    "sources": [
      {
        "path": "plugins/claude/hooks/hooks.json",
        "line": 1
      },
      {
        "path": "scripts/build-claude-plugin.py",
        "line": 1
      }
    ]
  },
  "codex": {
    "title": "Codex",
    "type": "agent",
    "icon": "terminal",
    "tag": "Harness adapter",
    "sub": "GPT-6 Astra · explicit effort",
    "text": "Codex routes now use gpt-6-astra, preserving each role's previous reasoning effort. Native hook enforcement still depends on installation and trust.",
    "input": "harnesses/codex/ + plugins/codex/.",
    "output": "Native dispatch plus configured guard, formatting, lint, and Stop hooks.",
    "rules": [
      "High: planner, specifier, builder, debugger, deployer.",
      "Medium: reviewer, integrator, documenter, profiler. Low: researcher.",
      "Rebuild and reinstall the plugin to activate changed repository defaults."
    ],
    "sources": [
      {
        "path": "agents/models.json",
        "line": 1
      },
      {
        "path": "docs/models/gpt-6-astra/prompting.md",
        "line": 1
      },
      {
        "path": "plugins/codex/hooks/hooks.json",
        "line": 1
      }
    ]
  },
  "agy": {
    "title": "Antigravity",
    "type": "agent",
    "icon": "terminal",
    "tag": "Harness adapter",
    "sub": "Session-wide hooks",
    "text": "Uses native subagents and session-global hooks. The installer places one owned plugin copy under the Gemini plugin directory.",
    "input": "harnesses/agy/ + plugins/agy/.",
    "output": "invoke_subagent dispatch and scoped session-level guard hooks.",
    "rules": [
      "Hooks do not identify the caller, so merge commands stay denied by the guard.",
      "The jj skill is agent-owned by builder and specifier."
    ],
    "sources": [
      {
        "path": "plugins/agy/hooks.json",
        "line": 1
      },
      {
        "path": "docs/gates.md",
        "line": 81
      }
    ]
  },
  "workspace": {
    "title": "Workspace helper",
    "type": "gate",
    "icon": "branch",
    "tag": "Isolation primitive",
    "sub": "One issue · one working copy",
    "text": "nova-ws creates, lists, forgets, and sweeps named sibling workspaces. The local trunk build uses Jujutsu workspaces; the helper also supports Git worktrees.",
    "input": "A key, repository, and agreed base.",
    "output": "An isolated working copy and surviving bookmark or branch.",
    "rules": [
      "Workspace identity and content are separate from a durable task identity.",
      "Cleanup refuses to remove the directory the calling shell is standing in."
    ],
    "command": "nova-ws add feature/<key> --base <base>\nnova-ws list\nnova-ws sweep",
    "notes": [
      5
    ],
    "sources": [
      {
        "path": "scripts/nova-ws",
        "line": 322
      },
      {
        "path": "docs/workspaces.md",
        "line": 1
      }
    ]
  },
  "guard": {
    "title": "tdd-guard",
    "type": "gate",
    "icon": "shield",
    "tag": "Go executable",
    "sub": "Seal · verify · review · status",
    "text": "The harness-neutral binary manages test seals, bound test commands, GREEN records, diff reviews, handoffs, and Stop decisions. Harness hooks call it through wrapper scripts.",
    "input": "Repository state, test commands, and native hook payloads.",
    "output": "Machine-readable guard status and command evidence.",
    "rules": [
      "The implementation is cmd/tdd-guard/ and guard/.",
      "Runtime exercise evidence remains a contract-level requirement."
    ],
    "notes": [
      1
    ],
    "sources": [
      {
        "path": "guard/run.go",
        "line": 1
      },
      {
        "path": "guard/actions.go",
        "line": 133
      }
    ]
  },
  "utilities": {
    "title": "Supporting scripts",
    "type": "gate",
    "icon": "code",
    "tag": "Deterministic tools",
    "sub": "Select · reconcile · validate",
    "text": "Small programs support scheduling, GitHub reconciliation, report assembly, plugin staging, and repository validation.",
    "input": "Planner sidecars, snapshots, findings, and canonical definitions.",
    "output": "Dispatchable sets, reconciled issues, generated artifacts, and check results.",
    "rules": [
      "build-guard enforces shell-operation policy; format and lint wrappers handle written files."
    ],
    "sources": [
      {
        "path": "skills/build/scripts/waves.py",
        "line": 1
      },
      {
        "path": "scripts/hooks/build-guard",
        "line": 1
      },
      {
        "path": "scripts/check-contract-parity.py",
        "line": 1
      }
    ]
  },
  "handoff": {
    "title": "Agent handoff",
    "type": "artifact",
    "icon": "file",
    "tag": "Structured contract",
    "sub": "anvil.agent-handoff/v1",
    "text": "Every specialist returns one JSON record. Commands carry IDs, changed paths identify scope, and agent-specific evidence records tests, runtime checks, findings, or measurements.",
    "input": "An agent's work and evidence.",
    "output": "done, blocked, or needs-decision, plus result and evidence.",
    "rules": [
      "Local builder handoffs pin commitId as well as changeId.",
      "A handoff is checked against current source and guard evidence.",
      "Full dispatch attempts and writer-slot leases are still outside this handoff contract."
    ],
    "sources": [
      {
        "path": "agents/handoff.md",
        "line": 55
      }
    ]
  },
  "github": {
    "title": "GitHub state",
    "type": "artifact",
    "icon": "branch",
    "tag": "Durable project record",
    "sub": "Milestones · issues · final PR",
    "text": "GitHub carries approved plans, durable issue markers, dependencies, labels, and final pull requests. The selector consumes a captured issue snapshot.",
    "input": "Approved issue reconciliation and PR/issue updates.",
    "output": "The external project record used on resume.",
    "notes": [
      3
    ],
    "sources": [
      {
        "path": "skills/build/SKILL.md",
        "line": 32
      },
      {
        "path": "skills/plan/scripts/reconcile_github.py",
        "line": 1
      }
    ]
  },
  "state": {
    "title": "Guard evidence store",
    "type": "artifact",
    "icon": "box",
    "tag": "Local evidence",
    "sub": "Per-workspace path identity",
    "text": "Guard records are stored outside the checkout, under ~/.local/state/tdd-guard by default. Each repository or workspace root hashes to a separate state directory.",
    "input": "Seal, verify, review, and handoff commands.",
    "output": "seal.json, green.json, diff-review.json, and related records.",
    "rules": [
      "ANVIL_GUARD_STATE can override the base directory.",
      "The state directory is writable by the same OS user; it is not an adversarial security boundary."
    ],
    "notes": [
      5
    ],
    "sources": [
      {
        "path": "guard/guard.go",
        "line": 217
      },
      {
        "path": "guard/guard.go",
        "line": 261
      }
    ]
  },
  "wiki": {
    "title": "Project wiki",
    "type": "artifact",
    "icon": "file",
    "tag": "Opt-in knowledge",
    "sub": "Outside every repository",
    "text": "An explicitly created project namespace stores raw run evidence and consolidated patterns outside the repository. It does not participate in merge readiness.",
    "input": "Accepted run evidence when a project namespace exists.",
    "output": "Append-only project evidence and curated pages.",
    "rules": [
      "Default home: ~/.nova/wiki/.",
      "Runtime agents deliberately do not read it as shared memory.",
      "An absent or failed record never blocks a merge."
    ],
    "sources": [
      {
        "path": "docs/adr/0019-the-wiki-lives-outside-every-repository.md",
        "line": 1
      },
      {
        "path": "skills/wiki/SKILL.md",
        "line": 1
      }
    ]
  },
  "controlplane": {
    "title": "Control-plane types",
    "type": "artifact",
    "icon": "layers",
    "tag": "Library contracts",
    "sub": "Authority · lifecycle · evidence",
    "text": "The Go controlplane package defines and validates lifecycle, route, authority, ownership, budget, cancellation, and result contracts. The guard uses its evidence types.",
    "input": "Versioned records and canonical digests.",
    "output": "Validated contracts and evidence structures.",
    "rules": [
      "The Go types remain library contracts, not an autonomous scheduler.",
      "The Python build ledger now executes candidate preparation, acceptance, and resume."
    ],
    "sources": [
      {
        "path": "controlplane/lifecycle.go",
        "line": 1
      },
      {
        "path": "controlplane/route.go",
        "line": 1
      },
      {
        "path": "cmd/tdd-guard/main.go",
        "line": 1
      }
    ]
  },
  "seal": {
    "title": "01 · Seal",
    "type": "gate",
    "icon": "shield",
    "tag": "Mechanical check",
    "sub": "Bind tests + test command",
    "text": "Captures test digests and the exact command that established RED, or a GREEN baseline in refactor mode. The code checks the exit status; an honest assertion failure is the specifier's contract.",
    "input": "Test paths and RED or baseline command argv.",
    "output": "A kind: red or kind: baseline seal.",
    "command": "tdd-guard seal --tests <paths>\n  --red-command <argv...>",
    "sources": [
      {
        "path": "guard/actions.go",
        "line": 19
      }
    ]
  },
  "protect": {
    "title": "02 · Protect tests",
    "type": "gate",
    "icon": "shield",
    "tag": "Hook + digest checks",
    "sub": "Deny sealed-path edits",
    "text": "On wired, active hooks, direct edits to sealed paths are denied. Changed test digests are also detected when verification or status runs.",
    "input": "Tool targets and sealed test digests.",
    "output": "Permission to proceed, denial, or a stale-test finding.",
    "rules": [
      "Shell-based out-of-band changes may be detected after execution.",
      "Amendments use reseal --reason; baseline seals cannot be resealed."
    ],
    "sources": [
      {
        "path": "guard/hook.go",
        "line": 299
      },
      {
        "path": "guard/actions.go",
        "line": 223
      }
    ]
  },
  "verify": {
    "title": "03 · Verify GREEN",
    "type": "gate",
    "icon": "check",
    "tag": "Mechanical check",
    "sub": "Same argv · same source state",
    "text": "Runs the bound command after the seal and records the base commit and source digest. Source changes during verification fail the attempt; subsequent edits make GREEN stale.",
    "input": "Current implementation, sealed tests, and bound command.",
    "output": "Tree-bound GREEN, or no passing evidence after failure.",
    "command": "tdd-guard verify --green-command <argv...>",
    "notes": [
      1
    ],
    "sources": [
      {
        "path": "guard/actions.go",
        "line": 1
      },
      {
        "path": "guard/green_freshness_test.go",
        "line": 1
      }
    ],
    "rules": [
      "A new attempt discards prior GREEN and the specifier Stop relaxation.",
      "Concurrent verification attempts are rejected.",
      "Coverage is advisory; it is not a new acceptance gate."
    ]
  },
  "diffreview": {
    "title": "04 · Record review",
    "type": "gate",
    "icon": "search",
    "tag": "Evidence freshness",
    "sub": "Bind a record to the diff",
    "text": "Records a non-empty findings file and a digest of the current diff. Changing the diff makes that review record stale.",
    "input": "Current diff and findings text.",
    "output": "Diff digest, command evidence, and recorded findings.",
    "rules": [
      "The guard checks record freshness; it does not mechanically prove an independent reviewer cleared every high finding."
    ],
    "command": "tdd-guard diff-review record\n  --findings <file>",
    "sources": [
      {
        "path": "guard/actions.go",
        "line": 267
      }
    ]
  },
  "stop": {
    "title": "05 · Stop / status",
    "type": "gate",
    "icon": "shield",
    "tag": "Readiness decision",
    "sub": "Seal + bound GREEN + fresh review",
    "text": "Readiness requires unchanged sealed tests, GREEN for the current source and base, the bound argv, and a current diff review.",
    "input": "Guard records and the current workspace tree.",
    "output": "ready plus greenStale and diffStale; the Stop hook enforces the same checks.",
    "rules": [
      "Specifier handoff relaxes Stop only; it never satisfies merge readiness."
    ],
    "command": "tdd-guard status --json",
    "notes": [
      1,
      5
    ],
    "sources": [
      {
        "path": "guard/actions.go",
        "line": 1
      },
      {
        "path": "docs/gates.md",
        "line": 1
      }
    ]
  },
  "runtime": {
    "title": "06 · Runtime proof",
    "type": "agent",
    "icon": "terminal",
    "tag": "Contract-level requirement",
    "sub": "Exercise the actual surface",
    "text": "The builder runs the surface it changed: a real UI, HTTP service, or CLI. Library-only changes can justify surface: none. This is checked through the handoff contract.",
    "input": "A runnable change and optional launch/url/healthPath hints.",
    "output": "evidence.runtime: commands, observations, console errors, screenshots where relevant.",
    "rules": [
      "The Stop hook does not validate runtime evidence.",
      "An incomplete runtime record should cause redispatch with a useful hint."
    ],
    "sources": [
      {
        "path": "agents/handoff.md",
        "line": 73
      },
      {
        "path": "docs/gates.md",
        "line": 56
      }
    ]
  },
  "evals": {
    "title": "Evaluation coverage",
    "type": "gate",
    "icon": "chart",
    "tag": "Validation layers",
    "sub": "Structural · routing · behavioral",
    "text": "Free structural checks validate instruction shape and parity. TF-IDF routing checks descriptions against trigger prompts. On-demand behavioral cases launch a harness and use a grader.",
    "input": "Skill and agent cases, fixture repositories, and execution output.",
    "output": "Structure checks, retrieval scores, and behavioral grades.",
    "rules": [
      "Real Jujutsu regression tests cover siblings, failed checks, changed candidates, and interrupted acceptance.",
      "Behavioral grading receives Codex JSON events plus independently captured workspace evidence.",
      "Live model behavior has not been measured by these deterministic checks."
    ],
    "notes": [
      6
    ],
    "sources": [
      {
        "path": "evals/run_evals.py",
        "line": 1
      },
      {
        "path": "evals/tests/test_evals.py",
        "line": 1
      },
      {
        "path": "skills/build/tests/test_build_run.py",
        "line": 1
      }
    ]
  },
  "ledger": {
    "title": "Build run ledger",
    "type": "artifact",
    "icon": "box",
    "tag": "Durable local progression",
    "sub": "Prepare → accept → select",
    "text": "An external run directory records integration intent, candidate receipts, command results, and accepted issue keys. It survives process restarts.",
    "input": "Approved plan digest, repository identity, sources, and combined check results.",
    "output": "run.json with preparing, prepared, failed, and accepted rounds.",
    "rules": [
      "Exclusive lock serializes integration operations.",
      "Acceptance can recover an interrupted bookmark update.",
      "This helper does not launch agents or lease writer slots."
    ],
    "sources": [
      {
        "path": "skills/build/scripts/build_run.py",
        "line": 1
      },
      {
        "path": "docs/build-runs.md",
        "line": 1
      }
    ],
    "notes": [
      2,
      3,
      5
    ]
  },
  "leadPlan": {
    "title": "Brief the planner",
    "type": "human",
    "icon": "file",
    "tag": "Orchestrator",
    "sub": "Preserve intent · delegate authorship",
    "text": "The orchestrator frames distinct assignments with source, constraints, decisions, artifact ownership, and the requested plan output. It chooses the planning team and records agent IDs.",
    "input": "User decisions, source context, and optional specialist evidence.",
    "output": "Scoped planner assignments with durable IDs and final authorship.",
    "rules": [
      "Planner agents author the approaches and final plan; the orchestrator compares and reviews.",
      "Research belongs to the planner, with orchestrator dispatch when nesting is unavailable.",
      "Preserve exact-artifact approval for optional GitHub reconciliation."
    ],
    "sources": [
      {
        "path": "docs/adr/0028-planner-owned-research-and-three-harnesses.md",
        "line": 1
      },
      {
        "path": "skills/plan/SKILL.md",
        "line": 1
      }
    ]
  },
  "finalVerify": {
    "title": "Integrator",
    "type": "agent",
    "icon": "check",
    "tag": "Independent verification",
    "sub": "Exact final source",
    "text": "For one change, the integrator verifies the already-combined source directly. No synthetic milestone or multi-issue ledger is required.",
    "input": "Pinned source and base, retained workspace, and required checks.",
    "output": "Command-linked outcomes for the exact final commit.",
    "rules": [
      "Source changes invalidate evidence.",
      "No product fixes or acceptance decisions.",
      "The orchestrator reads fresh guard status and records completion outside the tested workspace."
    ],
    "sources": [
      {
        "path": "skills/build/references/single-change.md",
        "line": 1
      },
      {
        "path": "agents/bodies/integrator.md",
        "line": 1
      }
    ]
  },
  "planningChoice": {
    "title": "Planning choice",
    "type": "human",
    "icon": "people",
    "tag": "Ask the user",
    "sub": "One plan or multiple ideas?",
    "text": "Ask the output choice once unless the request or saved state already answers it. This determines whether to compare alternative approaches, not a fixed number of agents.",
    "input": "Scoped goal and any saved planning choice.",
    "output": "A recorded choice for this planning round.",
    "rules": [
      "The orchestrator chooses useful team sizes and honors actual capacity and user constraints.",
      "Reuse explicit choices, agent IDs, evidence, and plan identity on resume.",
      "Markdown is the default; no format question. HTML requires an explicit visual request.",
      "This diagram never launches agents."
    ],
    "sources": [
      {
        "path": "skills/plan/references/planning-modes.md",
        "line": 1
      }
    ]
  },
  "researchAssignment": {
    "title": "Scoped research assignment",
    "type": "agent",
    "icon": "search",
    "tag": "Researcher",
    "sub": "One evidence question",
    "text": "The planner sends each researcher a distinct read-only question, pinned source, constraints, and unique artifact ownership. Evidence returns directly to the planner.",
    "input": "Assigned question, pinned source, relevant evidence, and read-only scope.",
    "output": "Findings, sources, coverage, uncertainty, and unresolved conflicts.",
    "rules": [
      "The planner owns questions and synthesis; the orchestrator chooses the team.",
      "No child delegation, target implementation, or GitHub writes.",
      "Save IDs and evidence so resume does not duplicate work.",
      "Queue useful work within actual runtime capacity; no workflow-imposed count or retry limit."
    ],
    "sources": [
      {
        "path": "skills/plan/references/planning-modes.md",
        "line": 1
      },
      {
        "path": "skills/plan/references/research.md",
        "line": 1
      }
    ]
  },
  "synthesis": {
    "title": "Planner synthesizes evidence",
    "type": "human",
    "icon": "file",
    "tag": "Planner",
    "sub": "Evidence into an executable plan",
    "text": "After approaches are compared and decisions are made, the assigned planner reconciles the selected ideas and evidence into a coherent executable plan.",
    "input": "The proposed approaches, source evidence, and the user constraints.",
    "output": "A Markdown plan, optional requested HTML companion, and sidecar for full plans.",
    "rules": [
      "Preserve source citations and critical evidence gaps.",
      "Compare alternatives against the user’s constraints; do not vote or append every suggestion.",
      "Return material decisions to the orchestrator."
    ],
    "sources": [
      {
        "path": "skills/plan/references/planning-modes.md",
        "line": 1
      },
      {
        "path": "skills/plan/references/research.md",
        "line": 1
      }
    ]
  },
  "planSelection": {
    "title": "Review the plan",
    "type": "human",
    "icon": "check",
    "tag": "Orchestrator",
    "sub": "Accept · revise · needs-decision",
    "text": "The orchestrator evaluates the planner’s report against the goal, constraints, evidence, and acceptance criteria. Revisions return to the same planner.",
    "input": "Planner report and source evidence.",
    "output": "Recorded review findings and disposition.",
    "rules": [
      "Standalone planning presents the reviewed artifacts, then asks whether to build. Prior plan-and-implement authorization continues without reasking.",
      "Do not treat a polished report or agent agreement as proof.",
      "Preserve review decisions, plan identity, and evidence on resume."
    ],
    "sources": [
      {
        "path": "skills/plan/references/planning-modes.md",
        "line": 1
      }
    ]
  },
  "treeIntent": {
    "title": "What kind of work?",
    "type": "human",
    "icon": "branch",
    "tag": "Developer goal",
    "sub": "Start with the outcome you need",
    "text": "Nova chooses a development workflow from the requested outcome. New behavior, behavior-preserving cleanup, and a reported failure use different entry points.",
    "input": "Your goal, constraints, and existing decisions.",
    "output": "A build, refactor, or debug workflow.",
    "rules": [
      "An existing approved plan resumes at execution using saved work and evidence.",
      "Research, docs, review, setup, and deployment remain separate commands for those outcomes."
    ],
    "sources": [
      {
        "path": "docs/developer-workflows.md",
        "line": 1
      }
    ]
  },
  "treeBuild": {
    "title": "Build",
    "type": "human",
    "icon": "branch",
    "tag": "Workflow",
    "sub": "Add or change behavior",
    "text": "The shared build entry point accepts a request, a selected plan, or scoped findings and chooses scheduling and verification independently.",
    "input": "Requested behavior and observable acceptance criteria.",
    "output": "The appropriate build path.",
    "rules": [
      "File count alone does not determine the required coordination.",
      "Reuse an executable brief or plan; delegate only missing planning work."
    ],
    "sources": [
      {
        "path": "skills/build/SKILL.md",
        "line": 1
      }
    ]
  },
  "treeBuildScope": {
    "title": "How much coordination?",
    "type": "human",
    "icon": "branch",
    "tag": "Scope decision",
    "sub": "Known interface or dependent changes?",
    "text": "A clear change can use a concise brief. Dependent changes use task ownership and dependency scheduling. Team size follows useful work rather than a simple-versus-complex quota.",
    "input": "Repository evidence, interfaces, dependencies, and ownership.",
    "output": "An executable task brief or dependency-aware plan.",
    "rules": [
      "A small protocol change may require coordinated planning.",
      "Escalation preserves completed evidence and user constraints."
    ],
    "sources": [
      {
        "path": "docs/developer-workflows.md",
        "line": 1
      }
    ]
  },
  "treeBounded": {
    "title": "Scoped change",
    "type": "human",
    "icon": "branch",
    "tag": "simple-build",
    "sub": "Known interface",
    "text": "A clear change can use a concise brief and retained workspace, with delegated tests, implementation, review, documentation, and final verification.",
    "input": "A clear goal, ownership, and acceptance criteria.",
    "output": "One independently verified change.",
    "rules": [
      "No synthetic milestone or GitHub issue is required.",
      "A new planning round asks only the output choice not already supplied."
    ],
    "sources": [
      {
        "path": "skills/build/SKILL.md",
        "line": 1
      }
    ]
  },
  "treeComplex": {
    "title": "Coordinated",
    "type": "human",
    "icon": "branch",
    "tag": "complex-build",
    "sub": "Dependencies or uncertainty",
    "text": "Planners author the architecture and task plan. The orchestrator reviews it and schedules ready work with separate ownership and durable receipts.",
    "input": "Uncertain interfaces, a migration, or dependent changes.",
    "output": "An executable plan and resumable task execution.",
    "rules": [
      "Use disjoint implementation and test ownership for parallel work.",
      "Research remains inside planning; the orchestrator chooses team sizes."
    ],
    "sources": [
      {
        "path": "skills/build/SKILL.md",
        "line": 1
      }
    ]
  },
  "treeRefactor": {
    "title": "Refactor",
    "type": "human",
    "icon": "branch",
    "tag": "Workflow",
    "sub": "Improve structure",
    "text": "The refactor workflow simplifies implementation while keeping observable behavior and the existing tests fixed.",
    "input": "A concrete simplification and behavior to preserve.",
    "output": "A simpler implementation verified against its preserved behavior and baseline.",
    "rules": [
      "Do not add features or fix bugs under the refactor invariant.",
      "Protect existing tests with a GREEN baseline seal."
    ],
    "sources": [
      {
        "path": "skills/refactor/SKILL.md",
        "line": 1
      }
    ]
  },
  "treeInvariant": {
    "title": "Keep behavior fixed",
    "type": "artifact",
    "icon": "file",
    "tag": "Refactor invariant",
    "sub": "Existing tests stay unchanged",
    "text": "A refactor retains the same behavior and tests. It uses baseline verification instead of authoring new failing acceptance tests.",
    "input": "Existing behavior, tests, and documented verification.",
    "output": "A behavior-preservation requirement carried into planning and execution.",
    "rules": [
      "No added, modified, or deleted tests.",
      "A failing baseline stops the refactor before implementation."
    ],
    "sources": [
      {
        "path": "skills/refactor/SKILL.md",
        "line": 1
      }
    ]
  },
  "treeDebug": {
    "title": "Debug",
    "type": "human",
    "icon": "branch",
    "tag": "Workflow",
    "sub": "Diagnose a reported failure",
    "text": "Debuggers reproduce and isolate the reported symptom. A requested repair carries that diagnosis into shared build; investigation-only requests finish with a report.",
    "input": "Reported symptom and reproduction context.",
    "output": "A diagnosis report with causal evidence and any unresolved reproduction gaps.",
    "rules": [
      "A reported failure is not a broad defect sweep.",
      "Carry the supported diagnosis into any authorized repair."
    ],
    "sources": [
      {
        "path": "skills/debug/SKILL.md",
        "line": 1
      }
    ]
  },
  "treePlan": {
    "title": "One final plan",
    "type": "artifact",
    "icon": "file",
    "tag": "Planner authors · orchestrator reviews",
    "sub": "A brief or a milestone plan",
    "text": "Both modes produce one coherent planner-authored Markdown plan. Full plans include a strict sidecar; an explicit visual request adds HTML.",
    "input": "Source evidence, user constraints, and planner synthesis.",
    "output": "One plan with clear ownership, dependencies, and acceptance criteria.",
    "rules": [
      "Default to Markdown with no format question; HTML is an explicit companion.",
      "Milestone reconciliation requires approval of the exact final plan.",
      "Saved choices and completed work survive resume."
    ],
    "sources": [
      {
        "path": "skills/plan/references/planning-modes.md",
        "line": 1
      },
      {
        "path": "skills/plan/SKILL.md",
        "line": 1
      }
    ]
  },
  "treeExecutionShape": {
    "title": "How is work organized?",
    "type": "human",
    "icon": "branch",
    "tag": "Execution decision",
    "sub": "One change or dependent tasks?",
    "text": "A scoped change can share a retained workspace in sequence. Dependent work uses separate ownership and a durable integration ledger. Both use the same build stages and gates.",
    "input": "The final scope, task dependencies, and ownership.",
    "output": "A single-change run or dependency-aware waves.",
    "rules": [
      "Parallelize independent work within the harness capacity.",
      "Approved-plan resumes enter execution without another planning round."
    ],
    "sources": [
      {
        "path": "docs/developer-workflows.md",
        "line": 1
      },
      {
        "path": "docs/build-runs.md",
        "line": 1
      }
    ]
  },
  "treeSingle": {
    "title": "One change",
    "type": "artifact",
    "icon": "file",
    "tag": "Bounded execution",
    "sub": "Saved brief · one workspace",
    "text": "The single-change path records a brief and agent evidence without inventing GitHub tracking. Specialists share the retained workspace in the required order.",
    "input": "The executable brief, exact base, ownership, and verification commands.",
    "output": "One source revision ready for final verification.",
    "rules": [
      "No builder starts before the required test seal.",
      "Retain evidence and workspace through merge or explicit abandonment."
    ],
    "sources": [
      {
        "path": "skills/build/references/single-change.md",
        "line": 1
      }
    ]
  },
  "treeTestChoice": {
    "title": "Which test gate?",
    "type": "human",
    "icon": "branch",
    "tag": "Behavior decision",
    "sub": "Changing behavior or preserving it?",
    "text": "Features and bug fixes use failing acceptance tests authored by a specifier. Behavior-preserving refactors use the existing GREEN suite protected by an integrator baseline seal.",
    "input": "The selected workflow and acceptance criteria.",
    "output": "A RED seal or a GREEN baseline seal before implementation.",
    "rules": [
      "The orchestrator does not author runnable acceptance tests.",
      "Both paths require fresh evidence and independent review."
    ],
    "sources": [
      {
        "path": "agents/bodies/specifier.md",
        "line": 1
      },
      {
        "path": "agents/bodies/integrator.md",
        "line": 1
      }
    ]
  },
  "treeVerification": {
    "title": "Verify the final source",
    "type": "agent",
    "icon": "file",
    "tag": "Integrator",
    "sub": "Check the exact combined result",
    "text": "The integrator verifies the exact source that will be accepted. A single change is verified directly; dependency waves verify combined candidates before acceptance.",
    "input": "Immutable source revisions, review findings, and required checks.",
    "output": "Command-linked verification and current guard evidence.",
    "rules": [
      "Required documentation must be included before final verification.",
      "Source changes invalidate previous evidence."
    ],
    "sources": [
      {
        "path": "agents/bodies/integrator.md",
        "line": 1
      },
      {
        "path": "docs/build-runs.md",
        "line": 1
      }
    ]
  },
  "treeReady": {
    "title": "Does the evidence pass?",
    "type": "human",
    "icon": "branch",
    "tag": "Orchestrator decision",
    "sub": "Fresh checks + resolved blocking findings",
    "text": "The orchestrator reads mechanical evidence and specialist handoffs before accepting work. Failed verification, stale source evidence, and blocking review findings return to the responsible specialist.",
    "input": "Current verification, source identity, and independent review.",
    "output": "Accept the change, or return it for correction.",
    "rules": [
      "A prose claim does not substitute for command evidence.",
      "An accepted local change is not yet a merged pull request."
    ],
    "sources": [
      {
        "path": "docs/gates.md",
        "line": 1
      },
      {
        "path": "skills/build/SKILL.md",
        "line": 1
      }
    ]
  },
  "treeRetry": {
    "title": "Return to the owner",
    "type": "agent",
    "icon": "file",
    "tag": "Fix or resolve",
    "sub": "Then review and verify again",
    "text": "Return failed checks or findings to the responsible specialist. Refresh the affected review and verification evidence after a change. Material scope decisions return to the human.",
    "input": "The concrete failed check, stale evidence, or blocking finding.",
    "output": "A corrected change, an explicit decision, or a reported blocker.",
    "rules": [
      "Choose useful follow-ups from the evidence and user constraints; no workflow-imposed retry quota.",
      "Do not broaden scope or pay for another planning round without the relevant user choice."
    ],
    "sources": [
      {
        "path": "skills/build/SKILL.md",
        "line": 1
      },
      {
        "path": "skills/plan/references/planning-modes.md",
        "line": 1
      }
    ]
  }
};

const views = {
  flow:{name:"Execution flow",icon:"flow",title:"How work moves.",eyebrow:"01 / EXECUTION",description:"How each workflow runs: orchestrator decisions, delegated agents, evidence gates, and the final result.",selected:"planningChoice"},
  tree:{name:"Decision tree",icon:"branch",title:"The choices behind the work.",eyebrow:"02 / DECISION TREE",description:"The implemented workflow surface: choose the outcome, then let the orchestrator delegate and review.",selected:"treeIntent"},
  architecture:{name:"Architecture",icon:"layers",title:"One system. Three harnesses.",eyebrow:"03 / ARCHITECTURE",description:"Shared definitions become installed harness packages, supported by local tools and evidence stores.",selected:"contracts"},
  agents:{name:"Agent roster",icon:"people",title:"Ten roles. Clear boundaries.",eyebrow:"04 / RESPONSIBILITIES",description:"Specialist agents own focused assignments. The planner owns plans; the main conversation coordinates, reviews, and decides completion.",selected:"builder"},
  gates:{name:"Mechanical gates",icon:"shield",title:"What actually enforces the flow.",eyebrow:"05 / EVIDENCE & ENFORCEMENT",description:"The current gate implementation, the contract-level checks, and how enforcement varies by harness.",selected:"verify"},
};
const roleIds=["planner","specifier","builder","reviewer","integrator","documenter","researcher","debugger","profiler","deployer"];
const workflowMap = Object.fromEntries(workflowCatalog.workflows.map(workflow => [workflow.name, workflow]));
// Workflow views and component details follow the current repository catalog.
const designGroups = [...workflowDesign.groups, {id:"auxiliary",title:"Auxiliary skills",question:"Supporting operations"}];
const designWorkflows = [...workflowDesign.workflows.map(workflow=>({...workflow,kind:"workflow"})), ...workflowDesign.auxiliaries.map(workflow=>({...workflow,kind:"auxiliary"}))].map(definition=>{
  const {source:sourceName,...fields}=definition;
  const base=workflowMap[sourceName || definition.name];
  return {...base,...fields,source:base.source,paths:definition.paths || base.paths};
});
const designWorkflowMap = Object.fromEntries(designWorkflows.map(workflow=>[workflow.name,workflow]));
const designStages = {...workflowCatalog.stages};
for (const [id,changes] of Object.entries(workflowDesign.stages)) designStages[id]={...designStages[id],...changes};
const designStageDescendants = id => [id, ...(designStages[id].chain || []).flatMap(designStageDescendants)];
const designSources = workflow => [{path:"docs/diagrams/system-map/workflow-design.js",line:1},{path:workflow.source,line:1}];

let view="tree", workflowName="build", pathId="bounded", planningMode="single", selected="preview-workflow-build", step=-1;
const el = id => document.getElementById(id);
const node = (id, overrides={}) => {const c={...components[id],...overrides};return `<button class="node ${esc(c.type)}" data-component="${id}" aria-pressed="${selected===id}"><span class="node-top">${icon(c.icon)} ${esc(c.tag)}</span><span class="node-title">${esc(c.title)}</span><span class="node-sub">${esc(c.sub)}</span>${c.notes?`<span class="note-marker" aria-label="Review notes ${c.notes.join(', ')}">${c.notes.join('·')}</span>`:""}</button>`;};
const currentWorkflow = () => designWorkflowMap[workflowName];
const currentPath = () => currentWorkflow().paths.find(path => path.id === pathId) || currentWorkflow().paths[0];
const pathHasPlanning = path => path.stages.includes("$planning");
const workflowHasPlanning = workflow => workflow.paths.some(pathHasPlanning);
const expandedStages = path => path.stages.flatMap(id => id === "$planning" ? ["planning-choice", "planner-brief", "planner-investigate", "research-team", "synthesize-plan", "review-plan"] : [id]);
const stageDescendants = id => [id, ...(workflowCatalog.stages[id].chain || []).flatMap(stageDescendants)];
function pathAgents(workflow, path, stages=workflowCatalog.stages) {
  const required = new Set(), conditional = new Set(workflow.support || []);
  if (pathHasPlanning(path)) { required.add("planner"); conditional.add("researcher"); }
  const visit=(id,parentConditional=false)=>{
    const stage=stages[id], isConditional=parentConditional||Boolean(stage.condition);
    if(stage.role)(isConditional?conditional:required).add(stage.role);
    for(const child of stage.chain||[])visit(child,isConditional);
  };
  for (const id of path.stages.filter(id => id !== "$planning"))visit(id);
  for (const role of required) conditional.delete(role);
  return {required: [...required], conditional: [...conditional]};
}
function workflowAgentUsage(workflow, role) {
  const uses = workflow.paths.map(path => pathAgents(workflow, path));
  if (uses.every(use => use.required.includes(role))) return "Required";
  if (uses.some(use => use.required.includes(role))) return "Some paths";
  if (uses.some(use => use.conditional.includes(role))) return "Conditional";
  return null;
}
const agentWorkflows = role => workflowCatalog.workflows.map(workflow => ({workflow, usage: workflowAgentUsage(workflow, role)})).filter(item => item.usage);
const roleOutputs = {
  planner:"A Markdown plan, optional requested HTML, source evidence, and unresolved decisions.",
  specifier:"A RED seal, acceptance-test map, and builder handoff.",
  builder:"Local source revision, fresh GREEN, runtime proof, and independent review evidence.",
  reviewer:"Structured findings, severity, evidence, and any refutation outcome.",
  integrator:"Command-linked verification for the supplied source and current gate state.",
  researcher:"Read-only findings with source references, coverage, and unresolved questions.",
  documenter:"Scoped documentation artifacts and validation evidence.",
  deployer:"Deployment and verification evidence, including any rollback outcome.",
  debugger:"Reproduction evidence and an isolated cause or bottleneck.",
  profiler:"Benchmark distributions, measurement environment, and before/after comparison.",
};
for (const workflow of workflowCatalog.workflows) {
  components[`workflow-${workflow.name}`] = {
    title:workflow.title,type:"artifact",icon:"flow",tag:`/nova:${workflow.name}`,sub:workflow.summary,
    text:workflow.summary,input:"The requested outcome and existing user decisions.",output:workflow.outcome,
    rules:[...(workflow.note ? [workflow.note] : []), ...(workflowHasPlanning(workflow) ? ["New plans use planner authorship and internal research. Team size is chosen by the orchestrator; the user chooses one plan or multiple ideas."] : [])],
    sources:[{path:workflow.source,line:1}],
  };
}
for (const [id, stage] of Object.entries(workflowCatalog.stages)) {
  const owners = workflowCatalog.workflows.filter(workflow => workflow.paths.some(path => expandedStages(path).flatMap(stageDescendants).includes(id)));
  components[`stage-${id}`] = {
    title:stage.title,type:stage.kind,icon:stage.role ? components[stage.role].icon : stage.kind === "gate" ? "shield" : "branch",tag:stage.role || (stage.kind === "human" ? "Orchestrator / user" : stage.kind === "gate" ? "Evidence gate" : "Artifact / tool"),sub:stage.condition || stage.parallel || stage.detail,
    text:stage.detail,input:"The workflow brief, current source context, and preceding evidence or decisions.",output:stage.role ? roleOutputs[stage.role] : "The recorded decision or artifact described by this stage.",
    rules:[...(stage.condition ? [stage.condition] : []), ...(stage.parallel ? [stage.parallel] : []), ...(stage.branches || []).map(([condition, result]) => `${condition}: ${result}`)],
    sources:[...(stage.role ? [{path:`agents/bodies/${stage.role}.md`,line:1}] : []), ...owners.map(workflow => ({path:workflow.source,line:1}))],
  };
}
for (const workflow of designWorkflows) {
  components[`preview-workflow-${workflow.name}`] = {
    title:workflow.title,type:"artifact",icon:"flow",tag:`${workflow.kind === "auxiliary" ? "Auxiliary skill" : "Workflow"} · /${workflow.name}`,sub:workflow.summary,
    text:workflow.summary,input:"The requested outcome and existing user decisions.",output:workflow.outcome,
    rules:["Implemented workflow in the current repository registry.",...(workflow.note ? [workflow.note] : []),...(workflowHasPlanning(workflow) ? ["Planners author the approaches and final plan; the orchestrator compares and reviews. Planning owns its research stage."] : [])],
    sources:designSources(workflow),
  };
}
for (const [id,stage] of Object.entries(designStages)) {
  const owners=designWorkflows.filter(workflow=>workflow.paths.some(path=>expandedStages(path).flatMap(designStageDescendants).includes(id)));
  if (!owners.length) continue;
  const sourcePaths=[...new Set([...(stage.role ? [`agents/bodies/${stage.role}.md`] : []),...owners.flatMap(workflow=>designSources(workflow).map(source=>source.path))])];
  components[`preview-stage-${id}`] = {
    title:stage.title,type:stage.kind,icon:stage.role ? components[stage.role].icon : stage.kind === "gate" ? "shield" : "branch",tag:stage.role || (stage.kind === "human" ? "Orchestrator / user" : stage.kind === "gate" ? "Evidence gate" : "Artifact / tool"),sub:stage.condition || stage.parallel || stage.detail,
    text:stage.detail,input:"The workflow brief, source context, and preceding evidence or decisions.",output:stage.role ? roleOutputs[stage.role] : "The recorded decision or artifact described by this stage.",
    rules:[...(stage.condition ? [stage.condition] : []),...(stage.parallel ? [stage.parallel] : []),...(stage.branches || []).map(([condition,result])=>`${condition}: ${result}`)],
    sources:sourcePaths.map(path=>({path,line:1})),
  };
}
const steps = () => expandedStages(currentPath()).flatMap(id => designStageDescendants(id).map(child => `preview-stage-${child}`));
function workflowControls() {
  const groups=[['Main workflows',['plan','build','review','debug','profile','docs','refactor']],['Prepare & operate',['repo-setup','deploy','wiki']],['Auxiliary skills',['jj','use-other-harness']]];
  const selectedName=workflowName==='perf'?'profile':workflowName;
  return `<label class="workflow-select-label" for="workflow-select">Workflow <select id="workflow-select">${workflowName==='research'?'<option value="research" selected disabled>Research · harness capability</option>':''}${groups.map(([label,names])=>`<optgroup label="${esc(label)}">${names.map(name=>`<option value="${name}" ${selectedName===name?'selected':''}>/${name}</option>`).join('')}</optgroup>`).join('')}</select></label>`;
}

function agentBadges(roles, qualifier = "") {
  return roles.map(role => `<a class="agent-badge ${qualifier ? 'conditional-agent' : ''}" href="#agents/${role}">${esc(role)}${qualifier ? ` <span>${esc(qualifier)}</span>` : ""}</a>`).join("");
}
function stageMarkup(id, index) {
  const stage = designStages[id];
  const branches = stage.branches ? `<div class="stage-branches">${stage.branches.map(([condition, result]) => `<div><b>${esc(condition)}</b><span>${esc(result)}</span></div>`).join("")}</div>` : "";
  const chain = stage.chain ? `<div class="issue-chains">${["A", "B"].map(letter => `<div class="issue-chain"><span class="issue-chain-label">Issue ${letter}<small>isolated workspace</small></span><div class="chain-nodes">${stage.chain.map(child => node(`preview-stage-${child}`, {sub:designStages[child].role, notes:undefined})).join("")}</div></div>`).join("")}<p>Illustrative independent issues; each chain keeps its own order.</p></div>` : "";
  return `<section class="workflow-stage ${stage.condition ? 'conditional-stage' : ''}"><div class="stage-number">${String(index+1).padStart(2,"0")}</div><div class="stage-content"><div class="stage-summary">${node(`preview-stage-${id}`, {sub:stage.role || (stage.kind === "gate" ? "Evidence" : "Decision / artifact"), notes:undefined})}<div class="stage-explanation">${stage.condition ? `<span class="condition-label">${esc(stage.condition)}</span>` : ""}${stage.parallel ? `<span class="parallel-label">${esc(stage.parallel)}</span>` : ""}<p>${esc(stage.detail)}</p></div></div>${chain}${branches}</div></section>`;
}
function legacyFlowMarkup() {
  const workflow=currentWorkflow(), path=currentPath(), agents=pathAgents(workflow,path,designStages);
  const group = designGroups.find(group=>group.id===workflow.group);
  return `<div class="workflow-flow">
    <div class="workflow-preview"><span>IMPLEMENTED WORKFLOW</span><p>Current repository stages and evidence. Team sizes follow useful work and actual runtime capacity.</p></div>
    <div class="workflow-heading"><div><span class="kicker">${workflow.kind === 'auxiliary' ? 'AUXILIARY SKILL' : 'WORKFLOW'} / ${esc(workflow.name)}</span><h2>${esc(workflow.title)}</h2><p>${esc(workflow.summary)}</p></div><span class="coverage-pill">${esc(group.title)}</span></div>
    <div class="workflow-orientation"><span>${workflow.kind === 'auxiliary' ? 'A supporting operation called within the applicable workflow.' : 'Read top to bottom: decisions → delegated stages → evidence → result.'}</span><a href="#tree">View workflow choices ↗</a></div>
    ${workflow.paths.length > 1 ? `<div class="path-controls"><span>Execution path</span><div class="mode-toggle" role="group" aria-label="Execution path">${workflow.paths.map(item=>`<button data-path="${esc(item.id)}" class="${item.id===path.id?'active':''}" aria-pressed="${item.id===path.id}">${esc(item.label)}</button>`).join("")}</div></div>` : ""}
    ${pathHasPlanning(path) ? `<div class="path-controls"><span>Planning preview</span><div class="mode-toggle" role="group" aria-label="Planning preview">${Object.entries({single:"One plan",multiple:"Multiple plan ideas"}).map(([id,label])=>`<button data-planning-mode="${id}" class="${planningMode===id?'active':''}" aria-pressed="${planningMode===id}">${label}</button>`).join("")}</div></div><p class="workflow-planning-caption">Planners author and revise approaches; the orchestrator compares and reviews them. Markdown is the default. HTML is added only when requested; saved choices carry through resume.</p>` : ""}
    <div class="workflow-agents"><div><span class="agent-caption">Agents in this path</span>${agents.required.length ? agentBadges(agents.required) : '<span class="agent-empty">Orchestrator / tool operations</span>'}</div>${agents.conditional.length ? `<div><span class="agent-caption">Conditional support</span>${agentBadges(agents.conditional,"conditional")}</div>` : ""}</div>
    ${workflow.note ? `<p class="workflow-note">${esc(workflow.note)}</p>` : ""}
    <div class="stage-timeline">${expandedStages(path).map(stageMarkup).join("")}</div>
    <div class="workflow-outcome"><span>OUTCOME</span><strong>${esc(path.outcome || workflow.outcome)}</strong></div>
    <div class="walkthrough"><span>Execution preview · no agents are launched</span><button class="walk-button" id="next-step">${step < 0 ? "Walk through the flow" : "Next step"} →</button></div>
  </div>`;
}

function layer(number,title,caption,ids,cls=""){return `<section class="layer ${cls}"><div class="layer-heading"><h2><span class="layer-number">${number}</span>${title}</h2><span class="kicker">${caption}</span></div><div class="layer-grid ${ids.length===4?'four':ids.length===2?'two':''}">${ids.map(id=>node(id)).join("")}</div></section>`;}
function architectureMarkup(){return `<div class="diagram-scroll"><div class="architecture">${layer("01","Shared source","Nova repository",["contracts","agentSource","skillSource"])}${layer("02","Harness distributions","Sync → stage → owned copy",["claude","codex","agy"],"install")}${layer("03","Execution support","Tools called by the harness",["workspace","guard","ledger","utilities"])}${layer("04","State & evidence","Different persistence boundaries",["github","handoff","state","wiki"])}<div style="margin-top:22px">${node("controlplane")}</div><p class="arch-aside">The run ledger executes integration and resume. Agent launch, concurrency limits, retries, and cancellation remain orchestrator responsibilities. The controlplane package supplies library contracts.</p></div></div>`;}
function agentsMarkup(){return `<p class="roster-intro">Only the roles needed by an entry workflow are dispatched. Researchers, debuggers, and profilers support the relevant investigation; they are not mandatory stages of every issue.</p><div class="roster-grid">${roleIds.map(id=>{const c=components[id];return `<button class="role-card" data-component="${id}" aria-pressed="${selected===id}"><span class="role-icon">${icon(c.icon)}</span><span><h2>${c.title}</h2><p>${esc(c.sub)}</p><div class="role-scope">${esc(c.tag)}</div><div class="role-usage-count">Used in ${agentWorkflows(id).length} workflows · select for details</div></span></button>`;}).join("")}</div><div style="margin-top:18px">${node("orchestrator")}</div>`;}
function gatesMarkup(){return `<p class="gate-caption">The first five steps use guard records and, where wired, native hooks. Runtime proof remains a builder contract checked through its handoff.</p><div class="gate-grid">${["seal","protect","verify","diffreview","stop","runtime"].map(id=>node(id)).join("")}</div><div class="matrix-wrap"><h2>Same contracts, different enforcement</h2><table class="matrix"><thead><tr><th scope="col">Harness</th><th scope="col">Native hooks</th><th scope="col">Activation / merge boundary</th></tr></thead><tbody><tr><td>Claude Code</td><td><span class="status-text">Wired</span></td><td>Main-conversation identity distinguishes merges</td></tr><tr><td>Codex</td><td><span class="conditional">Conditional</span></td><td>User must trust hooks with /hooks</td></tr><tr><td>Antigravity</td><td><span class="conditional">Session-wide</span></td><td>Scoped activation; merges remain denied</td></tr></tbody></table><p class="matrix-note">This describes checked-in adapters, not the trust or installation state of a running session.</p></div><div style="margin-top:22px">${node("evals")}</div><div class="review-summary"><b>Source freshness is now enforced</b>A failed verification removes prior GREEN, and a changed source tree cannot regain readiness by recording another review. <button data-component="verify">Inspect the updated guard →</button></div>`;}
const context={
  tree:[["Separate outcomes","Native research sits outside the Nova workflow menu. Planning keeps its internal investigation and evidence handoff. Plan, review, debug, profile, and refactor assessment finish with their own results. Supported, authorized changes can continue into build."],["Reuse completed work","Carry plans, selected findings, source context, user decisions, and authorization into the next workflow."],["Keep useful entry points","Documentation has its own workflow and can also be a build stage. Setup, deployment, wiki, and auxiliary skills remain accessible."]],
  flow:[["Workflow means an execution contract","Each diagram shows its decisions, delegated agents, evidence, and completed outcome. Supporting operations keep their existing detail views."],["Orchestrator chooses team sizes","All roles can use the number of agents the work needs, without workflow-imposed caps. Diagram detail only changes what is drawn."],["One coordinator, clear ownership","Orchestrator boxes show checkpoints for the same agent. It directs scheduling and revisions while specialists own their assigned work."]],
  architecture:[["Source and installed copies","Harnesses load staged, installer-owned copies. Editing this checkout does not update an installed plugin until it is rebuilt and installed."],["Mechanical and procedural","A shared role definition is portable. Hook activation, payload formats, and merge permissions differ by harness."],["Evidence outlives the checkout","Guard state and the opt-in wiki live outside the repository. Guard identity is still keyed to a workspace path."]],
  agents:[["One completion authority","Specialists return done, blocked, or needs-decision. The orchestrator decides whether the overall work is accepted."],["Independent review","The builder asks a fresh read-only reviewer for assurance. Critical and high findings block handoff."],["Shared return shape","anvil.agent-handoff/v1 carries changed files, commands, evidence, runtime observations, and open questions."]],
  gates:[["A seal is not a successful build","Specifier handoff allows the test author to stop without GREEN. It never makes the issue ready to merge."],["Tests and runtime are different evidence","The guard checks its own records. A real browser, endpoint, or CLI exercise is recorded separately in evidence.runtime."],["Structural checks have limits","Instruction parity and routing scores do not execute an end-to-end wave. Behavioral validation also needs the actual action trace."]],
};

function renderInspector(){const c=components[selected];if(!c)return;const sourceLinks=(c.sources||[]).map(src=>`<a href="${SOURCE}${encodeURIComponent(src.path)}#L${src.line}" target="_blank" rel="noreferrer">${esc(src.path)}:${src.line} ↗</a>`).join("");el("inspector").innerHTML=`<div class="inspector-header"><div class="eyebrow">COMPONENT DETAILS</div><div class="detail-icon">${icon(c.icon)}</div><h2>${esc(c.title)}</h2><div class="detail-type">${esc(c.tag)}</div>${view==='flow'&&step>=0?`<div class="detail-step" aria-label="Step ${step+1} of ${steps().length}">${steps().map((_,i)=>`<span class="${i<=step?'on':''}"></span>`).join("")}</div>`:""}</div><div class="inspector-body"><p>${esc(c.text)}</p><section class="detail-section"><h3>RECEIVES</h3><p>${esc(c.input||'Canonical repository definitions.')}</p></section><section class="detail-section"><h3>RETURNS</h3><p>${esc(c.output||'A result for the next stage.')}</p></section>${c.rules?`<section class="detail-section"><h3>BOUNDARIES</h3><ul>${c.rules.map(x=>`<li>${esc(x)}</li>`).join("")}</ul></section>`:""}${roleIds.includes(selected)?`<section class="detail-section"><h3>USED BY WORKFLOWS</h3><div class="role-usage-list">${agentWorkflows(selected).map(({workflow,usage})=>`<a href="#flow/${workflow.name}"><b>${workflow.name}</b><span>${usage}</span></a>`).join("")}</div></section>`:""}${c.command?`<section class="detail-section"><h3>COMMAND CONTRACT</h3><code class="code">${esc(c.command)}</code></section>`:""}${(c.notes||[]).map(n=>`<div class="review-note"><strong>CHANGE ${n} / IMPLEMENTED</strong>${esc(notes[n])}</div>`).join("")}<section class="detail-section"><h3>${['flow','tree'].includes(view)?'IMPLEMENTED WORKFLOW · SOURCE REFERENCES':'SOURCE SNAPSHOT · WORKING TREE'}</h3><div class="source-links">${sourceLinks}</div></section></div>`;document.querySelectorAll('[data-component]').forEach(button=>{if(button.classList.contains('node')||button.classList.contains('role-card')||button.classList.contains('rev-node'))button.setAttribute('aria-pressed',String(button.dataset.component===selected));});}
function render(){
  const v=views[view]; document.body.dataset.view=view;
  el("navigation").innerHTML=Object.entries(views).map(([id,item])=>`<a class="nav-link ${view===id?'active':''}" href="#${id}" ${view===id?'aria-current="page"':''}>${icon(item.icon)}${item.name}</a>`).join("");
  el("page-eyebrow").textContent=v.eyebrow; el("page-title").textContent=v.title; el("page-description").textContent=v.description;
  el("view-controls").innerHTML=view==='flow'?workflowControls():`<span class="toolbar-title">${view==='tree'?'WORKFLOW CHOICES → SHARED BUILD':view==='architecture'?'SOURCE → DISTRIBUTION → EXECUTION':view==='agents'?'SPECIALIST ROLE REGISTRY':'ENFORCEMENT MAP'}</span>`;
  el("canvas").innerHTML=({flow:diagramExecutionMarkup,tree:diagramTreeMarkup,architecture:architectureMarkup,agents:agentsMarkup,gates:gatesMarkup})[view]();
  fitTreeDiagram();
  el("context-strip").innerHTML=context[view].map(([title,text])=>`<div class="context-item"><h3>${title}</h3><p>${text}</p></div>`).join("");
  renderInspector(); document.title=`Nova · ${view==='flow'?(executionDesign.workflows[diagramForCurrentWorkflow()]?.title||currentWorkflow().title):v.name}`;
}
function route(){
  const [key, requested, requestedPath]=location.hash.slice(1).split('/');
  // Previously shared comparison links now land on the current workflow or tree.
  if(key==='proposal'){
    location.replace(requested && designWorkflowMap[requested]?`#flow/${requested}`:'#tree');
    return;
  }
  view=Object.hasOwn(views,key)?key:'tree';
  if(view==='flow'){
    const alias=workflowDesign.aliases[requested];
    if(requested==='research'){workflowName='research';pathId='';}
    else{
      workflowName=designWorkflowMap[requested]?requested:alias?alias.workflow:'build';
      pathId=alias?alias.path:currentWorkflow().paths[0].id;
      if(requestedPath && currentWorkflow().paths.some(path=>path.id===requestedPath))pathId=requestedPath;
    }
    if(requested==='simple-build'||['bounded','detail'].includes(requestedPath))diagramScale='detail';
    if(requested==='complex-build'||['coordinated','team'].includes(requestedPath))diagramScale='team';
    if(workflowName==='refactor' || workflowName==='build' && requestedPath==='refactor')diagramKind='refactor';
    if(workflowName==='debug')diagramKind='fix';
    const core=diagramForCurrentWorkflow();
    selected=executionDesign.workflows[core]?'diagram-'+core:`preview-workflow-${workflowName}`;
  }else selected=view==='agents'&&roleIds.includes(requested)?requested:views[view].selected;
  step=-1;render();
}

diagramRegisterComponents();
document.addEventListener('change',event=>{if(event.target.id==='workflow-select') location.hash=`flow/${event.target.value}`;});
document.addEventListener('click',event=>{
  const option=event.target.closest('[data-diagram-option]');
  if(option){
    const {diagramOption:key,value}=option.dataset;
    if(key==='plan' && ['single','multiple'].includes(value))diagramPlanMode=value;
    if(key==='scale' && ['detail','team'].includes(value))diagramScale=value;
    if(key==='kind' && ['behavior','fix','refactor','optimization'].includes(value))diagramKind=value;
    if(key==='fit' && ['fit','full'].includes(value))treeFitsWidth=value==='fit';
    step=-1;render();return;
  }
  const component=event.target.closest('[data-component]');
  if(component){selected=component.dataset.component;renderInspector();return;}
  const planningButton=event.target.closest('[data-planning-mode]');
  if(planningButton){planningMode=planningButton.dataset.planningMode;selected='preview-stage-planning-choice';step=-1;render();return;}
  const pathButton=event.target.closest('[data-path]');
  if(pathButton){location.hash=`flow/${workflowName}/${pathButton.dataset.path}`;return;}
  if(event.target.closest('#next-step')){step=(step+1)%steps().length;selected=steps()[step];renderInspector();el('next-step').innerHTML=`${step===steps().length-1?'Start again':'Next step'} →`;}
});
el('show-notes').addEventListener('change',event=>document.body.classList.toggle('hide-notes',!event.target.checked));
window.addEventListener('hashchange',route);
route();
