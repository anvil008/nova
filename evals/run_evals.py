"""Structural, routing, and on-demand behavioral evals for Workcell instructions."""

from __future__ import annotations

import argparse
import ast
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

REPO_ROOT = Path(__file__).resolve().parents[1]
VALID_CASE_KINDS = {"skill", "agent"}
VALID_EVAL_KINDS = {"execution", "dialogue"}
TOKEN_RE = re.compile(r"[a-z0-9]+")
ERROR_SIMILARITY = 0.75
WARNING_SIMILARITY = 0.50
EXECUTOR_TIMEOUT = 900
GRADER_TIMEOUT = 180


@dataclass(frozen=True)
class Document:
    doc_id: str
    name: str
    kind: str
    description: str


@dataclass(frozen=True)
class Case:
    path: Path
    data: dict[str, Any]

    @property
    def doc_id(self) -> str:
        return f"{self.data.get('kind')}:{self.data.get('name')}"


def _frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError("missing frontmatter")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError("unterminated frontmatter")
    fields: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if not line or line[0].isspace() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if value[:1] in {'"', "'"}:
            try:
                parsed = ast.literal_eval(value)
            except (SyntaxError, ValueError) as error:
                raise ValueError(f"invalid quoted {key}") from error
            value = parsed if isinstance(parsed, str) else value
        fields[key.strip()] = value
    return fields


def _expand_agent_description(
    description: str, variables: dict[str, Any], harness: str = "codex"
) -> str:
    def replace(match: re.Match[str]) -> str:
        value = variables.get(match.group(1), match.group(0))
        if isinstance(value, dict):
            return str(value.get(harness, match.group(0)))
        return str(value)

    return re.sub(r"{{([A-Za-z][A-Za-z0-9]*)}}", replace, description)


def load_documents(root: Path) -> tuple[dict[str, Document], list[str]]:
    documents: dict[str, Document] = {}
    errors: list[str] = []
    skills_dir = root / "skills"
    if not skills_dir.is_dir():
        errors.append(f"{skills_dir}: missing skills directory")
    else:
        for directory in sorted(path for path in skills_dir.iterdir() if path.is_dir()):
            skill_file = directory / "SKILL.md"
            if not skill_file.is_file():
                continue
            try:
                fields = _frontmatter(skill_file)
            except (OSError, ValueError) as error:
                errors.append(f"{skill_file}: {error}")
                continue
            name = fields.get("name", "")
            description = fields.get("description", "")
            if name != directory.name:
                errors.append(
                    f"{skill_file}: frontmatter name {name!r} does not equal directory "
                    f"{directory.name!r}"
                )
            if not description:
                errors.append(f"{skill_file}: description is empty")
            elif len(description) > 1024:
                errors.append(f"{skill_file}: description exceeds 1024 characters")
            if name:
                doc_id = f"skill:{name}"
                documents[doc_id] = Document(doc_id, name, "skill", description)

    agents_path = root / "agents" / "agents.json"
    try:
        agents_data = json.loads(agents_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"{agents_path}: {error}")
        return documents, errors
    agents = agents_data.get("agents")
    if not isinstance(agents, dict):
        errors.append(f"{agents_path}: `agents` must be an object")
        return documents, errors
    variables = agents_data.get("vars", {})
    for name, config in sorted(agents.items()):
        description = config.get("description") if isinstance(config, dict) else None
        if not isinstance(description, str) or not description.strip():
            errors.append(f"{agents_path}: agent {name!r} has an empty description")
            continue
        description = _expand_agent_description(description, variables)
        if len(description) > 1024:
            errors.append(
                f"{agents_path}: agent {name!r} description exceeds 1024 characters"
            )
        doc_id = f"agent:{name}"
        documents[doc_id] = Document(doc_id, name, "agent", description)
    return documents, errors


