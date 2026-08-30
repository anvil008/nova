// Package guard implements anvil-guard, the harness-neutral test-seal and
// diff-review gate. It records a RED baseline before implementation, refuses
// edits to sealed tests, and refuses to let an agent stop until a passing run
// and a real diff review exist for the change actually on disk.
package guard

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/anvil008/workcell/controlplane"
)

const (
	// APIVersion identifies the machine-readable `status` contract.
	APIVersion = "anvil.guard/v1"
	// StateEnv overrides the base directory holding per-repository state.
	StateEnv = "ANVIL_GUARD_STATE"
	// ConfigPath is the repository-relative test-glob override.
	ConfigPath = ".anvil/guard.json"
	// AstGrepEnv overrides the ast-grep binary the arch-check resolves. It exists
	// so the structural verifier can be pinned or, in tests, replaced by a
	// stand-in; when unset the check resolves the default `ast-grep` on PATH.
	AstGrepEnv = "ANVIL_GUARD_ASTGREP"

	sealFileName       = "seal.json"
	greenFileName      = "green.json"
	diffReviewFileName = "diff-review.json"
	archReviewFileName = "arch-review.json"
	handoffFileName    = "handoff.json"
)

// DefaultTestPatterns is the fleet-wide test surface. A repository narrows or
// widens it through ConfigPath rather than through a per-invocation flag.
var DefaultTestPatterns = []string{
	"**/*_test.go", "**/*.spec.*", "**/*.test.*", "**/test_*.py", "**/tests/**", "**/testdata/**",
}

// TestDigest pins one sealed test file to its content at seal time.
type TestDigest struct {
	Path   string `json:"path"`
	Digest string `json:"digest"`
}

// Base pins the revision and working-tree state a seal or review was taken on.
type Base struct {
	HeadCommit string `json:"headCommit"`
	TreeDigest string `json:"treeDigest"`
}

// Amendment is the explicit, recorded permission to change a sealed test.
type Amendment struct {
	At     string       `json:"at"`
	Reason string       `json:"reason"`
	Before []TestDigest `json:"before"`
	After  []TestDigest `json:"after"`
}

// BoundArgv is the command the seal binds verification to. The red run proves
// these tests fail; only the same argv can later prove they pass, otherwise
// `seal --red-command false` followed by `verify --green-command true` is a
// complete TDD cycle on paper.
type BoundArgv struct {
	Argv   []string `json:"argv"`
	Digest string   `json:"digest"`
}

// Seal is the RED baseline: the tests that must not move plus proof they
// actually failed before any implementation ran.
type Seal struct {
	SealedAt   string                       `json:"sealedAt"`
	Base       Base                         `json:"base"`
	Tests      []TestDigest                 `json:"tests"`
	Red        controlplane.CommandEvidence `json:"red"`
	Amendments []Amendment                  `json:"amendments"`
	// BoundArgv is absent from seals written before the binding existed; those
	// bind to Red.ArgvDigest, which every seal has always recorded.
	BoundArgv *BoundArgv `json:"boundArgv,omitempty"`
}

// boundArgv returns the binding in force, synthesizing one for a legacy seal.
func (s *Seal) boundArgv() BoundArgv {
	if s.BoundArgv != nil {
		return *s.BoundArgv
	}
	return BoundArgv{Digest: s.Red.ArgvDigest}
}

// Green is the passing run recorded at verify time. It carries the full command
// evidence plus an optional test-strength signal. CoveragePercent is advisory:
// it is captured when `verify --coverage-command` is given and the tool emits a
// parseable percentage, and it never gates verification.
type Green struct {
	controlplane.CommandEvidence
	CoveragePercent *float64 `json:"coveragePercent,omitempty"`
}

// DiffReview records that the real `git diff HEAD` was read, not summarized.
// Command is the full evidence of that read; CommandID is the same identifier
// hoisted out so a reader does not have to reach into the evidence for it.
type DiffReview struct {
	ReviewedAt string                       `json:"reviewedAt"`
	CommandID  string                       `json:"commandId"`
	Command    controlplane.CommandEvidence `json:"command"`
	DiffDigest string                       `json:"diffDigest"`
	Base       Base                         `json:"base"`
	Findings   []string                     `json:"findings"`
}

