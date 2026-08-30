package guard

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/anvil008/workcell/controlplane"
)

// seal records either a RED baseline for a behaviour change or a GREEN
// baseline for a refactor. Exactly one command kind is required.
func seal(loaded *state, patterns []string, redCommand, baselineCommand []string) error {
	if len(redCommand) > 0 && len(baselineCommand) > 0 {
		return fmt.Errorf("seal accepts exactly one of --red-command or --green-baseline")
	}
	kind, command := SealKindRed, redCommand
	if len(baselineCommand) > 0 {
		kind, command = SealKindBaseline, baselineCommand
	}
	if len(command) == 0 {
		return fmt.Errorf("seal requires exactly one of --red-command <argv...> or --green-baseline <argv...>")
	}
	if len(patterns) == 0 {
		resolved, err := configuredPatterns(loaded.repository)
		if err != nil {
			return err
		}
		patterns = resolved
	}
	tests, err := collectTests(loaded.repository, patterns)
	if err != nil {
		return err
	}
	if len(tests) == 0 {
		return fmt.Errorf("no test files matched %s", strings.Join(patterns, " "))
	}
	evidence, err := runArgv(loaded.repository, command)
	if err != nil {
		return err
	}
	if kind == SealKindRed && evidence.ExitCode == 0 {
		return fmt.Errorf("red command %q exited 0; a red seal requires a non-zero exit proving the tests fail first", strings.Join(command, " "))
	}
	if kind == SealKindBaseline && evidence.ExitCode != 0 {
		return fmt.Errorf("green baseline %q exited %d; a baseline seal requires exit 0", strings.Join(command, " "), evidence.ExitCode)
	}
	base, _, err := currentBase(loaded.repository)
	if err != nil {
		return err
	}
	record := Seal{
		Kind:       kind,
		SealedAt:   time.Now().UTC().Format(time.RFC3339Nano),
		Base:       base,
		Tests:      tests,
		Red:        evidence,
		Amendments: []Amendment{},
		BoundArgv:  &BoundArgv{Argv: append([]string{}, command...), Digest: evidence.ArgvDigest},
	}
	if err := dropSupersededEvidence(loaded); err != nil {
		return err
	}
	return writeJSON(loaded.sealPath(), record)
}

// dropSupersededEvidence discards proof taken over an earlier baseline. A new
// or amended seal describes different tests, so a green run and a diff review
// recorded before it prove nothing about the tests now in force.
func dropSupersededEvidence(loaded *state) error {
	for _, stale := range []string{loaded.greenPath(), loaded.diffReviewPath(), loaded.handoffPath()} {
		if err := os.Remove(stale); err != nil && !os.IsNotExist(err) {
			return err
		}
	}
	loaded.green, loaded.diffReview, loaded.handoff = nil, nil, nil
	return nil
}

// handoff marks the sealing agent's work finished with the implementation still
// owed. It requires a seal (there is nothing to hand off otherwise), refuses
// once GREEN exists (the work is already implemented), and refuses while the
// sealed tests differ from the seal, so it cannot be used to park a broken one.
func handoff(loaded *state, to string) error {
	to = strings.TrimSpace(to)
	if to == "" {
		return fmt.Errorf("handoff requires --to <role>")
	}
	if loaded.seal == nil {
		// Reaching handoff means this repository entered the guard workflow. Keep
		// that fact even though the handoff is refused, so Stop cannot mistake a
		// skipped seal for a repository that never opted into the workflow.
		if err := os.MkdirAll(loaded.directory, 0o700); err != nil {
			return err
		}
		return fmt.Errorf("nothing to hand off: seal the tests first with `anvil-guard seal`")
	}
	if loaded.green != nil {
		return fmt.Errorf("green evidence already exists; the implementation is done, so there is nothing to hand off")
	}
	changed, err := loaded.changedTests()
	if err != nil {
		return err
	}
	if len(changed) > 0 {
		return fmt.Errorf("sealed tests changed since the seal: %s; hand off the tests you sealed, or reseal them explicitly", strings.Join(changed, ", "))
	}
	base, _, err := currentBase(loaded.repository)
	if err != nil {
		return err
	}
	return writeJSON(loaded.handoffPath(), Handoff{
		HandedOffAt: time.Now().UTC().Format(time.RFC3339Nano),
		To:          to,
		Base:        base,
	})
}

