package guard

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"os/exec"
	"path"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/anvil008/swarm-coder/controlplane"
)

// skippedDirectories are never scanned for sealable tests. They are either
// version-control internals or vendored trees no writer is expected to seal.
var skippedDirectories = map[string]struct{}{
	".git": {}, ".jj": {}, "node_modules": {},
}

var filepathWalkDir = filepath.WalkDir

// runArgv executes one command as an argv array, never through a shell, and
// returns bounded proof of what it did.
// argvDigest pins an argv array exactly as it was given: no re-splitting, no
// shell, so two commands share a digest only when they are the same command.
func argvDigest(argv []string) string {
	return digestBytes([]byte(strings.Join(argv, "\x00")))
}

func runArgv(workingDirectory string, argv []string) (controlplane.CommandEvidence, error) {
	if len(argv) == 0 {
		return controlplane.CommandEvidence{}, errors.New("command must be a non-empty argv array")
	}
	stdout, stderr := &bytes.Buffer{}, &bytes.Buffer{}
	command := exec.Command(argv[0], argv[1:]...)
	command.Dir = workingDirectory
	command.Stdout, command.Stderr = stdout, stderr
	startedAt := time.Now().UTC()
	runErr := command.Run()
	finishedAt := time.Now().UTC()
	var exitError *exec.ExitError
	if runErr != nil && !errors.As(runErr, &exitError) {
		return controlplane.CommandEvidence{}, fmt.Errorf("run %q: %w", argv[0], runErr)
	}
	evidence := controlplane.CommandEvidence{
		ArgvDigest:   argvDigest(argv),
		ExitCode:     command.ProcessState.ExitCode(),
		StartedAt:    startedAt.Format(time.RFC3339Nano),
		FinishedAt:   finishedAt.Format(time.RFC3339Nano),
		StdoutDigest: digestBytes(stdout.Bytes()),
		StderrDigest: digestBytes(stderr.Bytes()),
	}
	evidence.CommandID = commandID(evidence)
	return evidence, nil
}

// astGrepBinary resolves the structural verifier: the AstGrepEnv override when
// set, otherwise `ast-grep` on PATH.
func astGrepBinary() string {
	if override := strings.TrimSpace(os.Getenv(AstGrepEnv)); override != "" {
		return override
	}
	return "ast-grep"
}

// astGrepInstalled reports whether the resolved ast-grep binary can be run. A
// missing tool is what turns an arch-check into an unverified record rather than
// a pass or a fail.
func astGrepInstalled() bool {
	binary := astGrepBinary()
	if strings.ContainsRune(binary, filepath.Separator) {
		info, err := os.Stat(binary)
		return err == nil && !info.IsDir()
	}
	_, err := exec.LookPath(binary)
	return err == nil
}

// runAstGrepPattern runs one structural pattern over paths and returns the match
// count ast-grep reported. It never routes through a shell; paths are handed as
// an argv array. A non-zero exit is a real tool error (a bad pattern, say), not
// "no match", so it is surfaced rather than counted as zero.
func runAstGrepPattern(workingDirectory, pattern string, paths []string) (int, controlplane.CommandEvidence, error) {
	argv := append([]string{astGrepBinary(), "run", "--pattern", pattern, "--json"}, paths...)
	stdout, stderr := &bytes.Buffer{}, &bytes.Buffer{}
	command := exec.Command(argv[0], argv[1:]...)
	command.Dir = workingDirectory
	command.Stdout, command.Stderr = stdout, stderr
	startedAt := time.Now().UTC()
	runErr := command.Run()
	finishedAt := time.Now().UTC()
	var exitError *exec.ExitError
	if runErr != nil && !errors.As(runErr, &exitError) {
		return 0, controlplane.CommandEvidence{}, fmt.Errorf("run ast-grep: %w", runErr)
	}
	evidence := controlplane.CommandEvidence{
		ArgvDigest:   argvDigest(argv),
		ExitCode:     command.ProcessState.ExitCode(),
		StartedAt:    startedAt.Format(time.RFC3339Nano),
		FinishedAt:   finishedAt.Format(time.RFC3339Nano),
		StdoutDigest: digestBytes(stdout.Bytes()),
		StderrDigest: digestBytes(stderr.Bytes()),
	}
	evidence.CommandID = commandID(evidence)
	if evidence.ExitCode != 0 {
		return 0, evidence, fmt.Errorf("ast-grep exited %d for pattern %q: %s", evidence.ExitCode, pattern, strings.TrimSpace(stderr.String()))
	}
	count, err := countAstGrepMatches(stdout.Bytes())
	if err != nil {
		return 0, evidence, fmt.Errorf("parse ast-grep output for pattern %q: %w", pattern, err)
	}
	return count, evidence, nil
}