// ArchAssertion is one structural design rule the arch-check evaluates with
// ast-grep: which module must call or import what, which boundary must hold.
// Expect is "present" (at least one match required) or "absent" (no match
// allowed); PathGlob narrows the files searched to a `**`-aware glob.
type ArchAssertion struct {
	ID          string `json:"id"`
	Description string `json:"description"`
	Pattern     string `json:"astGrepPattern"`
	Expect      string `json:"expect"`
	PathGlob    string `json:"pathGlob,omitempty"`
}

// ArchAssertionResult records how one assertion fared: the match count ast-grep
// reported and whether that satisfied the expectation.
type ArchAssertionResult struct {
	ArchAssertion
	MatchCount int  `json:"matchCount"`
	Passed     bool `json:"passed"`
}

// ArchReview is the executable architecture-conformance record: the structural
// assertions checked with ast-grep and whether each held. When ast-grep is not
// installed the review is Verified=false -- unverified, never passed -- mirroring
// the missing-verifier convention that a tool that never ran proves nothing, so
// an unverified review carries no command evidence and is not a citeable record.
type ArchReview struct {
	ReviewedAt string                        `json:"reviewedAt"`
	Verified   bool                          `json:"verified"`
	Passed     bool                          `json:"passed"`
	CommandID  string                        `json:"commandId,omitempty"`
	Command    *controlplane.CommandEvidence `json:"command,omitempty"`
	Results    []ArchAssertionResult         `json:"results"`
	Digest     string                        `json:"digest"`
	Base       Base                          `json:"base"`
}

// Handoff records that the agent which sealed the tests finished its part and
// owes the implementation to a different agent. It exists because a test-author
// legitimately stops with a seal and no GREEN: without this marker the Stop gate
// -- which is written for an implementer -- would deadlock it.
//
// A handoff relaxes the Stop gate only. It never satisfies the merge gate: an
// orchestrator reads Ready, which still requires GREEN and a fresh diff review.
type Handoff struct {
	HandedOffAt string `json:"handedOffAt"`
	To          string `json:"to"`
	// Base pins the working tree as it was handed over. The Stop relaxation
	// covers *that* state and nothing after it: once the next agent changes a
	// byte, it owes GREEN like any implementer, so a builder cannot coast to a
	// clean stop on the test-author's handoff.
	Base Base `json:"base"`
}

// Status is the machine-readable state the orchestrator reconciles.
type Status struct {
	APIVersion   string      `json:"apiVersion"`
	Repository   string      `json:"repository"`
	StateDir     string      `json:"stateDir"`
	Sealed       bool        `json:"sealed"`
	Seal         *Seal       `json:"seal,omitempty"`
	BoundArgv    *BoundArgv  `json:"boundArgv,omitempty"`
	Green        *Green      `json:"green,omitempty"`
	DiffReview   *DiffReview `json:"diffReview,omitempty"`
	ArchReview   *ArchReview `json:"archReview,omitempty"`
	Handoff      *Handoff    `json:"handoff,omitempty"`
	ChangedTests []string    `json:"changedTests"`
	DiffStale    bool        `json:"diffStale"`
	ArchStale    bool        `json:"archStale"`
	Ready        bool        `json:"ready"`
	// Records is the stable list of runs anvil-guard itself performed. It is
	// what the control plane resolves an agent-cited commandId against.
	Records []controlplane.GuardRecord `json:"records"`
}

// Snapshot reads one repository's guard-produced records without running git
// or touching the repository. The run-plane supervisor calls it directly after
// a foreign child exits; it returns nil when the repository was never sealed,
// because then there is nothing to resolve a cited commandId against.
//
// Note that this is resolution, not a trust boundary: the state directory is
// writable by the same OS user, so a deliberate forgery of these records is out
// of scope by design and is what the LXC 135 holdout measures.
func Snapshot(repositoryRoot string) (*controlplane.GuardSnapshot, error) {
	resolved := filepath.Clean(repositoryRoot)
	if evaluated, err := filepath.EvalSymlinks(resolved); err == nil {
		resolved = evaluated
	}
	loaded, err := loadRepositoryState(resolved)
	if err != nil {
		return nil, err
	}
	if loaded.seal == nil {
		return nil, nil
	}
	return &controlplane.GuardSnapshot{
		APIVersion: controlplane.GuardSnapshotAPIVersion,
		Repository: loaded.repository,
		Records:    loaded.records(),
	}, nil
}