// verify records GREEN. The passing run must be the command the seal bound,
// must postdate the seal, and the sealed tests must be exactly what the seal
// digested before the run and throughout it. When a coverage command is supplied
// it is run after green succeeds and its strength number is recorded, but a
// coverage that errors, parses to nothing, or falls short of --min-coverage
// never blocks: test strength is a signal, not a new gate.
func verify(loaded *state, greenCommand, coverageCommand []string, minCoverage float64, stderr io.Writer) error {
	if loaded.seal == nil {
		return fmt.Errorf("no seal for %s; run `anvil-guard seal` first", loaded.repository)
	}
	if len(greenCommand) == 0 {
		return fmt.Errorf("verify requires --green-command <argv...>")
	}
	bound := loaded.seal.boundArgv()
	if offered := argvDigest(greenCommand); offered != bound.Digest {
		return fmt.Errorf("green command %q (argv digest %s) is not the command the seal bound (argv digest %s); verify must run the same argv that established the seal",
			strings.Join(greenCommand, " "), offered, bound.Digest)
	}
	changed, err := loaded.changedTests()
	if err != nil {
		return err
	}
	if len(changed) > 0 {
		return fmt.Errorf("sealed tests changed since the seal: %s; run `anvil-guard reseal --reason <text>` to amend them explicitly", strings.Join(changed, ", "))
	}
	before, err := loaded.sealedTestStats()
	if err != nil {
		return err
	}
	evidence, err := runArgv(loaded.repository, greenCommand)
	if err != nil {
		return err
	}
	// The pre-run digest check cannot see a test that was rewritten for the
	// duration of the run and put back before it exited; the file's own
	// metadata can.
	touched, err := loaded.sealedTestsTouchedSince(before)
	if err != nil {
		return err
	}
	if len(touched) > 0 {
		return fmt.Errorf("sealed tests changed during the green run: %s; the run proves nothing about the tests in force", strings.Join(touched, ", "))
	}
	if evidence.ExitCode != 0 {
		return fmt.Errorf("green command %q exited %d; verification requires exit 0", strings.Join(greenCommand, " "), evidence.ExitCode)
	}
	if !isAfter(evidence.StartedAt, loaded.seal.SealedAt) {
		return fmt.Errorf("green evidence %s does not postdate the seal %s", evidence.StartedAt, loaded.seal.SealedAt)
	}
	green := Green{CommandEvidence: evidence}
	if len(coverageCommand) > 0 {
		if coverage, ok := measureCoverage(loaded.repository, coverageCommand); ok {
			green.CoveragePercent = &coverage
			if minCoverage > 0 && coverage < minCoverage {
				fmt.Fprintf(stderr, "anvil-guard: coverage %.1f%% is below --min-coverage %.1f%% (advisory, not a gate)\n", coverage, minCoverage)
			}
		}
	}
	return writeJSON(loaded.greenPath(), green)
}