// countAstGrepMatches counts the entries in ast-grep's `--json` array. Empty
// output is treated as no matches so a pattern that finds nothing is not an error.
func countAstGrepMatches(output []byte) (int, error) {
	trimmed := bytes.TrimSpace(output)
	if len(trimmed) == 0 {
		return 0, nil
	}
	var matches []json.RawMessage
	if err := json.Unmarshal(trimmed, &matches); err != nil {
		return 0, err
	}
	return len(matches), nil
}

// aggregateArchEvidence folds the per-assertion ast-grep runs into one command
// record, so the arch-review resolves as a single citeable run whose exit code
// is 0 exactly when every structural assertion held.
func aggregateArchEvidence(runs []controlplane.CommandEvidence, allPassed bool) controlplane.CommandEvidence {
	argv, out, errs := make([]string, 0, len(runs)), make([]string, 0, len(runs)), make([]string, 0, len(runs))
	for _, run := range runs {
		argv = append(argv, run.ArgvDigest)
		out = append(out, run.StdoutDigest)
		errs = append(errs, run.StderrDigest)
	}
	exitCode := 0
	if !allPassed {
		exitCode = 1
	}
	evidence := controlplane.CommandEvidence{
		ArgvDigest:   argvDigest(argv),
		ExitCode:     exitCode,
		StartedAt:    runs[0].StartedAt,
		FinishedAt:   runs[len(runs)-1].FinishedAt,
		StdoutDigest: digestBytes([]byte(strings.Join(out, "\x00"))),
		StderrDigest: digestBytes([]byte(strings.Join(errs, "\x00"))),
	}
	evidence.CommandID = commandID(evidence)
	return evidence
}

// filesMatchingGlob resolves a `**`-aware repository glob to the repository-
// relative paths it selects, skipping version-control internals and vendored
// trees. It is how a pathGlob is scoped to concrete files before ast-grep runs.
func filesMatchingGlob(repository, glob string) ([]string, error) {
	matched := make([]string, 0)
	walkErr := filepathWalkDir(repository, func(current string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.IsDir() {
			if _, skip := skippedDirectories[entry.Name()]; skip && current != repository {
				return fs.SkipDir
			}
			return nil
		}
		if !entry.Type().IsRegular() {
			return nil
		}
		relative, err := filepath.Rel(repository, current)
		if err != nil {
			return err
		}
		relative = filepath.ToSlash(relative)
		if matchTestPattern(glob, relative) {
			matched = append(matched, filepath.FromSlash(relative))
		}
		return nil
	})
	if walkErr != nil {
		return nil, walkErr
	}
	sort.Strings(matched)
	return matched, nil
}

// coveragePattern matches a percentage token like `83.3%` or `85%`. It is
// deliberately loose so it catches the shapes coverage tools actually print,
// e.g. `coverage: 83.3% of statements` or `total: (statements) 85.0%`.
var coveragePattern = regexp.MustCompile(`([0-9]+(?:\.[0-9]+)?)\s*%`)

// measureCoverage runs an optional strength tool after a green run and extracts
// a single coverage number. It returns ok=false — and the caller records no
// strength — whenever the tool cannot be run, exits non-zero, or emits nothing
// parseable, so this can never turn a passing green into a failure.
func measureCoverage(workingDirectory string, argv []string) (float64, bool) {
	if len(argv) == 0 {
		return 0, false
	}
	stdout, stderr := &bytes.Buffer{}, &bytes.Buffer{}
	command := exec.Command(argv[0], argv[1:]...)
	command.Dir = workingDirectory
	command.Stdout, command.Stderr = stdout, stderr
	if err := command.Run(); err != nil {
		return 0, false
	}
	return parseCoverage(stdout.String() + "\n" + stderr.String())
}

