# Docs 01 — README and diagram refresh against current source

Date: 2026-09-14. Scope: `README.md` and the three hand-authored SVG diagrams under `docs/diagrams/`. Source state at audit: local `main` at `5f09da4`, working copy on bookmark `docs/readme-diagram-refresh`. No product code, tests, instructions, or ADRs were changed.

## Changed pages

| File | Change |
|---|---|
| [README.md](../../README.md) | Four prose/alt-text corrections in "How Nova works" and "Hooks: what runs when?" |
| [docs/diagrams/nova-hooks.svg](../diagrams/nova-hooks.svg) | `integration.py` and `write-routing.py` effect cards, plus `<desc>` |
| [docs/diagrams/nova-workflow.svg](../diagrams/nova-workflow.svg) | Step 4 caption, box height, canvas height, `<desc>` |
| [docs/diagrams/nova-skills.svg](../diagrams/nova-skills.svg) | Verified only; no change needed |

## Reader benefit

The README is the first page a prospective user reads, and its three diagrams are the only visual explanation of what Nova installs. Since the README was last touched at `faec8cd`, four behavior changes landed that the page described incorrectly. A reader who ran a scout or reviewer and saw no integration reminder, or who ran a non-write tool under Antigravity and saw it pass through, would have concluded the documentation was wrong about the hooks. The delivery-summary contract also changed: readers now receive a diagram, linked deliverables, evidence, and a commit, and the README promised only "the result and verification evidence". These edits make the page match what the software does, without restructuring it.

## Drifts and fixes

### 1. The integration reminder no longer arms for read-only children

Source: `hooks/integration.py` lines 24–43 (`READ_ONLY_AGENTS`, `read_only_agent`, and the `SubagentStop` branch), documented in `hooks/README.md` "Parent integration reminders". Introduced by `7a4f597` ("fix(hooks): skip integration reminder for read-only subagents"). The code comment is explicit that "unknown or missing types still arm".

README "After delegation" bullet, before:

> Each can issue one parent continuation reminder to verify results, integrate into local main, and finish authorized publication and cleanup. Agy waits for a normal, fully idle Stop.

After:

> Each can issue one parent continuation reminder to verify results, integrate into local main, and finish authorized publication and cleanup. Known read-only child types—scout, reviewer, Explore, Plan, and similar—do not arm the Codex/Claude reminder; unknown or missing types still do. Agy waits for a normal, fully idle Stop.

README hook-map alt text, before: "Codex/Claude child-stop and Agy delegation events arm a parent integration reminder". After: "Codex/Claude implementer and writer child stops and Agy delegation events arm a parent integration reminder, while known read-only children do not".

`nova-hooks.svg`, the `SubagentStop → parent Stop` / `integration.py` card, before:

```
Child stop sets a session marker.
Next eligible parent Stop blocks once
with an integration reminder.
It never merges code itself.
```

After:

```
Writer child stop sets a session marker.
Read-only helpers (scout, reviewer) skip it.
Next eligible parent Stop blocks once
with an integration reminder.
It never merges code itself.
```

The card's `rect` already had 170px of height (16px more than its siblings), so the fifth line at `y="480"` fits inside the existing box; no geometry changed. The `<desc>` sentence about `SubagentStop` was updated to match.

### 2. Delivery summaries now carry a diagram, deliverables, evidence, and a commit

Source: `instructions/development.md` line 10 and the verification paragraph in `instructions/global/AGENTS.md`, `instructions/global/CLAUDE.md`, and `instructions/global/GEMINI.md`, all line 21: "Summarize delivered changes with a visual workflow diagram, key deliverables with file links, verification evidence, and the immutable local main commit." Introduced by `241597f`.

README step 4, before:

> You receive the result and verification evidence. When authorized, the parent agent also integrates changes…

After:

> You receive the result and verification evidence. The delivery summary includes a workflow diagram, key deliverables with file links, verification evidence, and the immutable local `main` commit. When authorized, the parent agent also integrates changes…