// reseal is the only sanctioned way to move a sealed test. The amendment stays
// in the seal so the assurance pass can inspect what the writer changed.
func reseal(loaded *state, reason string) error {
	if loaded.seal == nil {
		return fmt.Errorf("no seal for %s; nothing to amend", loaded.repository)
	}
	if loaded.seal.kind() == SealKindBaseline {
		return fmt.Errorf("cannot reseal a baseline seal: a refactor never amends its tests")
	}
	if strings.TrimSpace(reason) == "" {
		return fmt.Errorf("reseal requires --reason <text>")
	}
	before := loaded.sealedTests()
	after := make([]TestDigest, 0, len(before))
	for _, test := range before {
		content, err := os.ReadFile(filepath.Join(loaded.repository, filepath.FromSlash(test.Path)))
		if errors.Is(err, fs.ErrNotExist) {
			// A deleted test leaves the sealed set; the before/after pair in the
			// amendment is the record that it was removed on purpose.
			continue
		}
		if err != nil {
			return err
		}
		after = append(after, TestDigest{Path: test.Path, Digest: digestBytes(content)})
	}
	amendedAt := time.Now().UTC().Format(time.RFC3339Nano)
	record := *loaded.seal
	record.Amendments = append(append([]Amendment{}, record.Amendments...), Amendment{
		At: amendedAt, Reason: strings.TrimSpace(reason), Before: before, After: after,
	})
	record.Tests = after
	// The amendment is the baseline now in force. Advancing SealedAt is what
	// stops `seal -> verify -> gut the tests -> reseal` from finishing on a
	// green run that never executed the amended tests.
	record.SealedAt = amendedAt
	if err := dropSupersededEvidence(loaded); err != nil {
		return err
	}
	return writeJSON(loaded.sealPath(), record)
}

// recordDiffReview digests the real diff so the Stop gate can tell whether the
// change that was reviewed is still the change on disk.
func recordDiffReview(loaded *state, findingsPath string) error {
	if strings.TrimSpace(findingsPath) == "" {
		return fmt.Errorf("diff-review record requires --findings <file>")
	}
	target := findingsPath
	if !filepath.IsAbs(target) {
		target = filepath.Join(loaded.repository, filepath.FromSlash(findingsPath))
	}
	raw, err := os.ReadFile(target)
	if err != nil {
		return err
	}
	findings := make([]string, 0)
	for _, line := range strings.Split(string(raw), "\n") {
		if trimmed := strings.TrimSpace(line); trimmed != "" {
			findings = append(findings, trimmed)
		}
	}
	if len(findings) == 0 {
		return fmt.Errorf("findings file %s is empty; record what the diff review actually established", findingsPath)
	}
	evidence, err := runArgv(loaded.repository, []string{"git", "diff", "HEAD"})
	if err != nil {
		return err
	}
	base, digest, err := currentBase(loaded.repository)
	if err != nil {
		return err
	}
	return writeJSON(loaded.diffReviewPath(), DiffReview{
		ReviewedAt: time.Now().UTC().Format(time.RFC3339Nano),
		CommandID:  evidence.CommandID,
		Command:    evidence,
		DiffDigest: digest,
		Base:       base,
		Findings:   findings,
	})
}

