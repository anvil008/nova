"use strict";

// Current workflows and legacy diagram routes; validated against the registry.
const workflowDesign = {
  "status": "implemented",
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
    }
  ],
  "workflows": [
    {
      "name": "build",
      "title": "Build",
      "group": "change",
      "summary": "Reuse the request, selected plan, or findings; orchestrator chooses team size and execution shape.",
      "outcome": "One verified final PR",
      "support": [
        "researcher"
      ],
      "source": "build",
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
      ]
    },
    {
      "name": "refactor",
      "title": "Refactor",
      "group": "change",
      "summary": "Assess structural simplifications and preserved contracts; implement selected refactors through build when authorized.",
      "outcome": "Refactor proposal; verified simplification when authorized",
      "support": [
        "researcher"
      ],
      "source": "refactor",
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
      ]
    },
    {
      "name": "debug",
      "title": "Debug",
      "group": "change",
      "summary": "Reproduce a reported failure and return a supported diagnosis; repair only when authorized.",
      "outcome": "Diagnosis report; verified repair when requested",
      "source": "debug",
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
      "source": "profile",
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
      "source": "plan",
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
      "source": "review",
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
      "source": "repo-setup",
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
      "source": "docs",
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
      "source": "deploy",
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
      "source": "wiki",
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
    }
  ],
  "auxiliaries": [
    {
      "name": "jj",
      "title": "Jujutsu",
      "group": "auxiliary",
      "summary": "Operate on selected Jujutsu repositories with explicit, verifiable VCS commands.",
      "outcome": "Verified repository state",
      "source": "jj",
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
      "source": "use-other-harness",
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
  ],
  "aliases": {
    "new-feature": {
      "workflow": "build",
      "path": "coordinated"
    },
    "simple-build": {
      "workflow": "build",
      "path": "bounded"
    },
    "complex-build": {
      "workflow": "build",
      "path": "coordinated"
    },
    "code-refactor": {
      "workflow": "refactor",
      "path": "broad"
    },
    "code-review": {
      "workflow": "review",
      "path": "diff"
    },
    "code-analysis": {
      "workflow": "review",
      "path": "audit"
    },
    "review-fix-loop": {
      "workflow": "review",
      "path": "fix"
    },
    "perf": {
      "workflow": "profile",
      "path": "default"
    }
  },
  "stages": {}
};