// stateBaseDirectory resolves the directory holding every per-repository state
// directory and the per-session touch logs.
func stateBaseDirectory() (string, error) {
	base := strings.TrimSpace(os.Getenv(StateEnv))
	if base == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return "", fmt.Errorf("resolve home for guard state: %w", err)
		}
		base = filepath.Join(home, ".local", "state", "anvil-guard")
	}
	if !filepath.IsAbs(base) {
		return "", fmt.Errorf("guard state directory %q must be absolute", base)
	}
	return filepath.Clean(base), nil
}

// StateDirectory resolves the per-repository state directory. The repository
// path is hashed so unrelated checkouts of the same project stay separate.
func StateDirectory(repositoryRoot string) (string, error) {
	base, err := stateBaseDirectory()
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256([]byte(filepath.Clean(repositoryRoot)))
	return filepath.Join(base, hex.EncodeToString(sum[:])), nil
}

func digestBytes(content []byte) string {
	sum := sha256.Sum256(content)
	return controlplane.CanonicalDigestPrefix + hex.EncodeToString(sum[:])
}

func readJSON[T any](pathname string) (*T, error) {
	raw, err := os.ReadFile(pathname)
	if errors.Is(err, fs.ErrNotExist) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	value := new(T)
	if err := json.Unmarshal(raw, value); err != nil {
		return nil, fmt.Errorf("decode %s: %w", pathname, err)
	}
	return value, nil
}

func writeJSON(pathname string, value any) error {
	encoded, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(pathname), 0o700); err != nil {
		return err
	}
	temporary, err := os.CreateTemp(filepath.Dir(pathname), ".anvil-guard-*")
	if err != nil {
		return err
	}
	temporaryPath := temporary.Name()
	if err := errors.Join(temporary.Chmod(0o600), writeAll(temporary, append(encoded, '\n')), temporary.Close()); err != nil {
		_ = os.Remove(temporaryPath)
		return err
	}
	if err := os.Rename(temporaryPath, pathname); err != nil {
		_ = os.Remove(temporaryPath)
		return err
	}
	return nil
}

func writeAll(file *os.File, content []byte) error {
	if _, err := file.Write(content); err != nil {
		return err
	}
	return file.Sync()
}

// state is the loaded per-repository guard state for one invocation.
type state struct {
	repository string
	directory  string
	seal       *Seal
	green      *Green
	diffReview *DiffReview
	archReview *ArchReview
	handoff    *Handoff
}

func loadState(workingDirectory string) (*state, error) {
	repository, err := repositoryRoot(workingDirectory)
	if err != nil {
		return nil, err
	}
	return loadRepositoryState(repository)
}

// loadRepositoryState reads the state of an already-resolved repository. The
// hook resolves repositories from the paths a tool would write, so it never has
// a working directory to hand.
func loadRepositoryState(repository string) (*state, error) {
	directory, err := StateDirectory(repository)
	if err != nil {
		return nil, err
	}
	loaded := &state{repository: repository, directory: directory}
	if loaded.seal, err = readJSON[Seal](filepath.Join(directory, sealFileName)); err != nil {
		return nil, err
	}
	if loaded.green, err = readJSON[Green](filepath.Join(directory, greenFileName)); err != nil {
		return nil, err
	}
	if loaded.diffReview, err = readJSON[DiffReview](filepath.Join(directory, diffReviewFileName)); err != nil {
		return nil, err
	}
	if loaded.archReview, err = readJSON[ArchReview](filepath.Join(directory, archReviewFileName)); err != nil {
		return nil, err
	}
	if loaded.handoff, err = readJSON[Handoff](filepath.Join(directory, handoffFileName)); err != nil {
		return nil, err
	}
	return loaded, nil
}

// sealedTests returns the digests currently in force: the original seal, or the
// most recent recorded amendment when the writer explicitly resealed.
func (s *state) sealedTests() []TestDigest {
	if s.seal == nil {
		return nil
	}
	if count := len(s.seal.Amendments); count > 0 {
		return s.seal.Amendments[count-1].After
	}
	return s.seal.Tests
}

