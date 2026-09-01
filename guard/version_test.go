package guard

import (
	"bytes"
	"regexp"
	"strings"
	"testing"
)

// repositoryFreeDir returns a temporary directory that has no git or jj
// repository at or above it, and fails the test if that precondition does not
// hold. Every version assertion depends on it: the point of `version` is that
// an installed guard, run from $HOME or anywhere else, still answers.
func repositoryFreeDir(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	if root, err := repositoryRoot(dir); err == nil {
		t.Fatalf("fixture is invalid: %s resolves to repository root %s; the version command must be proven outside any repository", dir, root)
	}
	return dir
}

// TestVersionSubcommandPrintsSemverOutsideARepository pins the acceptance
// oracle `version-subcommand-prints-semver-outside-a-repository`.
func TestVersionSubcommandPrintsSemverOutsideARepository(t *testing.T) {
	dir := repositoryFreeDir(t)
	stdout, stderr := &bytes.Buffer{}, &bytes.Buffer{}

	code := Run(Options{Dir: dir, Stdout: stdout, Stderr: stderr}, []string{"version"})

	if code != 0 {
		t.Errorf("Run([version]) from %s = %d, want 0 (stderr: %q)", dir, code, stderr.String())
	}
	if want := "tdd-guard " + Version + "\n"; stdout.String() != want {
		t.Errorf("stdout = %q, want %q", stdout.String(), want)
	}
	if stderr.Len() != 0 {
		t.Errorf("stderr = %q, want empty", stderr.String())
	}
}

// TestVersionFlagsAreAliasesOfTheSubcommand pins the acceptance oracle
// `version-flags-are-aliases-of-the-subcommand`: byte-identical stdout and the
// same exit code for `version`, `--version` and `-v`.
func TestVersionFlagsAreAliasesOfTheSubcommand(t *testing.T) {
	dir := repositoryFreeDir(t)
	run := func(args ...string) (int, string, string) {
		stdout, stderr := &bytes.Buffer{}, &bytes.Buffer{}
		code := Run(Options{Dir: dir, Stdout: stdout, Stderr: stderr}, args)
		return code, stdout.String(), stderr.String()
	}

	baseCode, baseOut, baseErr := run("version")
	if baseCode != 0 {
		t.Fatalf("Run([version]) = %d, want 0 (stderr: %q)", baseCode, baseErr)
	}

	for _, alias := range []string{"--version", "-v"} {
		code, out, errOut := run(alias)
		if code != baseCode {
			t.Errorf("Run([%s]) exit = %d, want %d (stderr: %q)", alias, code, baseCode, errOut)
		}
		if out != baseOut {
			t.Errorf("Run([%s]) stdout = %q, want byte-identical to Run([version]) stdout %q", alias, out, baseOut)
		}
	}
}

// TestVersionConstantIsAPlainSemver pins the acceptance oracle
// `version-constant-is-a-plain-semver`.
func TestVersionConstantIsAPlainSemver(t *testing.T) {
	semver := regexp.MustCompile(`^[0-9]+\.[0-9]+\.[0-9]+$`)
	if !semver.MatchString(Version) {
		t.Errorf("Version = %q, want a plain semver matching %s (no v prefix, no build metadata)", Version, semver)
	}
	if Version == APIVersion {
		t.Errorf("Version = %q must not be the status --json contract identifier APIVersion = %q", Version, APIVersion)
	}
}

// TestVersionBuildMetadataAppendsAndNeverReplacesTheSemver pins the acceptance
// oracle `build-metadata-appends-and-never-replaces-the-semver`: an unstamped
// build degrades to a correct semver rather than to "dev" or "".
func TestVersionBuildMetadataAppendsAndNeverReplacesTheSemver(t *testing.T) {
	original := BuildMetadata
	t.Cleanup(func() { BuildMetadata = original })

	BuildMetadata = "abc1234"
	if got, want := VersionString(), Version+"+abc1234"; got != want {
		t.Errorf("with BuildMetadata=%q, VersionString() = %q, want %q", BuildMetadata, got, want)
	}

	BuildMetadata = ""
	if got, want := VersionString(), Version; got != want {
		t.Errorf("with BuildMetadata empty, VersionString() = %q, want %q", got, want)
	}
}

// TestVersionUsageListsTheVersionCommand pins the acceptance oracle
// `usage-lists-the-version-command`: the command is discoverable from --help
// the same way `status` is.
func TestVersionUsageListsTheVersionCommand(t *testing.T) {
	dir := repositoryFreeDir(t)
	stdout, stderr := &bytes.Buffer{}, &bytes.Buffer{}

	code := Run(Options{Dir: dir, Stdout: stdout, Stderr: stderr}, []string{"--help"})

	if code != 0 {
		t.Fatalf("Run([--help]) = %d, want 0 (stderr: %q)", code, stderr.String())
	}
	var found bool
	for _, line := range strings.Split(stdout.String(), "\n") {
		if strings.Contains(line, "version") {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("--help stdout lists no line naming `version`; got:\n%s", stdout.String())
	}
}