def load_cases(root: Path) -> tuple[dict[str, Case], list[str]]:
    cases: dict[str, Case] = {}
    errors: list[str] = []
    cases_root = root / "evals" / "cases"
    for kind in sorted(VALID_CASE_KINDS):
        directory = cases_root / f"{kind}s"
        if not directory.is_dir():
            errors.append(f"{directory}: missing case directory")
            continue
        for path in sorted(directory.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                errors.append(f"{path}: {error}")
                continue
            if not isinstance(data, dict):
                errors.append(f"{path}: case must be a JSON object")
                continue
            case = Case(path, data)
            if case.doc_id in cases:
                errors.append(f"{path}: duplicate case for {case.doc_id}")
            else:
                cases[case.doc_id] = case
    return cases, errors


def _nonempty_prompt(entry: Any) -> bool:
    return (
        isinstance(entry, dict)
        and isinstance(entry.get("prompt"), str)
        and bool(entry["prompt"].strip())
    )


def structural_errors(
    root: Path,
) -> tuple[list[str], dict[str, Document], dict[str, Case]]:
    documents, errors = load_documents(root)
    cases, case_errors = load_cases(root)
    errors.extend(case_errors)
    missing = sorted(set(documents) - set(cases))
    extra = sorted(set(cases) - set(documents))
    errors.extend(f"missing case file for {doc_id}" for doc_id in missing)
    errors.extend(f"case has no matching description: {doc_id}" for doc_id in extra)

    fixtures = (root / "evals" / "fixtures").resolve()
    for doc_id, case in sorted(cases.items()):
        data = case.data
        label = str(case.path)
        if data.get("name") != case.path.stem:
            errors.append(f"{label}: name must equal filename stem")
        if data.get("kind") not in VALID_CASE_KINDS:
            errors.append(f"{label}: kind must be skill or agent")
        if doc_id not in documents:
            continue
        trigger = data.get("trigger")
        if not isinstance(trigger, dict):
            errors.append(f"{label}: trigger must be an object")
            continue
        positives = trigger.get("positive")
        negatives = trigger.get("negative")
        if not isinstance(positives, list) or len(positives) < 3:
            errors.append(f"{label}: requires at least 3 positive prompts")
        else:
            for index, entry in enumerate(positives, 1):
                if not _nonempty_prompt(entry):
                    errors.append(f"{label}: positive {index} needs a prompt")
                    continue
                top_k = entry.get("top_k")
                if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
                    errors.append(f"{label}: positive {index} needs top_k >= 1")
        if not isinstance(negatives, list) or len(negatives) < 2:
            errors.append(f"{label}: requires at least 2 negative prompts")
        else:
            for index, entry in enumerate(negatives, 1):
                if not _nonempty_prompt(entry):
                    errors.append(f"{label}: negative {index} needs a prompt")
                if not isinstance(entry, dict) or not isinstance(
                    entry.get("owner"), str
                ):
                    errors.append(f"{label}: negative {index} needs an owner")
        evals = data.get("evals")
        if not isinstance(evals, list) or not evals:
            errors.append(f"{label}: requires at least 1 behavioral eval")
            continue
        seen_ids: set[int] = set()
        for index, evaluation in enumerate(evals, 1):
            if not isinstance(evaluation, dict):
                errors.append(f"{label}: eval {index} must be an object")
                continue
            eval_id = evaluation.get("id")
            if not isinstance(eval_id, int) or isinstance(eval_id, bool) or eval_id < 1:
                errors.append(f"{label}: eval {index} needs a positive integer id")
            elif eval_id in seen_ids:
                errors.append(f"{label}: duplicate eval id {eval_id}")
            else:
                seen_ids.add(eval_id)
            eval_kind = evaluation.get("kind")
            if eval_kind not in VALID_EVAL_KINDS:
                errors.append(
                    f"{label}: eval {index} kind must be execution or dialogue"
                )
            for field in ("prompt", "expected_output"):
                if (
                    not isinstance(evaluation.get(field), str)
                    or not evaluation[field].strip()
                ):
                    errors.append(f"{label}: eval {index} needs {field}")
            expectations = evaluation.get("expectations")
            if (
                not isinstance(expectations, list)
                or not expectations
                or not all(
                    isinstance(item, str) and item.strip() for item in expectations
                )
            ):
                errors.append(f"{label}: eval {index} needs non-empty expectations")
            if eval_kind == "execution":
                files = evaluation.get("files")
                if not isinstance(files, list) or not files:
                    errors.append(f"{label}: execution eval {index} needs files[]")
                    continue
                for fixture in files:
                    if not isinstance(fixture, str) or not fixture:
                        errors.append(
                            f"{label}: eval {index} has an invalid fixture path"
                        )
                        continue
                    candidate = (fixtures / fixture).resolve()
                    if fixtures not in candidate.parents or not candidate.exists():
                        errors.append(
                            f"{label}: eval {index} fixture {fixture!r} does not exist "
                            "under evals/fixtures"
                        )
    return errors, documents, cases


def _stem(token: str) -> str:
    if token.endswith("ies") and len(token) > 5:
        return f"{token[:-3]}y"
    for suffix in (
        "izations",
        "ization",
        "ational",
        "fulness",
        "ousness",
        "iveness",
        "ments",
        "ations",
        "ingly",
        "edly",
        "ation",
        "ment",
        "ness",
        "ers",
        "ing",
        "ed",
        "ly",
        "es",
        "s",
    ):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


def tokenize(text: str) -> list[str]:
    return [_stem(token) for token in TOKEN_RE.findall(text.lower())]


class TfidfIndex:
    def __init__(self, documents: dict[str, Document]):
        self.documents = documents
        tokens = {
            doc_id: tokenize(doc.description) for doc_id, doc in documents.items()
        }
        document_frequency: Counter[str] = Counter()
        for values in tokens.values():
            document_frequency.update(set(values))
        count = len(tokens)
        self.idf = {
            token: math.log((count + 1) / (frequency + 1)) + 1
            for token, frequency in document_frequency.items()
        }
        self.vectors = {
            doc_id: self._vector(values) for doc_id, values in tokens.items()
        }

    def _vector(self, tokens: list[str]) -> dict[str, float]:
        counts = Counter(token for token in tokens if token in self.idf)
        return {token: count * self.idf[token] for token, count in counts.items()}

    @staticmethod
    def cosine(left: dict[str, float], right: dict[str, float]) -> float:
        left_norm = math.sqrt(sum(value * value for value in left.values()))
        right_norm = math.sqrt(sum(value * value for value in right.values()))
        if not left_norm or not right_norm:
            return 0.0
        overlap = set(left) & set(right)
        return sum(left[token] * right[token] for token in overlap) / (
            left_norm * right_norm
        )

    def scores(self, prompt: str) -> list[tuple[str, float]]:
        query = self._vector(tokenize(prompt))
        return sorted(
            (
                (doc_id, self.cosine(query, vector))
                for doc_id, vector in self.vectors.items()
            ),
            key=lambda item: (-item[1], item[0]),
        )


def _resolve_owner(owner: str, documents: dict[str, Document]) -> str | None:
    if owner in documents:
        return owner
    matches = [
        doc_id for doc_id, document in documents.items() if document.name == owner
    ]
    return matches[0] if len(matches) == 1 else None


def _print_prompt_table(
    rows: list[tuple[str, str, str, str, float, bool]], out: TextIO
) -> None:
    print("case | type | target | winner | winner-score | pass", file=out)
    print("--- | --- | --- | --- | ---: | ---", file=out)
    for case_id, polarity, target, winner, score, passed in rows:
        print(
            f"{case_id} | {polarity} | {target} | {winner} | {score:.3f} | "
            f"{'yes' if passed else 'no'}",
            file=out,
        )


def evaluate_routing(
    documents: dict[str, Document],
    cases: dict[str, Case],
    min_rank1: float,
    out: TextIO,
) -> int:
    index = TfidfIndex(documents)
    failed = False
    rows: list[tuple[str, str, str, str, float, bool]] = []
    doc_ids = sorted(documents)
    for left_index, left_id in enumerate(doc_ids):
        for right_id in doc_ids[left_index + 1 :]:
            similarity = index.cosine(index.vectors[left_id], index.vectors[right_id])
            if similarity >= ERROR_SIMILARITY:
                print(
                    f"ERROR collision {left_id} / {right_id}: {similarity:.1%}",
                    file=out,
                )
                failed = True
            elif similarity >= WARNING_SIMILARITY:
                print(
                    f"WARNING collision {left_id} / {right_id}: {similarity:.1%}",
                    file=out,
                )

    rank1 = 0
    positive_count = 0
    for case_id, case in sorted(cases.items()):
        trigger = case.data["trigger"]
        for entry in trigger["positive"]:
            scores = index.scores(entry["prompt"])
            ranking = [doc_id for doc_id, _ in scores]
            winner, winner_score = scores[0]
            rank = ranking.index(case_id) + 1
            passed = rank <= entry["top_k"]
            positive_count += 1
            rank1 += rank == 1
            failed = failed or not passed
            rows.append(
                (
                    case_id,
                    "positive",
                    f"rank {rank} <= {entry['top_k']}",
                    winner,
                    winner_score,
                    passed,
                )
            )
        for entry in trigger["negative"]:
            owner = _resolve_owner(entry["owner"], documents)
            scores = index.scores(entry["prompt"])
            score_map = dict(scores)
            winner, winner_score = scores[0]
            passed = owner is not None and score_map[owner] > score_map[case_id]
            failed = failed or not passed
            target = f"{owner or entry['owner']} > {case_id}"
            rows.append((case_id, "negative", target, winner, winner_score, passed))

    rate = 100.0 * rank1 / positive_count if positive_count else 0.0
    print(f"Rank-1 rate: {rank1}/{positive_count} ({rate:.1f}%)", file=out)
    if rate + 1e-9 < min_rank1:
        print(f"ERROR rank-1 rate is below the {min_rank1:.1f}% floor", file=out)
        failed = True
    if failed:
        _print_prompt_table(rows, out)
    return 1 if failed else 0


def _command_text(command: list[str]) -> str:
    import shlex

    return shlex.join(command)


def _grader_prompt(case: Case, evaluation: dict[str, Any]) -> str:
    contract = {
        "expectations": [
            {"text": text, "pass": True, "evidence": "trace evidence"}
            for text in evaluation["expectations"]
        ],
        "pass": True,
    }
    return (
        "Grade the executor trace against every expectation. Judge behavior, not exact "
        "phrasing. Return only JSON with exactly this shape: "
        f"{json.dumps(contract)}. The expected artifact is: "
        f"{evaluation['expected_output']}"
    )


def _behavioral_commands(
    case: Case,
    evaluation: dict[str, Any],
    harness: str,
    workspace: str,
    trace_path: str,
) -> tuple[list[str], list[str]]:
    if harness == "claude":
        executor = [
            "claude",
            "-p",
            evaluation["prompt"],
            "--output-format",
            "stream-json",
            "--verbose",
            "--permission-mode",
            "acceptEdits",
        ]
    else:
        executor = [
            "codex",
            "exec",
            "--cd",
            workspace,
            "-o",
            trace_path,
            evaluation["prompt"],
        ]
    grader = ["claude", "-p", _grader_prompt(case, evaluation)]
    return executor, grader


def validate_grader_output(
    raw: str, expected: list[str]
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        return None, f"grader output is not JSON: {error}"
    if not isinstance(data, dict) or set(data) != {"expectations", "pass"}:
        return None, "grader output must contain exactly expectations[] and pass"
    if not isinstance(data["pass"], bool) or not isinstance(data["expectations"], list):
        return None, "grader pass must be boolean and expectations must be a list"
    if len(data["expectations"]) != len(expected):
        return None, "grader must return one result for every expectation"
    for index, (item, text) in enumerate(
        zip(data["expectations"], expected, strict=True), 1
    ):
        if not isinstance(item, dict) or set(item) != {"text", "pass", "evidence"}:
            return None, f"grader expectation {index} has the wrong shape"
        if item["text"] != text:
            return None, f"grader expectation {index} does not match the requested text"
        if not isinstance(item["pass"], bool) or not isinstance(item["evidence"], str):
            return None, f"grader expectation {index} has invalid field types"
    if data["pass"] != all(item["pass"] for item in data["expectations"]):
        return None, "grader top-level pass disagrees with expectation results"
    return data, None


def _run_checked(
    command: list[str],
    *,
    cwd: Path,
    timeout: int,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def run_behavioral_eval(
    root: Path,
    case: Case,
    evaluation: dict[str, Any],
    harness: str,
    out: TextIO,
) -> int:
    results_dir = root / "evals" / "results"
    with tempfile.TemporaryDirectory(prefix="workcell-eval-") as temp:
        workspace = Path(temp)
        for fixture in evaluation.get("files", []):
            source = root / "evals" / "fixtures" / fixture
            if source.is_dir():
                shutil.copytree(source, workspace, dirs_exist_ok=True)
            else:
                shutil.copy2(source, workspace / source.name)
        git_commands = [
            ["git", "init"],
            ["git", "add", "--all"],
            [
                "git",
                "-c",
                "user.name=Workcell Eval",
                "-c",
                "user.email=evals@workcell.invalid",
                "commit",
                "--allow-empty",
                "-m",
                "baseline",
            ],
        ]
        for command in git_commands:
            result = _run_checked(command, cwd=workspace, timeout=30)
            if result.returncode:
                print(
                    f"ERROR baseline command failed: {_command_text(command)}", file=out
                )
                return 1
        trace_path = workspace / ".workcell-eval-trace.txt"
        executor, grader = _behavioral_commands(
            case, evaluation, harness, str(workspace), str(trace_path)
        )
        try:
            executor_result = _run_checked(
                executor, cwd=workspace, timeout=EXECUTOR_TIMEOUT
            )
        except subprocess.TimeoutExpired:
            print(f"ERROR executor timed out after {EXECUTOR_TIMEOUT}s", file=out)
            return 1
        if executor_result.returncode:
            print(f"ERROR executor exited {executor_result.returncode}", file=out)
            return 1
        if harness == "codex" and trace_path.exists():
            trace = trace_path.read_text(encoding="utf-8")
        else:
            trace = executor_result.stdout
        try:
            grader_result = _run_checked(
                grader, cwd=workspace, timeout=GRADER_TIMEOUT, input_text=trace
            )
        except subprocess.TimeoutExpired:
            print(f"ERROR grader timed out after {GRADER_TIMEOUT}s", file=out)
            return 1
        if grader_result.returncode:
            print(f"ERROR grader exited {grader_result.returncode}", file=out)
            return 1
        grade, error = validate_grader_output(
            grader_result.stdout, evaluation["expectations"]
        )
        if error:
            print(f"ERROR {error}", file=out)
            return 1
        record = {
            "case": case.data["name"],
            "kind": case.data["kind"],
            "id": evaluation["id"],
            "harness": harness,
            "executor": executor,
            "grader": grader,
            "grade": grade,
        }
        results_dir.mkdir(parents=True, exist_ok=True)
        result_path = results_dir / f"{case.data['name']}-{evaluation['id']}.json"
        result_path.write_text(f"{json.dumps(record, indent=2)}\n", encoding="utf-8")
        print(f"Wrote {result_path}", file=out)
        return 0 if grade["pass"] else 1


def _select_behavioral_case(selector: str, cases: dict[str, Case]) -> Case | None:
    normalized = selector.replace("/", ":", 1)
    if normalized in cases:
        return cases[normalized]
    matches = [case for case in cases.values() if case.data.get("name") == selector]
    return matches[0] if len(matches) == 1 else None


def run_behavioral(
    root: Path,
    cases: dict[str, Case],
    selector: str,
    harness: str,
    dry_run: bool,
    out: TextIO,
) -> int:
    case = _select_behavioral_case(selector, cases)
    if case is None:
        print(
            f"ERROR behavioral case {selector!r} is missing or ambiguous; "
            "use skill:<name> or agent:<name>",
            file=out,
        )
        return 1
    if dry_run:
        for evaluation in case.data["evals"]:
            trace = "<workspace>/.workcell-eval-trace.txt"
            executor, grader = _behavioral_commands(
                case, evaluation, harness, "<workspace>", trace
            )
            print(f"executor: {_command_text(executor)}", file=out)
            print(f"grader:   {_command_text(grader)} < {trace}", file=out)
        return 0
    status = 0
    for evaluation in case.data["evals"]:
        status |= run_behavioral_eval(root, case, evaluation, harness, out)
    return status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--structural", action="store_true", help="run structural checks only"
    )
    parser.add_argument("--min-rank1", type=float, default=0.0, metavar="PCT")
    parser.add_argument("--behavioral", metavar="CASE")
    parser.add_argument("--harness", choices=("claude", "codex"), default="claude")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None, out: TextIO = sys.stdout) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    errors, documents, cases = structural_errors(root)
    if errors:
        for error in errors:
            print(f"ERROR {error}", file=out)
        return 1
    if args.structural:
        print(
            f"Structural evals passed: {len(documents)} descriptions, {len(cases)} cases",
            file=out,
        )
        return 0
    if args.behavioral:
        return run_behavioral(
            root, cases, args.behavioral, args.harness, args.dry_run, out
        )
    if args.dry_run:
        print("ERROR --dry-run requires --behavioral", file=out)
        return 1
    if not 0 <= args.min_rank1 <= 100:
        print("ERROR --min-rank1 must be between 0 and 100", file=out)
        return 1
    return evaluate_routing(documents, cases, args.min_rank1, out)


if __name__ == "__main__":
    raise SystemExit(main())
