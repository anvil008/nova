# Workcell instruction evals

These evals test whether skills and agents are complete, discoverable from realistic
requests, and behaviorally faithful to their contracts. For the other kind — harness evals, where
Workcell runs unattended against an external benchmark task and is scored on the patch it
produces — see [docs/eval-runs.md](../docs/eval-runs.md).

They use three tiers:

1. **Structural** is free and runs in CI. It checks skill frontmatter, full case coverage,
   trigger counts, behavioral entries, and fixture paths.
2. **Routing** is free and runs in CI. It uses lowercase tokenization, deterministic
   suffix stemming, and TF-IDF cosine ranking over skill and agent descriptions. Positive
   prompts must retrieve their case, negatives must prefer their declared owner, and
   description collisions warn at 50% and fail at 75%. The checked-in corpus ranks first
   for 67 of 81 positive prompts (82.7%); CI allows normal wording movement down to 77%.
3. **Behavioral** is on demand and spends executor/grader tokens. It initializes a temporary
   git repository from the requested fixtures, runs Claude Code or Codex headlessly, then
   sends the trace to a Claude grader. The validated grade is written under `results/`.

Run the free tiers and unit tests from the repository root:

```sh
python3 evals/run_evals.py --structural
python3 evals/run_evals.py --min-rank1 77
python3 -m unittest discover -s evals/tests -p 'test_*.py'
```

Preview a behavioral invocation without creating a repository, spawning a process, or
writing a result:

```sh
python3 evals/run_evals.py --behavioral build --dry-run
python3 evals/run_evals.py --behavioral agent:builder --harness codex --dry-run
```

Without `--dry-run`, the executor and grader have bounded timeouts. The grader must return
exactly `{"expectations":[{"text":"…","pass":true,"evidence":"…"}],"pass":true}`,
with one result matching every expectation. Invalid JSON or an invalid shape fails without
writing a result.

## Adding a case

Add one JSON file beneath `cases/skills/` or `cases/agents/`; its filename, `name`, and the
corresponding skill directory or agent key must agree. Include at least three natural,
paraphrased positive prompts, two negative prompts naming the case that should win, and one
`execution` or `dialogue` eval. Execution evals must list one or more paths beneath
`fixtures/`. Expectations describe observable decisions or file behavior, never required
phrasing. Run both free tiers and the unit tests before submitting the case.
