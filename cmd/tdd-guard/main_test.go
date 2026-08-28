package main

import (
	"encoding/json"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

// reexecEnv marks the child process that runs main() itself, so the real
// process boundary — argv, stdin, stdout, stderr, and the exit code — is what
// the assertions observe.
const reexecEnv = "ANVIL_GUARD_MAIN_REEXEC"

func TestMain(m *testing.M) {
	if os.Getenv(reexecEnv) == "1" {
		main()
		return
	}
	os.Exit(m.Run())
}

type invocation struct {
	code   int
	stdout string
	stderr string
}

func runMain(t *testing.T, directory, stdin string, args ...string) invocation {
	t.Helper()
	command := exec.Command(os.Args[0], args...)
	command.Dir = directory
	command.Env = append(os.Environ(), reexecEnv+"=1")
	command.Stdin = strings.NewReader(stdin)
	stdout, stderr := &strings.Builder{}, &strings.Builder{}
	command.Stdout, command.Stderr = stdout, stderr
	var exitError *exec.ExitError
	if err := command.Run(); err != nil && !errors.As(err, &exitError) {
		t.Fatalf("run %v: %v", args, err)
	}
	return invocation{code: command.ProcessState.ExitCode(), stdout: stdout.String(), stderr: stderr.String()}
}

func newRepository(t *testing.T) string {
	t.Helper()
	repository := t.TempDir()
	t.Setenv("ANVIL_GUARD_STATE", t.TempDir())
	for _, argv := range [][]string{
		{"git", "init", "--initial-branch=main"},
		{"git", "config", "user.email", "guard@example.test"},
		{"git", "config", "user.name", "Guard Test"},
		{"git", "config", "commit.gpgsign", "false"},
	} {
		command := exec.Command(argv[0], argv[1:]...)
		command.Dir = repository
		if output, err := command.CombinedOutput(); err != nil {
			t.Fatalf("%v: %v: %s", argv, err, output)
		}
	}
	if err := os.WriteFile(filepath.Join(repository, "thing_test.go"), []byte("package thing\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	for _, argv := range [][]string{{"git", "add", "-A"}, {"git", "commit", "-m", "baseline"}} {
		command := exec.Command(argv[0], argv[1:]...)
		command.Dir = repository
		if output, err := command.CombinedOutput(); err != nil {
			t.Fatalf("%v: %v: %s", argv, err, output)
		}
	}
	return repository
}

func TestMainReportsStatusForTheProcessDirectory(t *testing.T) {
	repository := newRepository(t)
	got := runMain(t, repository, "", "status")
	if got.code != 0 {
		t.Fatalf("status exit %d stderr %q", got.code, got.stderr)
	}
	var status struct {
		APIVersion string `json:"apiVersion"`
		Repository string `json:"repository"`
		Sealed     bool   `json:"sealed"`
	}
	if err := json.Unmarshal([]byte(got.stdout), &status); err != nil {
		t.Fatalf("decode %q: %v", got.stdout, err)
	}
	if status.APIVersion != "anvil.guard/v1" || status.Sealed {
		t.Fatalf("status = %+v", status)
	}
	if resolved, err := filepath.EvalSymlinks(repository); err != nil || status.Repository != resolved {
		t.Fatalf("status repository %q, want %q (%v)", status.Repository, resolved, err)
	}
}

func TestMainForwardsTheFailureExitCode(t *testing.T) {
	repository := newRepository(t)
	got := runMain(t, repository, "", "nonsense")
	if got.code != 1 || got.stdout != "" || !strings.Contains(got.stderr, "unknown command") {
		t.Fatalf("exit %d stdout %q stderr %q", got.code, got.stdout, got.stderr)
	}
}

func TestMainReadsTheHookPayloadFromStandardInput(t *testing.T) {
	repository := newRepository(t)
	payload := `{"hook_event_name":"PreToolUse","tool_name":"Edit","tool_input":{"file_path":"thing_test.go"},"cwd":"` + repository + `"}`

	silent := runMain(t, repository, payload, "hook", "--harness", "claude", "--event", "PreToolUse")
	if silent.code != 0 || silent.stdout != "" || silent.stderr != "" {
		t.Fatalf("unsealed repository: exit %d stdout %q stderr %q", silent.code, silent.stdout, silent.stderr)
	}

	sealed := runMain(t, repository, "", "seal", "--tests", "**/*_test.go", "--red-command", "false")
	if sealed.code != 0 {
		t.Fatalf("seal exit %d stderr %q", sealed.code, sealed.stderr)
	}
	denied := runMain(t, repository, payload, "hook", "--harness", "claude", "--event", "PreToolUse")
	if denied.code != 0 || !strings.Contains(denied.stdout, `"permissionDecision":"deny"`) {
		t.Fatalf("exit %d stdout %q stderr %q", denied.code, denied.stdout, denied.stderr)
	}
}

// false-then-true-no-longer-passes: the process boundary must refuse the
// original hole end to end, not just the in-process verify.
func TestMainRefusesFalseThenTrue(t *testing.T) {
	repository := newRepository(t)
	sealed := runMain(t, repository, "", "seal", "--tests", "**/*_test.go", "--red-command", "false")
	if sealed.code != 0 {
		t.Fatalf("seal exit %d stderr %q", sealed.code, sealed.stderr)
	}
	verified := runMain(t, repository, "", "verify", "--green-command", "true")
	if verified.code == 0 {
		t.Fatalf("verify --green-command true passed after seal --red-command false: stdout %q stderr %q", verified.stdout, verified.stderr)
	}
	if !strings.Contains(verified.stderr, "argv") {
		t.Fatalf("stderr %q does not explain the argv binding", verified.stderr)
	}
	status := runMain(t, repository, "", "status")
	if status.code != 0 || strings.Contains(status.stdout, `"green":`) {
		t.Fatalf("status after refused verify: exit %d stdout %q", status.code, status.stdout)
	}
}