// archCheck evaluates the structural architecture-conformance assertions with
// ast-grep and records the result. Structural design has to be a check the
// machine ran, not prose (CodeSpec RQ3), so each assertion is an ast-grep
// pattern that must be present or absent. When ast-grep is not installed the
// review is recorded as unverified -- never a pass -- mirroring the coverage
// tool's missing-verifier convention. The returned code is 0 when every
// assertion held (or the tool was absent), 2 when a structural rule is violated.
func archCheck(loaded *state, assertionsPath string, stderr io.Writer) (int, error) {
	if strings.TrimSpace(assertionsPath) == "" {
		return 1, fmt.Errorf("arch-check requires --assertions <file>")
	}
	target := assertionsPath
	if !filepath.IsAbs(target) {
		target = filepath.Join(loaded.repository, filepath.FromSlash(assertionsPath))
	}
	raw, err := os.ReadFile(target)
	if err != nil {
		return 1, err
	}
	var document struct {
		Assertions []ArchAssertion `json:"assertions"`
	}
	if err := json.Unmarshal(raw, &document); err != nil {
		return 1, fmt.Errorf("decode arch assertions %s: %w", assertionsPath, err)
	}
	if len(document.Assertions) == 0 {
		return 1, fmt.Errorf("arch assertions file %s declares no assertions", assertionsPath)
	}
	seen := make(map[string]struct{}, len(document.Assertions))
	for _, assertion := range document.Assertions {
		if strings.TrimSpace(assertion.ID) == "" {
			return 1, fmt.Errorf("every arch assertion needs an id")
		}
		if _, duplicate := seen[assertion.ID]; duplicate {
			return 1, fmt.Errorf("arch assertion id %q is listed more than once", assertion.ID)
		}
		seen[assertion.ID] = struct{}{}
		if strings.TrimSpace(assertion.Pattern) == "" {
			return 1, fmt.Errorf("arch assertion %q needs an astGrepPattern", assertion.ID)
		}
		if assertion.Expect != "present" && assertion.Expect != "absent" {
			return 1, fmt.Errorf("arch assertion %q expect must be \"present\" or \"absent\", got %q", assertion.ID, assertion.Expect)
		}
	}
	base, _, err := currentBase(loaded.repository)
	if err != nil {
		return 1, err
	}
	review := ArchReview{
		ReviewedAt: time.Now().UTC().Format(time.RFC3339Nano),
		Base:       base,
		Results:    make([]ArchAssertionResult, 0, len(document.Assertions)),
	}
	// A missing verifier is unverified, never a pass: record what would be
	// checked, but attach no command evidence so it is not a citeable record.
	if !astGrepInstalled() {
		for _, assertion := range document.Assertions {
			review.Results = append(review.Results, ArchAssertionResult{ArchAssertion: assertion})
		}
		review.Digest = archAssertionsDigest(review.Results)
		if err := writeJSON(loaded.archReviewPath(), review); err != nil {
			return 1, err
		}
		fmt.Fprintln(stderr, "anvil-guard: ast-grep is not installed; architecture conformance recorded as unverified")
		return 0, nil
	}
	runs := make([]controlplane.CommandEvidence, 0, len(document.Assertions))
	allPassed := true
	violations := make([]string, 0)
	var cachedFiles []string
	var walkErr error
	hasWalked := false
	for _, assertion := range document.Assertions {
		paths := []string{"."}
		if strings.TrimSpace(assertion.PathGlob) != "" {
			if !hasWalked {
				cachedFiles, walkErr = repositoryFilesWalk(loaded.repository)
				if walkErr != nil {
					return 1, walkErr
				}
				hasWalked = true
			}
			paths = matchGlobCached(cachedFiles, assertion.PathGlob)
		}
		count := 0
		if len(paths) > 0 {
			matchCount, evidence, runErr := runAstGrepPattern(loaded.repository, assertion.Pattern, paths)
			if runErr != nil {
				return 1, runErr
			}
			count = matchCount
			runs = append(runs, evidence)
		}
		passed := (assertion.Expect == "present" && count > 0) || (assertion.Expect == "absent" && count == 0)
		if !passed {
			allPassed = false
			violations = append(violations, assertion.ID)
		}
		review.Results = append(review.Results, ArchAssertionResult{ArchAssertion: assertion, MatchCount: count, Passed: passed})
	}
	review.Verified = true
	review.Passed = allPassed
	review.Digest = archAssertionsDigest(review.Results)
	// Every assertion may resolve to zero scanned files, leaving no run to
	// aggregate; synthesize one so the verified review is still a citeable record.
	if len(runs) == 0 {
		runs = append(runs, controlplane.CommandEvidence{
			ArgvDigest:   digestBytes([]byte(review.Digest)),
			StartedAt:    review.ReviewedAt,
			FinishedAt:   review.ReviewedAt,
			StdoutDigest: digestBytes(nil),
			StderrDigest: digestBytes(nil),
		})
	}
	evidence := aggregateArchEvidence(runs, allPassed)
	review.CommandID = evidence.CommandID
	review.Command = &evidence
	if err := writeJSON(loaded.archReviewPath(), review); err != nil {
		return 1, err
	}
	if !allPassed {
		fmt.Fprintf(stderr, "anvil-guard: architecture conformance failed: %s\n", strings.Join(violations, ", "))
		return 2, nil
	}
	return 0, nil
}

// archAssertionsDigest pins the assertion set and its outcomes so a reader can
// tell whether two arch reviews checked the same structural rules.
func archAssertionsDigest(results []ArchAssertionResult) string {
	encoded, err := json.Marshal(results)
	if err != nil {
		return digestBytes(nil)
	}
	return digestBytes(encoded)
}