`nova-workflow.svg` step 4 gained a second caption line, `Summary: diagram, deliverables, evidence, commit.` The teal step-4 box grew from 92px to 118px and the canvas from 800px to 826px so the footer line keeps its clearance; the layout grid, colors, and fonts are unchanged. The image alt text and `<desc>` were extended with the same facts.

### 3. The Agy write-routing hook returns an explicit allow

Source: `tools/write_routing.py` line 239 (`result = {'decision': 'allow'}`), added by `d0ef314` ("Return an explicit allow from the agy write-routing hook"). Antigravity treats an empty PreToolUse response as a missing decision, so the hook now emits an allow whenever it has nothing to deny.

README "Before a task-file edit" bullet, before: "recognized edits receive implementer-routing guidance. Claude can identify its implementer…". After: "recognized edits receive implementer-routing guidance, and unrecognized calls pass through unchanged (Agy receives an explicit allow). Claude can identify its implementer…".

`nova-hooks.svg` `write-routing.py` card, before:

```
Deny with implementer guidance.
Claude identifies its implementer; Codex
and Agy receive an argv runner path.
The hook never launches a worker.
```

After:

```
Deny with implementer guidance.
Claude identifies its implementer; Codex
and Agy receive an argv runner path.
Other calls pass through; Agy gets an
explicit allow. It never launches a worker.
```

The fifth line sits at `y="1356"`, inside the card's existing bottom edge at `y=1376`. The `<desc>` was extended accordingly.

### 4. si-project / si-global wording — verified accurate, unchanged

`skills/si-project/SKILL.md` line 11 places the store at `<primary-root>/.nova/si/`; `skills/si-global/SKILL.md` line 11 aggregates across repositories registered in `~/.nova/known_projects.json`, line 19 gates global skill changes behind Nova's CI checks, and line 25 skips eval-mode projects. The skills diagram card text, "In-repo store (.nova/si/) and cross-repo synthesis.", is an accurate compression of both, so it was left alone. The README table rows ("Project-scoped adaptation and self-improvement", "Cross-project pattern synthesis and skill evolution") match the `description` frontmatter of each SKILL.md and were left alone. `nova-skills.svg` is unchanged.

### 5. Sweep of the remaining README claims — no further drift found

Everything below was checked against source and found correct, so nothing was edited:

- Bootstrap flags. `scripts/bootstrap.py` lines 143–155 define `--harness`, `--dry-run`, `--prefix`, `--bin-dir`, `--with-codex-helpers`, `--replace-marketplace`, `--align-global`, `--no-align-global`, and `--force-global`. The README uses only `--dry-run`, `--no-align-global`, `--harness`, and `--with-codex-helpers`, all present.
- Contributing commands. `requirements-dev.txt`, `scripts/update-guide.py`, and `scripts/package.py` exist; `scripts/package.py` line 122 defaults its output to `dist/plugins`, and line 10 defines `HARNESSES = ('codex', 'claude', 'agy')`, matching the documented `dist/plugins/{codex,claude,agy}/`.
- nova-flow commands. `tools/nova-flow` registers `init` (line 1306, with a positional title and `--id`), `task add` with `--phase` (line 1310), `view` (line 1334), and `serve` (line 1341). The README example is valid.
- Directory table. All eight directories exist.
- Skill table. `skills/` contains exactly the fifteen skills the table lists; every `SKILL.md` link resolves.
- Every relative link and image path in the README resolves, including the two section anchors (`instructions/install.md#instruction-loading` → heading at line 84; `instructions/integration.md#parent-owned-task-integration` → heading at line 25).

## Validation

Working directory `/home/anvil/repos/nova`, run after the edits.

XML well-formedness of all three diagrams:

```
$ python3 -c "import xml.dom.minidom,sys; [xml.dom.minidom.parse(p) for p in sys.argv[1:]]" \
    docs/diagrams/nova-workflow.svg docs/diagrams/nova-skills.svg docs/diagrams/nova-hooks.svg
(no output; exit 0)
```

