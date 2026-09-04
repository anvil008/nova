"""Acceptance tests for GitHub Actions CI Go build and Python pip caching (Issue #215)."""

from __future__ import annotations

from pathlib import Path
import unittest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def load_ci_workflow() -> dict:
    """Load and parse .github/workflows/ci.yml into a dictionary."""
    if not CI_WORKFLOW_PATH.is_file():
        raise FileNotFoundError(f"Missing CI workflow file at {CI_WORKFLOW_PATH}")
    with open(CI_WORKFLOW_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML dictionary in {CI_WORKFLOW_PATH}, got {type(data)}")
    return data


class TestCICaching(unittest.TestCase):
    """Verifies dependency caching and trigger scoping in .github/workflows/ci.yml."""

    def test_ci_workflow_has_go_build_cache(self) -> None:
        """Verify .github/workflows/ci.yml contains caching configuration for ~/.cache/go-build."""
        workflow = load_ci_workflow()
        jobs = workflow.get("jobs", {})
        self.assertIsInstance(jobs, dict, "Expected 'jobs' section in CI workflow")

        found_go_build_cache = False
        for job_name, job in jobs.items():
            if not isinstance(job, dict):
                continue
            steps = job.get("steps", [])
            for step in steps:
                if not isinstance(step, dict):
                    continue
                uses = step.get("uses", "")
                if isinstance(uses, str) and uses.startswith("actions/cache"):
                    with_cfg = step.get("with", {})
                    if isinstance(with_cfg, dict):
                        path = with_cfg.get("path", "")
                        if isinstance(path, list):
                            if any("~/.cache/go-build" in str(p) for p in path):
                                found_go_build_cache = True
                                break
                        elif isinstance(path, str):
                            if "~/.cache/go-build" in path:
                                found_go_build_cache = True
                                break
            if found_go_build_cache:
                break

        self.assertTrue(
            found_go_build_cache,
            "Expected .github/workflows/ci.yml to contain an actions/cache step configured for ~/.cache/go-build",
        )

    def test_ci_workflow_has_python_pip_cache(self) -> None:
        """Verify .github/workflows/ci.yml configures pip caching on Python setup or actions/cache for pip dependencies."""
        workflow = load_ci_workflow()
        jobs = workflow.get("jobs", {})
        self.assertIsInstance(jobs, dict, "Expected 'jobs' section in CI workflow")

        found_pip_cache = False
        for job_name, job in jobs.items():
            if not isinstance(job, dict):
                continue
            steps = job.get("steps", [])
            for step in steps:
                if not isinstance(step, dict):
                    continue
                uses = step.get("uses", "")
                with_cfg = step.get("with", {}) if isinstance(step.get("with"), dict) else {}
                if isinstance(uses, str):
                    # Check setup-python cache: 'pip'
                    if uses.startswith("actions/setup-python"):
                        cache_val = with_cfg.get("cache")
                        if cache_val == "pip" or (isinstance(cache_val, str) and "pip" in cache_val):
                            found_pip_cache = True
                            break
                    # Check actions/cache for pip dependencies
                    if uses.startswith("actions/cache"):
                        path = with_cfg.get("path", "")
                        key = with_cfg.get("key", "")
                        path_str = " ".join(str(p) for p in path) if isinstance(path, list) else str(path)
                        if "pip" in path_str.lower() or "pip" in str(key).lower():
                            found_pip_cache = True
                            break
            if found_pip_cache:
                break

        self.assertTrue(
            found_pip_cache,
            "Expected .github/workflows/ci.yml to configure pip caching via actions/setup-python (cache: 'pip') or actions/cache for pip dependencies",
        )

    def test_ci_triggers_restricted_to_main(self) -> None:
        """Verify .github/workflows/ci.yml scopes push and pull_request events to the main branch."""
        workflow = load_ci_workflow()
        # In PyYAML, unquoted 'on:' key parses as boolean True
        triggers = workflow.get("on") or workflow.get(True)
        self.assertIsInstance(
            triggers,
            dict,
            "Workflow 'on' trigger configuration must be a dictionary",
        )

        # push trigger must specify branches: [main]
        push_cfg = triggers.get("push")
        self.assertIsInstance(
            push_cfg,
            dict,
            "Workflow 'push' trigger must be configured with a dictionary",
        )
        push_branches = push_cfg.get("branches")
        self.assertIsInstance(
            push_branches,
            list,
            "Workflow 'push' trigger must specify a list of branches",
        )
        self.assertEqual(
            push_branches,
            ["main"],
            f"Expected push branches to be ['main'], got {push_branches}",
        )

        # pull_request trigger must specify branches: [main]
        pr_cfg = triggers.get("pull_request")
        self.assertIsInstance(
            pr_cfg,
            dict,
            "Workflow 'pull_request' trigger must be configured with a dictionary (not bare)",
        )
        pr_branches = pr_cfg.get("branches")
        self.assertIsInstance(
            pr_branches,
            list,
            "Workflow 'pull_request' trigger must specify a list of branches",
        )
        self.assertEqual(
            pr_branches,
            ["main"],
            f"Expected pull_request branches to be ['main'], got {pr_branches}",
        )


if __name__ == "__main__":
    unittest.main()