// archReviewStale reports whether a recorded arch review was taken over a
// different working tree than the one on disk now.
func archReviewStale(loaded *state) (bool, error) {
	if loaded.archReview == nil {
		return false, nil
	}
	_, digest, err := currentBase(loaded.repository)
	if err != nil {
		return false, err
	}
	return digest != loaded.archReview.Base.TreeDigest, nil
}

// stopBlockers lists every reason the writer may not finish yet.
// stopGateBlockers is what the Stop hook enforces: whether *this agent* may
// finish. A handed-off state is mid-wave, not incomplete -- the sealing agent
// owes nothing more -- so it stops cleanly. This deliberately differs from
// stopBlockers, which answers whether the change is ready to merge and stays
// unsatisfied until GREEN and a fresh diff review exist.
func stopGateBlockers(loaded *state) ([]string, error) {
	blockers, err := stopBlockers(loaded)
	if err != nil {
		return nil, err
	}
	if loaded.green == nil && loaded.handoff != nil {
		changed, err := loaded.changedTests()
		if err != nil {
			return nil, err
		}
		untouched, err := handoffTreeUntouched(loaded)
		if err != nil {
			return nil, err
		}
		if len(changed) == 0 && untouched {
			return nil, nil
		}
	}
	return blockers, nil
}

// handoffTreeUntouched reports whether the working tree still matches what was
// handed over. It is what stops the relaxation leaking past the agent that
// recorded it: an implementer who wrote anything has moved the tree, so the
// handoff no longer describes the state it is stopping in.
func handoffTreeUntouched(loaded *state) (bool, error) {
	if loaded.handoff == nil {
		return false, nil
	}
	base, _, err := currentBase(loaded.repository)
	if err != nil {
		return false, err
	}
	return base == loaded.handoff.Base, nil
}

func stopBlockers(loaded *state) ([]string, error) {
	blockers := make([]string, 0, 3)
	if loaded.seal == nil {
		return append(blockers, "no seal; run `anvil-guard seal --tests <globs> --red-command <argv...>` (or `--green-baseline <argv...>` for a refactor) first"), nil
	}
	changed, err := loaded.changedTests()
	if err != nil {
		return nil, err
	}
	if len(changed) > 0 {
		blockers = append(blockers, "sealed tests changed without a recorded amendment: "+strings.Join(changed, ", "))
	}
	if loaded.green == nil {
		blockers = append(blockers, "no green evidence; run `anvil-guard verify --green-command <argv...>`")
	} else if loaded.seal != nil && !isAfter(loaded.green.StartedAt, loaded.seal.SealedAt) {
		blockers = append(blockers, "green evidence predates the current seal; re-run `anvil-guard verify`")
	}
	stale, err := diffReviewStale(loaded)
	if err != nil {
		return nil, err
	}
	if stale {
		blockers = append(blockers, "diff review is missing or stale; run `anvil-guard diff-review record --findings <file>`")
	}
	return blockers, nil
}

func diffReviewStale(loaded *state) (bool, error) {
	if loaded.diffReview == nil {
		return true, nil
	}
	_, digest, err := currentBase(loaded.repository)
	if err != nil {
		return false, err
	}
	return digest != loaded.diffReview.DiffDigest, nil
}

func status(loaded *state) (Status, error) {
	report := Status{
		APIVersion: APIVersion, Repository: loaded.repository, StateDir: loaded.directory,
		Sealed: loaded.seal != nil, Seal: loaded.seal, Green: loaded.green, DiffReview: loaded.diffReview,
		ArchReview: loaded.archReview, Handoff: loaded.handoff, ChangedTests: []string{}, Records: loaded.records(),
	}
	// The arch review is independent of the test seal, so its staleness is
	// reported whether or not the repository is sealed.
	stale, err := archReviewStale(loaded)
	if err != nil {
		return Status{}, err
	}
	report.ArchStale = stale
	if loaded.seal == nil {
		return report, nil
	}
	report.SealKind = loaded.seal.kind()
	bound := loaded.seal.boundArgv()
	report.BoundArgv = &bound
	changed, err := loaded.changedTests()
	if err != nil {
		return Status{}, err
	}
	sort.Strings(changed)
	report.ChangedTests = changed
	if report.DiffStale, err = diffReviewStale(loaded); err != nil {
		return Status{}, err
	}
	blockers, err := stopBlockers(loaded)
	if err != nil {
		return Status{}, err
	}
	report.Ready = len(blockers) == 0
	return report, nil
}

