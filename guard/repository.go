package guard

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"os/exec"
	"path"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/anvil008/swarm-coder/controlplane"
)

// skippedDirectories are never scanned for sealable tests. They are either
// version-control internals or vendored trees no writer is expected to seal.
var skippedDirectories = map[string]struct{}{
	".git": {}, ".jj": {}, "node_modules": {},
}

// runArgv executes one command as an argv array, never through a shell, and
// returns bounded proof of what it did.
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
		ArgvDigest:   digestBytes([]byte(strings.Join(argv, "\x00"))),
		ExitCode:     command.ProcessState.ExitCode(),
		StartedAt:    startedAt.Format(time.RFC3339Nano),
		FinishedAt:   finishedAt.Format(time.RFC3339Nano),
		StdoutDigest: digestBytes(stdout.Bytes()),
		StderrDigest: digestBytes(stderr.Bytes()),
	}
	evidence.CommandID = commandID(evidence)
	return evidence, nil
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
		content, err := os.ReadFile(filepath.Join(repository, filepath.FromSlash(name)))
		if err != nil {
			if !errors.Is(err, fs.ErrNotExist) {
				return nil, err
			}
			// A listed path that no longer resolves is itself part of the state
			// under review, so it stays in the digest as an empty content.
			content = nil
		}
		combined = append(combined, name...)
		combined = append(combined, 0)
		combined = append(combined, digestBytes(content)...)
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
	walkErr := filepath.WalkDir(repository, func(current string, entry fs.DirEntry, err error) error {
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
