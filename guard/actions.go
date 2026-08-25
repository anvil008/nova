package guard

import (
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

// seal records the RED baseline. The red command must actually fail, otherwise
// the tests do not describe work that still needs doing.
func seal(loaded *state, patterns []string, redCommand []string) error {
	if len(redCommand) == 0 {
		return fmt.Errorf("seal requires --red-command <argv...>")
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
	evidence, err := runArgv(loaded.repository, redCommand)
	if err != nil {
		return err
	}
	if evidence.ExitCode == 0 {
		return fmt.Errorf("red command %q exited 0; a seal requires a non-zero exit proving the tests fail first", strings.Join(redCommand, " "))
	}
	base, _, err := currentBase(loaded.repository)
	if err != nil {
		return err
	}
	record := Seal{
		SealedAt:   time.Now().UTC().Format(time.RFC3339Nano),
		Base:       base,
		Tests:      tests,
		Red:        evidence,
		Amendments: []Amendment{},
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
	for _, stale := range []string{loaded.greenPath(), loaded.diffReviewPath()} {
		if err := os.Remove(stale); err != nil && !os.IsNotExist(err) {
			return err
		}
	}
	loaded.green, loaded.diffReview = nil, nil
	return nil
}

// verify records GREEN. The passing run must postdate the seal and the sealed
// tests must still be exactly what failed.
func verify(loaded *state, greenCommand []string) error {
	if loaded.seal == nil {
		return fmt.Errorf("no seal for %s; run `anvil-guard seal` first", loaded.repository)
	}
	if len(greenCommand) == 0 {
		return fmt.Errorf("verify requires --green-command <argv...>")
	}
	changed, err := loaded.changedTests()
	if err != nil {
		return err
	}
	if len(changed) > 0 {
		return fmt.Errorf("sealed tests changed since the seal: %s; run `anvil-guard reseal --reason <text>` to amend them explicitly", strings.Join(changed, ", "))
	}
	evidence, err := runArgv(loaded.repository, greenCommand)
	if err != nil {
		return err
	}
	if evidence.ExitCode != 0 {
		return fmt.Errorf("green command %q exited %d; verification requires exit 0", strings.Join(greenCommand, " "), evidence.ExitCode)
	}
	if !isAfter(evidence.StartedAt, loaded.seal.SealedAt) {
		return fmt.Errorf("green evidence %s does not postdate the seal %s", evidence.StartedAt, loaded.seal.SealedAt)
	}
	return writeJSON(loaded.greenPath(), evidence)
}

// reseal is the only sanctioned way to move a sealed test. The amendment stays
// in the seal so the assurance pass can inspect what the writer changed.
func reseal(loaded *state, reason string) error {
	if loaded.seal == nil {
		return fmt.Errorf("no seal for %s; nothing to amend", loaded.repository)
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

// stopBlockers lists every reason the writer may not finish yet.
func stopBlockers(loaded *state) ([]string, error) {
	blockers := make([]string, 0, 3)
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
		ChangedTests: []string{}, Records: loaded.records(),
	}
	if loaded.seal == nil {
		return report, nil
	}
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
	parts := strings.Split(filepath.ToSlash(pathname), "/")
	components := make([]string, 0, len(parts))
	for _, part := range parts {
		if part != "" && part != "." {
			components = append(components, part)
		}
	}
	return components
}