// isSealedTestPath reports whether an edit target is one of the sealed tests.
// A harness payload carries the path exactly as the tool received it, so it may
// be absolute, relative to the tool's own working directory, or routed through
// a symlink; all three must land on the same repository-relative name the seal
// records.
func isSealedTestPath(loaded *state, workingDirectory, candidate string) bool {
	candidate = strings.TrimSpace(candidate)
	candidate = strings.ReplaceAll(candidate, "\\", "/")
	if candidate == "" {
		return false
	}
	absolute := absoluteTarget(workingDirectory, filepath.FromSlash(candidate))
	if absolute == "" {
		return false
	}
	relative, err := filepath.Rel(loaded.repository, resolveSymlinks(absolute))
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
		return false
	}
	relative = filepath.ToSlash(relative)
	for _, test := range loaded.sealedTests() {
		if test.Path == relative {
			return true
		}
	}
	return false
}

// absoluteTarget anchors a tool-supplied path to the session directory without
// the lexical cleaning filepath.Join performs. `..` has to survive intact this
// far: only resolveSymlinks knows what the preceding component really is.
func absoluteTarget(workingDirectory, candidate string) string {
	if filepath.IsAbs(candidate) {
		return candidate
	}
	if workingDirectory == "" {
		return ""
	}
	return workingDirectory + string(filepath.Separator) + candidate
}

// maxSymlinkHops bounds symlink expansion the way the kernel's ELOOP limit
// does, so a cyclic alias cannot spin the resolver.
const maxSymlinkHops = 40

// resolveSymlinks resolves a path physically, component by component, exactly
// as open(2) does: each name is expanded before the next one is applied, and
// `..` is applied to the already-resolved parent.
//
// Lexical cleaning cannot stand in for this. `filepath.Clean` collapses `a/..`
// by text, but when `a` is a symlink the kernel pops the link's *target*, so
// the two answers name different files -- and `<alias>/../<repo>/x` is a
// sealed test the lexical answer says is somewhere else entirely.
//
// A component that does not exist yet is kept as an ordinary name, so a file an
// edit tool has not created still resolves through its symlinked parent; the
// repository root is already resolved, so both sides of the comparison land in
// the same namespace.
func resolveSymlinks(absolute string) string {
	if !filepath.IsAbs(absolute) {
		return filepath.Clean(absolute)
	}
	resolved, pending, hops := string(filepath.Separator), pathComponents(absolute), 0
	for len(pending) > 0 {
		component := pending[0]
		pending = pending[1:]
		if component == ".." {
			resolved = filepath.Dir(resolved)
			continue
		}
		next := filepath.Join(resolved, component)
		info, err := os.Lstat(next)
		if err != nil || info.Mode()&os.ModeSymlink == 0 {
			resolved = next
			continue
		}
		target, err := os.Readlink(next)
		if err != nil {
			resolved = next
			continue
		}
		hops++
		if hops > maxSymlinkHops {
			return filepath.Join(append([]string{next}, pending...)...)
		}
		if filepath.IsAbs(target) {
			resolved = string(filepath.Separator)
		}
		pending = append(pathComponents(target), pending...)
	}
	return resolved
}

func pathComponents(pathname string) []string {
	pathname = strings.ReplaceAll(pathname, "\\", "/")
	parts := strings.Split(filepath.ToSlash(pathname), "/")
	components := make([]string, 0, len(parts))
	for _, part := range parts {
		if part != "" && part != "." {
			components = append(components, part)
		}
	}
	return components
}
