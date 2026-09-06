"use strict";

// Current workflows and legacy diagram routes; validated against the registry.
const workflowCatalog = {
  "groups": [
    {
      "id": "understand",
      "title": "Plan an approach",
      "question": "One plan or multiple ideas?"
    },
    {
      "id": "change",
      "title": "Change software",
      "question": "Build, debug, refactor, review, profile, or document?"
    },
    {
      "id": "operate",
      "title": "Prepare & operate",
      "question": "Set up, release, or retain knowledge?"
    },
    {
      "id": "auxiliary",
      "title": "Auxiliary skills",
      "question": "Version control or a named harness?"
    }
  ],
  "stages": {
    "scope": {
      "detail": "Read the relevant source and preserve the user’s goal, constraints, ownership, and acceptance criteria. Resolve material unanswered requirements before planning; reuse decisions the user already supplied.",
      "title": "Confirm scope and existing decisions",
      "kind": "human",
      "role": null
    },
    "route-build": {
      "title": "Choose execution shape",
      "detail": "Reuse existing plans and findings. Single changes and dependency runs are internal execution shapes.",
      "kind": "human",
      "role": null
    },
    "planning-choice": {
      "title": "One plan or multiple ideas?",
      "detail": "Ask only when the request and saved choice do not answer. The choice sets output, not agent count.",
      "kind": "human",
      "role": null
    },
    "synthesize-plan": {
      "title": "Author plan artifacts",
      "detail": "Planners combine evidence into Markdown and an executable sidecar when needed. Add HTML only when explicitly requested.",
      "kind": "agent",
      "role": "planner"
    },
    "brief": {
      "title": "Save the scoped brief",
      "detail": "Record scope, source revision, ownership, acceptance criteria, authorization, and verification commands outside the tested workspace.",
      "kind": "artifact",
      "role": null
    },
    "folio": {
      "title": "Plan artifacts",
      "detail": "Markdown by default, strict dependency sidecar when needed, explicit HTML companion.",
      "kind": "artifact",
      "role": null
    },
    "approve-plan": {
      "title": "Approve the exact plan",
      "detail": "Obtain approval of the reviewed artifacts before GitHub reconciliation. A changed sidecar needs renewed approval.",
      "kind": "human",
      "role": null,
      "branches": [
        [
          "Not approved",
          "Keep the offline plan; no GitHub writes"
        ],
        [
          "Exact revision approved",
          "Reconcile the approved plan"
        ]
      ]
    },
    "reconcile": {
      "title": "Optional issue tracking",
      "detail": "Create or update GitHub issues only when wanted and authorized. Local task IDs need no GitHub issues.",
      "kind": "artifact",
      "role": null
    },
    "queue": {
      "title": "Select dependency-ready work",
      "detail": "Reuse the run ledger and accepted receipts. Parallel work must have disjoint implementation and test ownership.",
      "kind": "artifact",
      "role": null
    },
    "red": {
      "title": "Seal failing acceptance tests",
      "detail": "The specifier authors the acceptance tests, demonstrates honest RED, seals them, and hands off the retained workspace.",
      "kind": "agent",
      "role": "specifier"
    },
    "baseline": {
      "title": "Seal the GREEN baseline",
      "detail": "The integrator proves existing tests GREEN and protects them unchanged. A refactor never invents new failing tests.",
      "kind": "agent",
      "role": "integrator"
    },
    "implement": {
      "title": "Implement against the seal",
      "detail": "The builder changes only its assigned implementation, preserves sealed tests, and verifies fresh GREEN.",
      "kind": "agent",
      "role": "builder"
    },
    "refactor-implement": {
      "title": "Implement without changing behavior",
      "detail": "The builder runs in refactor mode, preserves existing tests and behavior, and verifies the bound baseline command.",
      "kind": "agent",
      "role": "builder"
    },
    "runtime": {
      "title": "Exercise the changed surface",
      "detail": "The builder records real runtime evidence for a changed UI, service, or CLI, or explains why no runnable surface applies.",
      "kind": "agent",
      "role": "builder"
    },
    "review": {
      "title": "Independent review",
      "detail": "Choose useful lenses and team sizes; iterate from findings and progress without a workflow attempt quota.",
      "kind": "agent",
      "role": "reviewer"
    },
    "verify-single": {
      "title": "Verify the exact final source",
      "detail": "The integrator verifies the already-combined source directly, with current guard evidence and all required checks.",
      "kind": "agent",
      "role": "integrator"
    },
    "verify-combined": {
      "title": "Verify combined candidates",
      "detail": "The integrator tests combined source, checks conflicts and ownership, and returns command-linked candidate evidence.",
      "kind": "agent",
      "role": "integrator"
    },
    "accept": {
      "title": "Accept from current evidence",
      "detail": "The orchestrator checks source identity, fresh GREEN, independent review, and required outcomes before recording acceptance.",
      "kind": "human",
      "role": null,
      "branches": [
        [
          "Failed or stale evidence",
          "Return to the responsible specialist"
        ],
        [
          "Current evidence passes",
          "Record acceptance; local readiness is not merge"
        ]
      ]
    },
    "docs-change": {
      "title": "Relevant documentation",
      "detail": "Documenters update assigned scopes before final combined verification; do not launch standalone /docs recursively.",
      "kind": "agent",
      "role": "documenter"
    },
    "final-source": {
      "title": "Verify final combined source",
      "detail": "Integrator checks code and documentation at the exact final source, with fresh evidence. Remeasure performance work.",
      "kind": "agent",
      "role": "integrator"
    },
    "pr": {
      "title": "Open the final pull request",
      "detail": "Use the verified source head and real closing references. Do not fabricate an issue or treat local acceptance as a merge.",
      "kind": "artifact",
      "role": null
    },
    "remote-checks": {
      "title": "Read remote checks",
      "detail": "Check the final PR head and required CI before an authorized merge. A moving target can require refreshed verification.",
      "kind": "gate",
      "role": null
    },
    "merge": {
      "title": "Merge within authorization",
      "detail": "Only the orchestrator completes an authorized merge. Deployment remains a separate workflow.",
      "kind": "human",
      "role": null,
      "condition": "When merge is authorized"
    },
    "feature-issues": {
      "title": "Build independent issue chains",
      "detail": "Each ready issue keeps its own test → implementation → review order. Independent issues can overlap in separate workspaces.",
      "kind": "artifact",
      "role": null,
      "chain": [
        "red",
        "implement",
        "runtime",
        "review"
      ],
      "parallel": "Per dependency-ready issue"
    },
    "interview": {
      "title": "Resolve material user decisions",
      "detail": "Ask only what source and prior decisions do not establish. Carry answers into every relevant dispatch.",
      "kind": "human",
      "role": null
    },
    "diagnose": {
      "branches": [
        [
          "Failure reproduced and cause supported",
          "Return the diagnosis; enter build only when repair is authorized"
        ],
        [
          "Reproduction or causal evidence is missing",
          "Return attempts and missing conditions without beginning implementation"
        ]
      ],
      "title": "Reproduce and isolate the cause",
      "kind": "agent",
      "role": "debugger",
      "detail": "Debuggers use experiments to establish the reported failure and its cause. Investigation-only requests return a diagnosis; requested repair carries its source, reproduction, and evidence into shared build."
    },
    "benchmark-before": {
      "title": "Measure the performance baseline",
      "detail": "Use the project’s existing benchmark harness; record environment, run count, median, and spread.",
      "kind": "agent",
      "role": "profiler",
      "branches": [
        [
          "No benchmark harness",
          "Stop; establish a real harness first"
        ],
        [
          "Harness available",
          "Record a reproducible baseline"
        ]
      ]
    },
    "correctness-before": {
      "title": "Check existing correctness",
      "detail": "The integrator runs the documented verification on the unchanged source before a refactor or optimization.",
      "kind": "agent",
      "role": "integrator"
    },
    "bottleneck": {
      "title": "Locate the actual bottleneck",
      "detail": "The debugger uses profiling and the measured baseline to identify where time is spent.",
      "kind": "agent",
      "role": "debugger"
    },
    "benchmark-after": {
      "title": "Measure the changed code",
      "detail": "Repeat the same benchmark on the same machine and report the comparison and uncertainty.",
      "kind": "agent",
      "role": "profiler"
    },
    "gain": {
      "title": "Decide whether the gain is real",
      "detail": "The orchestrator evaluates improvement against the baseline spread while preserving correctness.",
      "kind": "human",
      "role": null,
      "branches": [
        [
          "Outside the noise; correctness preserved",
          "Keep and verify the optimization"
        ],
        [
          "Within noise or a regression",
          "Drop the optimization; report the result"
        ]
      ]
    },
    "refactor-survey": {
      "title": "Assess structural friction",
      "detail": "Planners identify demonstrated duplication, shallow interfaces, dead paths, and coupling, then propose simplifications with contracts and tests to preserve. Reuse an accepted assessment instead of repeating it.",
      "kind": "agent",
      "role": "planner",
      "condition": "When current assessment evidence is missing"
    },
    "analysis-baseline": {
      "title": "Map pre-existing failures",
      "detail": "The integrator records the initial suite result so the defect sweep can distinguish pre-existing failures from regressions.",
      "kind": "agent",
      "role": "integrator"
    },
    "hunt": {
      "title": "Hunt concrete defects",
      "detail": "Reviewers inspect applicable lenses, always including correctness and tests, and return concrete failure scenarios.",
      "kind": "agent",
      "role": "reviewer",
      "parallel": "One reviewer per applicable lens"
    },
    "refute": {
      "title": "Adversarially verify findings",
      "detail": "A fresh reviewer that did not originate a finding attempts to refute it. Unsupported findings are dropped and reported.",
      "kind": "agent",
      "role": "reviewer",
      "parallel": "Independent verification of candidates"
    },
    "dedupe-findings": {
      "title": "Deduplicate and rank evidence",
      "detail": "Merge findings deterministically, require verification records, and retain both substantiated and refuted candidates.",
      "kind": "artifact",
      "role": null
    },
    "review-report": {
      "title": "Verified review report",
      "detail": "Markdown findings, evidence, coverage, and severity. HTML is an explicit companion.",
      "kind": "artifact",
      "role": null
    },
    "approve-findings": {
      "title": "Approve issue creation",
      "detail": "Get approval of the exact review before optional GitHub issue reconciliation.",
      "kind": "human",
      "role": null,
      "condition": "Only when tracking the findings is requested"
    },
    "track-findings": {
      "title": "Reconcile verified findings",
      "detail": "Create or update marker-based GitHub issues from the approved review without duplicating existing work.",
      "kind": "artifact",
      "role": null
    },
    "repo-survey": {
      "title": "Survey the existing repository",
      "detail": "The researcher inventories the stack, manifests, CI, instructions, VCS, and real build/test/lint commands.",
      "kind": "agent",
      "role": "researcher"
    },
    "repo-vcs": {
      "title": "Apply the chosen VCS setup",
      "detail": "Preserve plain Git when chosen; adopt Jujutsu only for the selected repository setup.",
      "kind": "artifact",
      "role": null
    },
    "repo-instructions": {
      "title": "Write canonical repository guidance",
      "detail": "The documenter records the agreed commands and conventions in one instruction source, with harness-specific links.",
      "kind": "agent",
      "role": "documenter"
    },
    "repo-tools": {
      "title": "Set up tooling and gates",
      "detail": "Set up the agreed tooling and gates. Repository configuration that changes executable behavior enters shared build.",
      "kind": "artifact",
      "role": null
    },
    "repo-config": {
      "title": "Build requested configuration changes",
      "detail": "Carry the agreed CI or build-configuration scope into shared build, including applicable tests, independent review, documentation, and final verification.",
      "kind": "human",
      "role": null,
      "condition": "Only when configuration code needs changes",
      "chain": [
        "shared-build"
      ]
    },
    "repo-verify": {
      "title": "Prove the documented commands",
      "detail": "The integrator executes the actual build, test, and lint commands and returns evidence.",
      "kind": "agent",
      "role": "integrator"
    },
    "repo-report": {
      "title": "Return the setup result",
      "detail": "Report what was configured, verification outcomes, and any remaining decisions.",
      "kind": "artifact",
      "role": null
    },
    "docs-inventory": {
      "title": "Audit documentation truth",
      "detail": "The documenter inventories stale, duplicate, missing, and misplaced material before changing it.",
      "kind": "agent",
      "role": "documenter"
    },
    "docs-update": {
      "title": "Update the scoped documents",
      "detail": "The same role updates documentation, instructions, ADRs, and relevant handover records within its assigned ownership.",
      "kind": "agent",
      "role": "documenter"
    },
    "docs-check": {
      "title": "Run the documentation gate",
      "detail": "The documenter runs docs_check and the diagram generator check where applicable, returning exact outcomes and coverage.",
      "kind": "agent",
      "role": "documenter"
    },
    "docs-accept": {
      "title": "Accept the documentation evidence",
      "detail": "The orchestrator reads the mechanical gate and confirms that every requested area is covered.",
      "kind": "gate",
      "role": null
    },
    "release-notes": {
      "title": "Prepare version and release notes",
      "detail": "The documenter prepares changelog, release notes, and upgrade callouts. Executable versioning or release logic belongs to the shared build handoff.",
      "kind": "agent",
      "role": "documenter"
    },
    "release": {
      "title": "Create the requested release",
      "detail": "The orchestrator tags and publishes the GitHub release using the prepared notes, within the release authorization.",
      "kind": "artifact",
      "role": null
    },
    "release-ci": {
      "title": "Build release automation changes",
      "detail": "Requested CI/CD or release logic changes enter shared build before release, preserving verification evidence and authorization.",
      "kind": "human",
      "role": null,
      "condition": "Only when the pipeline needs changes",
      "chain": [
        "shared-build"
      ]
    },
    "deploy-approval": {
      "title": "Approve target and commit",
      "detail": "Explicit deployment approval identifies this environment and immutable commit before the deployer is dispatched.",
      "kind": "human",
      "role": null,
      "branches": [
        [
          "Approval absent",
          "Stop before deployment"
        ],
        [
          "Target and commit approved",
          "Dispatch the deployer"
        ]
      ]
    },
    "preflight": {
      "title": "Run preflight and confirm rollback",
      "detail": "The deployer checks target readiness, verification commands, and the exact rollback path.",
      "kind": "agent",
      "role": "deployer"
    },
    "deploy": {
      "title": "Deploy or publish the approved source",
      "detail": "The deployer performs the approved deployment or package publication and records its commands.",
      "kind": "agent",
      "role": "deployer"
    },
    "post-deploy": {
      "title": "Verify the deployed result",
      "detail": "The deployer observes the agreed verification window and rolls back on failed checks.",
      "kind": "agent",
      "role": "deployer",
      "branches": [
        [
          "Verification passes",
          "Return deployment evidence"
        ],
        [
          "Verification fails",
          "Run rollback and report its outcome"
        ]
      ]
    },
    "release-handoff": {
      "title": "Record the release outcome",
      "detail": "The documenter records the handover and any non-trivial release decision.",
      "kind": "agent",
      "role": "documenter"
    },
    "wiki-opt-in": {
      "title": "Check project opt-in",
      "detail": "Read wiki.py status. No namespace means no recording or agent dispatch; ask the user before initialization.",
      "kind": "human",
      "role": null,
      "branches": [
        [
          "Not opted in",
          "End without recording or dispatch"
        ],
        [
          "Opted in",
          "Continue in the external project namespace"
        ],
        [
          "Eval mode or identity mismatch",
          "Refuse the run"
        ]
      ]
    },
    "wiki-consolidate": {
      "title": "Consolidate completed-run evidence",
      "detail": "One documenter uses wiki.py to record write-once traces, append patterns, and update the catalog outside the source repository.",
      "kind": "agent",
      "role": "documenter",
      "condition": "Only for an opted-in project"
    },
    "wiki-check": {
      "title": "Verify the namespace",
      "detail": "Read wiki.py check to verify recorded hashes, references, and catalog integrity. Return failures to the same documenter.",
      "kind": "gate",
      "role": null
    },
    "jj-inspect": {
      "title": "Inspect repository state",
      "detail": "Read the working copy, change graph, bookmarks, and relevant diff. This capability applies only where Jujutsu is selected.",
      "kind": "artifact",
      "role": null
    },
    "jj-mutate": {
      "title": "Perform the scoped VCS operation",
      "detail": "Use explicit messages and non-interactive commands for the requested branch, rebase, squash, or other VCS operation.",
      "kind": "artifact",
      "role": null
    },
    "jj-verify": {
      "title": "Verify the resulting state",
      "detail": "Read jj status and the relevant graph or diff. Report unresolved conflicts or unexpected state.",
      "kind": "gate",
      "role": null
    },
    "foreign-request": {
      "title": "Confirm the named harness settings",
      "detail": "This workflow requires an explicit request naming the other harness, model, and effort. Missing choices return to the user.",
      "kind": "human",
      "role": null,
      "branches": [
        [
          "A required setting is missing",
          "Ask; do not guess or launch"
        ],
        [
          "Explicit settings supplied",
          "Run one bounded headless task"
        ]
      ]
    },
    "foreign-run": {
      "title": "Run the headless leaf task",
      "detail": "Launch the named harness with a bounded brief and capture its result. It is a leaf task, not automatic cross-harness routing.",
      "kind": "agent",
      "role": null
    },
    "foreign-result": {
      "title": "Inspect the result and handoff",
      "detail": "The orchestrator reads outputs and any diff, then owns the next integration decision.",
      "kind": "artifact",
      "role": null
    },
    "planner-brief": {
      "title": "Frame and assign approaches",
      "detail": "The orchestrator preserves scope, evidence, and decisions and gives planners distinct directions.",
      "kind": "human",
      "role": null
    },
    "planner-investigate": {
      "title": "Planners investigate",
      "detail": "Own the assigned approach and direct research into its unknowns.",
      "kind": "agent",
      "role": "planner"
    },
    "research-team": {
      "title": "Planner-owned research",
      "detail": "Researchers return attributable evidence to the planner. The orchestrator proxies native dispatch when needed. Team size follows useful work.",
      "kind": "agent",
      "role": "researcher",
      "condition": "When useful to resolve independent planning questions"
    },
    "review-plan": {
      "title": "Orchestrator compares and reviews",
      "detail": "Compare tradeoffs, resolve conflicting evidence, and have a planner author the selected or combined plan.",
      "kind": "human",
      "role": null
    },
    "review-scope": {
      "title": "Scope the review",
      "detail": "The orchestrator pins the source revision, review target, relevant lenses, and requested outcome. A review report is the default; fixes and issue creation require the applicable authorization.",
      "kind": "human",
      "role": null
    },
    "build-transition": {
      "title": "Continue to build?",
      "detail": "Offer build for actionable follow-up. Existing authorization to implement or fix carries through without another question.",
      "kind": "human",
      "role": null
    },
    "shared-build": {
      "title": "Shared build execution",
      "detail": "Reuse selected plan or findings; protect tests, implement, review, combine documentation, verify final source, then authorized delivery.",
      "kind": "gate",
      "role": null,
      "chain": [
        "red",
        "implement",
        "review",
        "docs-change",
        "final-source"
      ]
    },
    "shared-preserving-build": {
      "title": "Shared build with protected baseline",
      "detail": "Preserve observable behavior using GREEN baseline evidence; remeasure performance after optimization.",
      "kind": "gate",
      "role": null,
      "chain": [
        "baseline",
        "refactor-implement",
        "review",
        "docs-change",
        "final-source"
      ]
    },
    "profile-report": {
      "title": "Performance report",
      "detail": "Markdown baseline, hotspots, measurements, uncertainty, and proposed changes. HTML is an explicit companion.",
      "kind": "artifact",
      "role": null
    },
    "diagnosis-report": {
      "title": "Write the diagnosis report",
      "detail": "Return Markdown with the symptom, reproduction, experiments, supported cause, source revision, and remaining gaps. Add HTML only when explicitly requested.",
      "kind": "artifact"
    },
    "diagnosis-finish": {
      "title": "Finish the investigation",
      "detail": "A diagnosis or documented inability to reproduce is a complete outcome. Do not launch a builder or automatically prompt to repair a diagnosis-only request.",
      "kind": "artifact"
    },
    "debug-transition": {
      "title": "Check cause and repair authorization",
      "detail": "Continue only with a supported cause and authorized repair. A debug-and-fix request already authorizes shared build. Reuse the diagnosis and complete brief; plan only missing detail.",
      "kind": "human",
      "branches": [
        [
          "Both conditions hold",
          "Continue through the shared build fix path"
        ],
        [
          "Either condition is missing",
          "Finish with the diagnosis and remaining gaps"
        ]
      ]
    },
    "refactor-research": {
      "title": "Investigate useful independent areas",
      "detail": "The planner directs read-only researchers to investigate source-backed questions and return evidence, conflicts, and gaps. The orchestrator chooses team sizes.",
      "kind": "agent",
      "role": "researcher",
      "condition": "When the assessment has independent unknowns"
    },
    "refactor-report": {
      "title": "Refactor proposal",
      "detail": "The planner returns Markdown with source evidence, selected scope, preserved behavior, existing tests, validation commands, tradeoffs, and gaps. Reuse a current accepted proposal; HTML is an explicit companion.",
      "kind": "artifact",
      "role": null
    },
    "refactor-transition": {
      "title": "Review the proposal and implementation scope",
      "detail": "The orchestrator reviews the evidence. Refactor assessment is a complete outcome; only selected, authorized simplifications continue through build.",
      "kind": "human",
      "role": null,
      "branches": [
        [
          "Report-only request or no worthwhile changes",
          "Finish with the proposal and remaining gaps."
        ],
        [
          "Actionable proposal without implementation authorization",
          "Offer build for the selected changes; continue only if accepted."
        ],
        [
          "Refactor implementation already requested",
          "Reuse that authorization and the proposal; fill only missing executable detail."
        ]
      ]
    }
  },
  "workflows": [
    {
      "name": "build",
      "title": "Build",
      "group": "change",
      "summary": "Reuse the request, selected plan, or findings; orchestrator chooses team size and execution shape.",
      "outcome": "One verified final PR",
      "source": "skills/build/SKILL.md",
      "paths": [
        {
          "id": "bounded",
          "label": "Scoped change",
          "stages": [
            "route-build",
            "scope",
            "$planning",
            "brief",
            "red",
            "implement",
            "runtime",
            "review",
            "docs-change",
            "verify-single",
            "accept",
            "pr",
            "remote-checks",
            "merge"
          ]
        },
        {
          "id": "coordinated",
          "label": "Coordinated work",
          "stages": [
            "route-build",
            "scope",
            "$planning",
            "folio",
            "approve-plan",
            "reconcile",
            "queue",
            "feature-issues",
            "verify-combined",
            "accept",
            "docs-change",
            "final-source",
            "pr",
            "remote-checks",
            "merge"
          ]
        },
        {
          "id": "resume",
          "label": "Resume approved plan",
          "stages": [
            "route-build",
            "queue",
            "feature-issues",
            "verify-combined",
            "accept",
            "docs-change",
            "final-source",
            "pr",
            "remote-checks",
            "merge"
          ]
        }
      ],
      "support": [
        "researcher"
      ]
    },
    {
      "name": "refactor",
      "title": "Refactor",
      "group": "change",
      "summary": "Assess structural simplifications and preserved contracts; implement selected refactors through build when authorized.",
      "outcome": "Refactor proposal; verified simplification when authorized",
      "source": "skills/refactor/SKILL.md",
      "paths": [
        {
          "id": "assess",
          "label": "Assess and report",
          "outcome": "Markdown refactor proposal, preserved contracts, tradeoffs, and remaining gaps",
          "stages": [
            "scope",
            "refactor-survey",
            "refactor-research",
            "refactor-report",
            "refactor-transition"
          ]
        },
        {
          "id": "bounded",
          "label": "Scoped refactor",
          "outcome": "A verified simplification with preserved behavior and unchanged baseline tests",
          "stages": [
            "scope",
            "refactor-survey",
            "refactor-research",
            "refactor-report",
            "refactor-transition",
            "shared-preserving-build"
          ]
        },
        {
          "id": "broad",
          "label": "Broad restructuring",
          "outcome": "Verified refactors in dependency order with preserved behavior",
          "stages": [
            "scope",
            "refactor-survey",
            "refactor-research",
            "refactor-report",
            "refactor-transition",
            "correctness-before",
            "$planning",
            "queue",
            "shared-preserving-build"
          ]
        }
      ],
      "support": [
        "researcher"
      ]
    },
    {
      "name": "debug",
      "title": "Debug",
      "group": "change",
      "summary": "Reproduce a reported failure and return a supported diagnosis; repair only when authorized.",
      "outcome": "Diagnosis report; verified repair when requested",
      "source": "skills/debug/SKILL.md",
      "paths": [
        {
          "id": "diagnose",
          "label": "Investigate only",
          "outcome": "Markdown diagnosis, reproduction evidence, and any remaining gaps",
          "stages": [
            "diagnose",
            "diagnosis-report",
            "diagnosis-finish"
          ]
        },
        {
          "id": "bounded",
          "label": "Diagnose and fix",
          "outcome": "Diagnosis and a verified, authorized repair",
          "stages": [
            "diagnose",
            "diagnosis-report",
            "debug-transition",
            "shared-build",
            "runtime"
          ]
        },
        {
          "id": "dependent",
          "label": "Dependent repairs",
          "outcome": "Diagnosis and verified repairs in dependency order",
          "stages": [
            "diagnose",
            "diagnosis-report",
            "debug-transition",
            "scope",
            "$planning",
            "queue",
            "shared-build",
            "runtime"
          ]
        }
      ]
    },
    {
      "name": "profile",
      "title": "Profile",
      "group": "change",
      "summary": "Measure the baseline and hotspots; carry selected optimizations into build.",
      "outcome": "Reproducible report; remeasured optimization when authorized",
      "source": "skills/profile/SKILL.md",
      "paths": [
        {
          "id": "default",
          "label": "Measure and report",
          "stages": [
            "benchmark-before",
            "bottleneck",
            "profile-report",
            "build-transition"
          ]
        },
        {
          "id": "optimize",
          "label": "Optimize when authorized",
          "stages": [
            "benchmark-before",
            "bottleneck",
            "profile-report",
            "build-transition",
            "shared-preserving-build",
            "benchmark-after",
            "gain"
          ]
        }
      ]
    },
    {
      "name": "plan",
      "title": "Plan",
      "group": "understand",
      "summary": "Choose one plan or multiple ideas; planners direct research and the orchestrator compares results.",
      "outcome": "Reviewed Markdown plan; HTML when requested",
      "source": "skills/plan/SKILL.md",
      "paths": [
        {
          "id": "offline",
          "label": "Plan and report",
          "stages": [
            "scope",
            "$planning",
            "folio",
            "build-transition"
          ]
        },
        {
          "id": "reconcile",
          "label": "Plan with optional tracking",
          "stages": [
            "scope",
            "$planning",
            "folio",
            "approve-plan",
            "reconcile",
            "build-transition"
          ]
        }
      ]
    },
    {
      "name": "review",
      "title": "Review",
      "group": "change",
      "summary": "Independently verified diff findings or a scoped codebase audit.",
      "outcome": "Verified report; build only when authorized",
      "source": "skills/review/SKILL.md",
      "paths": [
        {
          "id": "diff",
          "label": "Diff / PR report",
          "stages": [
            "review-scope",
            "hunt",
            "refute",
            "dedupe-findings",
            "review-report",
            "build-transition"
          ]
        },
        {
          "id": "audit",
          "label": "Codebase audit",
          "stages": [
            "review-scope",
            "analysis-baseline",
            "hunt",
            "refute",
            "dedupe-findings",
            "review-report",
            "build-transition"
          ]
        },
        {
          "id": "fix",
          "label": "Review and fix requested",
          "stages": [
            "review-scope",
            "hunt",
            "refute",
            "dedupe-findings",
            "review-report",
            "build-transition",
            "shared-build"
          ]
        },
        {
          "id": "track",
          "label": "Track approved findings",
          "stages": [
            "hunt",
            "refute",
            "review-report",
            "approve-findings",
            "track-findings"
          ]
        }
      ]
    },
    {
      "name": "repo-setup",
      "title": "Repository setup",
      "group": "operate",
      "summary": "Discover the repository and establish agreed guidance, tooling, and working verification.",
      "outcome": "Configured repository and real verification evidence",
      "source": "skills/repo-setup/SKILL.md",
      "paths": [
        {
          "id": "default",
          "label": "Prepare the repository",
          "stages": [
            "repo-survey",
            "interview",
            "repo-vcs",
            "repo-instructions",
            "repo-tools",
            "repo-config",
            "repo-verify",
            "repo-report"
          ]
        }
      ]
    },
    {
      "name": "docs",
      "title": "Documentation",
      "group": "change",
      "summary": "Audit documentation truth, update assigned areas, and run the documentation gate.",
      "outcome": "Updated and checked documentation",
      "source": "skills/docs/SKILL.md",
      "paths": [
        {
          "id": "default",
          "label": "Documentation pass",
          "stages": [
            "docs-inventory",
            "docs-update",
            "docs-check",
            "docs-accept"
          ]
        }
      ]
    },
    {
      "name": "deploy",
      "title": "Deploy / release",
      "group": "operate",
      "summary": "Prepare a release, then deploy an explicitly approved target and commit.",
      "outcome": "Verified deployment or reported rollback",
      "source": "skills/deploy/SKILL.md",
      "paths": [
        {
          "id": "default",
          "label": "Release and deploy",
          "stages": [
            "release-notes",
            "release-ci",
            "release",
            "deploy-approval",
            "preflight",
            "deploy",
            "post-deploy",
            "release-handoff"
          ]
        }
      ]
    },
    {
      "name": "wiki",
      "title": "Project wiki",
      "group": "operate",
      "summary": "Consolidate completed-run evidence into an opted-in namespace outside the repository.",
      "outcome": "Checked traces, patterns, and catalog",
      "source": "skills/wiki/SKILL.md",
      "paths": [
        {
          "id": "default",
          "label": "Opt-in consolidation",
          "stages": [
            "wiki-opt-in",
            "wiki-consolidate",
            "wiki-check"
          ]
        }
      ]
    },
    {
      "name": "jj",
      "title": "Jujutsu",
      "group": "auxiliary",
      "summary": "Operate on selected Jujutsu repositories with explicit, verifiable VCS commands.",
      "outcome": "Verified repository state",
      "source": "skills/jj/SKILL.md",
      "paths": [
        {
          "id": "default",
          "label": "VCS operation",
          "stages": [
            "jj-inspect",
            "jj-mutate",
            "jj-verify"
          ]
        }
      ]
    },
    {
      "name": "use-other-harness",
      "title": "Another harness",
      "group": "auxiliary",
      "summary": "Run one bounded headless task in the harness, model, and effort explicitly named by the user.",
      "outcome": "Captured leaf-task result and handoff",
      "source": "skills/use-other-harness/SKILL.md",
      "paths": [
        {
          "id": "default",
          "label": "Explicit cross-harness task",
          "stages": [
            "foreign-request",
            "foreign-run",
            "foreign-result"
          ]
        }
      ]
    }
  ]
};