Guide check:

```
$ python3 scripts/update-guide.py --check
(no output; exit 0)
```

Test suite:

```
$ python3 -m unittest discover -s tests
Ran 157 tests in 32.695s

OK
```

157 passed, 0 failed, 0 errors. No product code or test was modified.

README link check (every relative link and image path):

```
$ python3 -c "
import re,os
t=open('README.md').read()
bad=0
for l in sorted(set(re.findall(r'\]\(([^)]+)\)',t))):
    if l.startswith('http') or l.startswith('#'): continue
    p=l.split('#')[0]; ok=os.path.exists(p); bad+= not ok
    print(('OK  ' if ok else 'MISS'), l)
print('missing:',bad)"
... 36 paths, all OK
missing: 0
```

Visual check. Headless Chromium rendered each SVG to PNG at its declared canvas size into `~/.cache/agent-work/nova/readme-diagrams/`:

```
$ chromium --headless --disable-gpu --no-sandbox --hide-scrollbars \
    --screenshot=<out>.png --window-size=<W>,<H> file://$PWD/docs/diagrams/<name>.svg
nova-workflow 900x826    nova-skills 960x1340    nova-hooks 1040x1714
```

The rendered step-4 card, `integration.py` card, and `write-routing.py` card were inspected at full resolution; all text sits inside its box with normal margins and the workflow footer keeps its clearance below the enlarged card.

An independent width audit measured every `<text>` run with Pillow against DejaVu Sans at the element's computed font size and compared it to the innermost containing `rect`:

```
docs/diagrams/nova-workflow.svg: 0 overflowing text runs
docs/diagrams/nova-skills.svg: 2 overflowing text runs
docs/diagrams/nova-hooks.svg: 1 overflowing text runs
```

All three reported runs are pre-existing lines that this change did not touch (`"This code is hard to work on."`, `In-repo store (.nova/si/) and cross-repo synthesis.`, and the bootstrap banner line in the hooks footer). They are measurement artifacts: DejaVu Sans is wider than the `-apple-system` / Segoe UI / Arial stack the diagrams actually specify, so the audit is an upper bound. The Chromium render shows all three inside their boxes. Every line added by this change measured below the widest pre-existing line in the same column.

## Limitations

- **ADR 0010 is stale and was deliberately not edited.** [docs/adr/0010-readme-diagrams-are-generated-svg.md](../adr/0010-readme-diagrams-are-generated-svg.md) describes a `render-diagrams.py` pipeline that generates the README SVGs from a source definition. That script no longer exists; the diagrams have been hand-authored SVG since #225. The ADR is outside this task's owned paths. Someone should supersede it with a new ADR recording the hand-authored decision, or amend its Status — editing the accepted text in place would erase the decision history.
- **No rendering toolchain was introduced.** The Chromium render and the Pillow width audit are one-off verification run from `~/.cache/agent-work/nova/readme-diagrams/`; neither is committed, wired into `tests/`, nor required to change a diagram. Future diagram edits get no automated overflow guard.
- **Font substitution.** The overflow audit and the Chromium render both use Linux font fallbacks, not the macOS `-apple-system` or Windows Segoe UI that the diagrams name first. Line widths on those platforms will differ slightly. The added lines have 20–30px of slack against the widest pre-existing line in their column, which should absorb the variance, but this was not verified on macOS or Windows.
- **Prose accuracy is source-verified, not behavior-verified.** Each corrected claim was checked against the hook and instruction sources cited above and against the existing test suite, which passes. No hook was executed against a live Codex, Claude, or Antigravity session as part of this documentation change.
- **Sweep scope.** Item 5 covered the README claims enumerated in the assignment (bootstrap flags, contributing commands, directory table, nova-flow commands, skill table, links). The README's narrative sections on read routing, workspace behavior, and the 0.6 upgrade note were read but not exhaustively cross-checked against every referenced instruction file; no contradiction was apparent, but absence of a found drift there is weaker evidence than for the enumerated items.