// changedTests reports sealed paths whose current content no longer matches the
// digests in force, including sealed files that were deleted.
func (s *state) changedTests() ([]string, error) {
	changed := make([]string, 0)
	for _, test := range s.sealedTests() {
		content, err := os.ReadFile(filepath.Join(s.repository, filepath.FromSlash(test.Path)))
		if errors.Is(err, fs.ErrNotExist) {
			changed = append(changed, test.Path)
			continue
		}
		if err != nil {
			return nil, err
		}
		if digestBytes(content) != test.Digest {
			changed = append(changed, test.Path)
		}
	}
	return changed, nil
}

// testStat is what a sealed test looked like on disk at one instant. Digest
// catches a change that stayed; modification time and size catch one that was
// undone before anyone looked.
type testStat struct {
	digest  string
	modTime time.Time
	size    int64
}

// sealedTestStats snapshots every sealed test so a later call can tell whether
// any of them moved in between, even transiently.
func (s *state) sealedTestStats() (map[string]testStat, error) {
	stats := make(map[string]testStat, len(s.sealedTests()))
	for _, test := range s.sealedTests() {
		target := filepath.Join(s.repository, filepath.FromSlash(test.Path))
		content, err := os.ReadFile(target)
		if err != nil {
			return nil, err
		}
		info, err := os.Stat(target)
		if err != nil {
			return nil, err
		}
		stats[test.Path] = testStat{digest: digestBytes(content), modTime: info.ModTime(), size: info.Size()}
	}
	return stats, nil
}

// sealedTestsTouchedSince reports sealed tests whose content or metadata differ
// from an earlier snapshot, including tests that no longer exist.
func (s *state) sealedTestsTouchedSince(before map[string]testStat) ([]string, error) {
	after, err := s.sealedTestStats()
	if err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			return s.changedTests()
		}
		return nil, err
	}
	touched := make([]string, 0)
	for path, was := range before {
		if now, ok := after[path]; !ok || now != was {
			touched = append(touched, path)
		}
	}
	sort.Strings(touched)
	return touched, nil
}

// records lists the runs anvil-guard performed for this repository, in a stable
// order so two readers of the same state agree byte for byte.
func (s *state) records() []controlplane.GuardRecord {
	collected := make([]controlplane.GuardRecord, 0, 3)
	if s.seal != nil && s.seal.Red.CommandID != "" {
		collected = append(collected, controlplane.GuardRecord{
			Kind: controlplane.GuardRecordSealRed, CommandID: s.seal.Red.CommandID, Evidence: s.seal.Red,
		})
	}
	if s.green != nil && s.green.CommandID != "" {
		collected = append(collected, controlplane.GuardRecord{
			Kind: controlplane.GuardRecordGreen, CommandID: s.green.CommandID, Evidence: s.green.CommandEvidence,
		})
	}
	if s.diffReview != nil && s.diffReview.CommandID != "" {
		collected = append(collected, controlplane.GuardRecord{
			Kind: controlplane.GuardRecordDiffReview, CommandID: s.diffReview.CommandID, Evidence: s.diffReview.Command,
		})
	}
	// An unverified arch review (ast-grep absent) records no command, so it never
	// becomes a citeable record: a tool that never ran cannot back a claim.
	if s.archReview != nil && s.archReview.CommandID != "" && s.archReview.Command != nil {
		collected = append(collected, controlplane.GuardRecord{
			Kind: controlplane.GuardRecordArchReview, CommandID: s.archReview.CommandID, Evidence: *s.archReview.Command,
		})
	}
	return collected
}

func (s *state) sealPath() string       { return filepath.Join(s.directory, sealFileName) }
func (s *state) greenPath() string      { return filepath.Join(s.directory, greenFileName) }
func (s *state) diffReviewPath() string { return filepath.Join(s.directory, diffReviewFileName) }
func (s *state) archReviewPath() string { return filepath.Join(s.directory, archReviewFileName) }
func (s *state) handoffPath() string    { return filepath.Join(s.directory, handoffFileName) }