// parseCoverage takes the last percentage token in the output, which is where
// summary tools print the total after any per-file lines.
func parseCoverage(output string) (float64, bool) {
	matches := coveragePattern.FindAllStringSubmatch(output, -1)
	if len(matches) == 0 {
		return 0, false
	}
	value, err := strconv.ParseFloat(matches[len(matches)-1][1], 64)
	if err != nil {
		return 0, false
	}
	return value, true
}

// captureArgv runs a command that must succeed and returns its stdout.
func captureArgv(workingDirectory string, argv ...string) ([]byte, error) {
	stdout, stderr := &bytes.Buffer{}, &bytes.Buffer{}
	command := exec.Command(argv[0], argv[1:]...)
	command.Dir = workingDirectory
	command.Stdout, command.Stderr = stdout, stderr
	if err := command.Run(); err != nil {
		return nil, fmt.Errorf("%s: %w: %s", strings.Join(argv, " "), err, strings.TrimSpace(stderr.String()))
	}
	return stdout.Bytes(), nil
}

func commandID(evidence controlplane.CommandEvidence) string {
	sum := sha256.Sum256([]byte(evidence.ArgvDigest + evidence.StartedAt + evidence.FinishedAt))
	return "cmd-" + hex.EncodeToString(sum[:8])
}

func repositoryRoot(workingDirectory string) (string, error) {
	output, err := captureArgv(workingDirectory, "git", "rev-parse", "--show-toplevel")
	if err != nil {
		return "", fmt.Errorf("resolve git repository from %s: %w", workingDirectory, err)
	}
	root := strings.TrimSpace(string(output))
	if root == "" {
		return "", fmt.Errorf("git reported no repository for %s", workingDirectory)
	}
	// macOS and container mounts routinely hand back a symlinked toplevel; the
	// resolved path keeps the state directory hash stable across invocations.
	resolved, err := filepath.EvalSymlinks(root)
	if err != nil {
		return "", err
	}
	return resolved, nil
}

func headCommit(repository string) (string, error) {
	output, err := captureArgv(repository, "git", "rev-parse", "HEAD")
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(string(output)), nil
}

// workingDiff returns the exact bytes a diff review must be taken over: the
// tracked diff against HEAD plus the name and content digest of every untracked
// file. Names alone would leave the Stop gate blind to a rewrite of a new file,
// which is precisely the code a change is most likely to be adding.
func workingDiff(repository string) ([]byte, error) {
	tracked, err := captureArgv(repository, "git", "diff", "HEAD")
	if err != nil {
		return nil, err
	}
	untracked, err := captureArgv(repository, "git", "ls-files", "--others", "--exclude-standard", "-z")
	if err != nil {
		return nil, err
	}
	combined := append(append([]byte(nil), tracked...), 0)
	for _, name := range strings.Split(string(untracked), "\x00") {
		if name == "" {
			continue
		}
		digest, err := digestFileStreaming(filepath.Join(repository, filepath.FromSlash(name)))
		if err != nil {
			return nil, err
		}
		combined = append(combined, name...)
		combined = append(combined, 0)
		combined = append(combined, digest...)
		combined = append(combined, 0)
	}
	return combined, nil
}

func currentBase(repository string) (Base, string, error) {
	commit, err := headCommit(repository)
	if err != nil {
		return Base{}, "", err
	}
	diff, err := workingDiff(repository)
	if err != nil {
		return Base{}, "", err
	}
	digest := digestBytes(diff)
	return Base{HeadCommit: commit, TreeDigest: digest}, digest, nil
}

// configuredPatterns resolves the repository override, falling back to the
// fleet defaults when `.anvil/guard.json` is absent.
func configuredPatterns(repository string) ([]string, error) {
	type guardConfig struct {
		Tests []string `json:"tests"`
	}
	config, err := readJSON[guardConfig](filepath.Join(repository, filepath.FromSlash(ConfigPath)))
	if err != nil {
		return nil, err
	}
	if config == nil || len(config.Tests) == 0 {
		return DefaultTestPatterns, nil
	}
	return config.Tests, nil
}

// collectTests digests every repository file matching any pattern.
func collectTests(repository string, patterns []string) ([]TestDigest, error) {
	matched := make(map[string]struct{})
	walkErr := filepathWalkDir(repository, func(current string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.IsDir() {
			if _, skip := skippedDirectories[entry.Name()]; skip && current != repository {
				return fs.SkipDir
			}
			return nil
		}
		if !entry.Type().IsRegular() {
			return nil
		}
		relative, err := filepath.Rel(repository, current)
		if err != nil {
			return err
		}
		relative = filepath.ToSlash(relative)
		for _, pattern := range patterns {
			if matchTestPattern(pattern, relative) {
				matched[relative] = struct{}{}
				break
			}
		}
		return nil
	})
	if walkErr != nil {
		return nil, walkErr
	}
	paths := make([]string, 0, len(matched))
	for relative := range matched {
		paths = append(paths, relative)
	}
	sort.Strings(paths)
	tests := make([]TestDigest, 0, len(paths))
	for _, relative := range paths {
		content, err := os.ReadFile(filepath.Join(repository, filepath.FromSlash(relative)))
		if err != nil {
			return nil, err
		}
		tests = append(tests, TestDigest{Path: relative, Digest: digestBytes(content)})
	}
	return tests, nil
}

// matchTestPattern matches slash-separated repository paths, where `**` spans
// zero or more path segments and every other segment uses path.Match syntax.
func matchTestPattern(pattern, name string) bool {
	return matchSegments(strings.Split(pattern, "/"), strings.Split(name, "/"))
}

func matchSegments(pattern, name []string) bool {
	for len(pattern) > 0 {
		if pattern[0] == "**" {
			// A trailing `**` means "inside this directory", so it must consume
			// at least one segment; `**/tests/**` is not a file named tests.
			if len(pattern) == 1 {
				return len(name) > 0
			}
			for index := 0; index <= len(name); index++ {
				if matchSegments(pattern[1:], name[index:]) {
					return true
				}
			}
			return false
		}
		if len(name) == 0 {
			return false
		}
		if ok, err := path.Match(pattern[0], name[0]); err != nil || !ok {
			return false
		}
		pattern, name = pattern[1:], name[1:]
	}
	return len(name) == 0
}

func digestFileStreaming(filePath string) (string, error) {
	file, err := os.Open(filePath)
	if err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			return digestBytes(nil), nil
		}
		return "", err
	}
	defer file.Close()

	const maxBytes = 10 * 1024 * 1024
	reader := io.LimitReader(file, maxBytes)

	hasher := sha256.New()
	if _, err := io.Copy(hasher, reader); err != nil {
		return "", err
	}
	sum := hasher.Sum(nil)
	return controlplane.CanonicalDigestPrefix + hex.EncodeToString(sum), nil
}

// repositoryFilesWalk walks the repository once and returns all regular files,
// skipping skippedDirectories.
func repositoryFilesWalk(repository string) ([]string, error) {
	files := make([]string, 0)
	walkErr := filepathWalkDir(repository, func(current string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.IsDir() {
			if _, skip := skippedDirectories[entry.Name()]; skip && current != repository {
				return fs.SkipDir
			}
			return nil
		}
		if !entry.Type().IsRegular() {
			return nil
		}
		relative, err := filepath.Rel(repository, current)
		if err != nil {
			return err
		}
		relative = filepath.ToSlash(relative)
		files = append(files, relative)
		return nil
	})
	if walkErr != nil {
		return nil, walkErr
	}
	return files, nil
}

// matchGlobCached filters the cached files by glob.
func matchGlobCached(cachedFiles []string, glob string) []string {
	matched := make([]string, 0)
	for _, relative := range cachedFiles {
		if matchTestPattern(glob, relative) {
			matched = append(matched, filepath.FromSlash(relative))
		}
	}
	sort.Strings(matched)
	return matched
}
