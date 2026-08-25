package codingfleet

import (
	"bytes"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"github.com/anvil008/swarm-coder/guard"
)

// sealedGuardRepository puts one repository under seal so the decode-error path
// is live: with no seal anywhere the guard stays silent by design.
func sealedGuardRepository(t *testing.T) string {
	t.Helper()
	repository := t.TempDir()
	t.Setenv(guard.StateEnv, t.TempDir())
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
	if err := os.MkdirAll(filepath.Join(repository, "pkg"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(repository, "pkg", "thing_test.go"), []byte("package pkg\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	for _, argv := range [][]string{{"git", "add", "-A"}, {"git", "commit", "-m", "baseline"}} {
		command := exec.Command(argv[0], argv[1:]...)
		command.Dir = repository
		if output, err := command.CombinedOutput(); err != nil {
			t.Fatalf("%v: %v: %s", argv, err, output)
		}
	}
	stdout, stderr := &bytes.Buffer{}, &bytes.Buffer{}
	if code := guard.Run(guard.Options{Dir: repository, Stdout: stdout, Stderr: stderr},
		[]string{"seal", "--tests", "**/*_test.go", "--red-command", "false"}); code != 0 {
		t.Fatalf("seal exit %d: %s", code, stderr)
	}
	return repository
}

// registeredHookArgv strips the installed binary path off a registration and
// returns the arguments the harness would actually hand the guard. Deriving
// them from the installer is the point: a test that spells the argv itself
// cannot notice that the shipped registration omits `--event`.
func registeredHookArgv(t *testing.T, command, home string) []string {
	t.Helper()
	fields := strings.Fields(command)
	if len(fields) == 0 || fields[0] != guardInstalledPath(home) {
		t.Fatalf("registration %q does not invoke the installed guard", command)
	}
	return fields[1:]
}

// claudeFrontmatterHookArgv reads back the per-agent registrations Claude Code
// applies to every writing fleet definition.
func claudeFrontmatterHookArgv(t *testing.T, event string) []string {
	t.Helper()
	var frontmatter map[string][]struct {
		Matcher string `json:"matcher"`
		Hooks   []struct {
			Command string `json:"command"`
		} `json:"hooks"`
	}
	if err := json.Unmarshal([]byte(claudeGuardHooksFrontmatter()), &frontmatter); err != nil {
		t.Fatalf("decode claude frontmatter hooks: %v", err)
	}
	groups, ok := frontmatter[event]
	if !ok || len(groups) != 1 || len(groups[0].Hooks) != 1 {
		t.Fatalf("claude frontmatter has no single registration for %s: %v", event, frontmatter)
	}
	return registeredHookArgv(t, groups[0].Hooks[0].Command, canonicalHomeDirectory)
}

func runGuard(t *testing.T, dir string, argv []string, stdin string) (int, string, string) {
	t.Helper()
	stdout, stderr := &bytes.Buffer{}, &bytes.Buffer{}
	code := guard.Run(guard.Options{Dir: dir, Stdin: strings.NewReader(stdin), Stdout: stdout, Stderr: stderr}, argv)
	return code, stdout.String(), stderr.String()
}

// refusalShape is the documented block dialect for one harness and event.
// PostToolUse can block nowhere, so Claude and Codex use their documented
// stderr message channel; a `permissionDecision` there is read by nobody.
type refusalShape struct {
	exitCode int
	stdout   map[string]any
	stderr   bool
}

func hookRefusalShapes(t *testing.T) map[string]map[string]refusalShape {
	t.Helper()
	claudeDeny := func(event string) refusalShape {
		return refusalShape{stdout: map[string]any{"hookSpecificOutput": map[string]any{
			"hookEventName": event, "permissionDecision": "deny",
		}}}
	}
	return map[string]map[string]refusalShape{
		"claude": {
			"PreToolUse":   claudeDeny("PreToolUse"),
			"PostToolUse":  {exitCode: 2, stderr: true},
			"Stop":         {exitCode: 2, stderr: true},
			"SubagentStop": {exitCode: 2, stderr: true},
		},
		"codex": {
			"PreToolUse":   {stdout: map[string]any{"decision": "block"}},
			"PostToolUse":  {exitCode: 2, stderr: true},
			"Stop":         {stdout: map[string]any{"continue": false}},
			"SubagentStop": {stdout: map[string]any{"continue": false}},
		},
		"agy": {
			"PreToolUse":  {stdout: map[string]any{"decision": "deny"}},
			"PostToolUse": {stdout: map[string]any{"decision": "deny"}},
			"Stop":        {stdout: map[string]any{"decision": "continue"}},
		},
	}
}

func assertRefusalShape(t *testing.T, label string, want refusalShape, code int, stdout, stderr string) {
	t.Helper()
	if code != want.exitCode {
		t.Fatalf("%s: exit %d, want %d (stdout %q stderr %q)", label, code, want.exitCode, stdout, stderr)
	}
	if want.stderr && strings.TrimSpace(stderr) == "" {
		t.Fatalf("%s: refusal carried no message on stderr", label)
	}
	if want.stdout == nil {
		if strings.TrimSpace(stdout) != "" {
			t.Fatalf("%s: unexpected stdout %q", label, stdout)
		}
		return
	}
	var decoded map[string]any
	if err := json.Unmarshal([]byte(stdout), &decoded); err != nil {
		t.Fatalf("%s: decode stdout %q: %v", label, stdout, err)
	}
	assertSubset(t, label, want.stdout, decoded)
}

func assertSubset(t *testing.T, label string, want map[string]any, got map[string]any) {
	t.Helper()
	for key, expected := range want {
		actual, present := got[key]
		if !present {
			t.Fatalf("%s: response is missing %q: %v", label, key, got)
		}
		if nested, ok := expected.(map[string]any); ok {
			inner, ok := actual.(map[string]any)
			if !ok {
				t.Fatalf("%s: %q is not an object: %v", label, key, actual)
			}
			assertSubset(t, label+"."+key, nested, inner)
			continue
		}
		if actual != expected {
			t.Fatalf("%s: %q = %v, want %v", label, key, actual, expected)
		}
	}
}

// H1: the defect. Claude and Codex registered every event with a bare
// `hook --harness <name>`, so a malformed payload -- which is precisely when
// the guard has nothing else to go on -- was classified as PreToolUse. The
// resulting `permissionDecision` refusal is a documented no-op on Stop and
// PostToolUse, so the fail-closed path silently failed open on the Stop gate.
func TestRegisteredHookRefusesMalformedPayloadsInTheRightDialect(t *testing.T) {
	repository := sealedGuardRepository(t)
	home := t.TempDir()
	malformed := `{"hook_event_name":"Stop","cwd":"` + repository + `","session_i`
	shapes := hookRefusalShapes(t)

	for _, harness := range []string{"claude", "codex", "agy"} {
		for _, event := range hookEventsFor(harness) {
			want, known := shapes[harness][event]
			if !known {
				t.Fatalf("no documented refusal shape for %s/%s", harness, event)
			}
			argv := registeredHookArgv(t, guardHookGroup(home, harness, event).Hooks[0].Command, home)
			code, stdout, stderr := runGuard(t, repository, argv, malformed)
			assertRefusalShape(t, harness+"/"+event, want, code, stdout, stderr)
		}
	}
}

// H2: the per-agent Claude frontmatter is a second registration surface with
// the same failure mode.
func TestClaudeFrontmatterHooksRefuseMalformedPayloadsInTheRightDialect(t *testing.T) {
	repository := sealedGuardRepository(t)
	malformed := `{"hook_event_name":"Stop","cwd":"` + repository + `","session_i`
	shapes := hookRefusalShapes(t)["claude"]

	for _, event := range []string{"PreToolUse", "PostToolUse", "Stop"} {
		argv := claudeFrontmatterHookArgv(t, event)
		code, stdout, stderr := runGuard(t, repository, argv, malformed)
		assertRefusalShape(t, "claude-frontmatter/"+event, shapes[event], code, stdout, stderr)
	}
}

// H3: a well-formed payload for the same event must already have produced the
// documented dialect, so H1 isolates the decode path rather than the emitter.
func TestWellFormedStopPayloadsAlreadyUseTheDocumentedDialect(t *testing.T) {
	repository := sealedGuardRepository(t)
	home := t.TempDir()
	shapes := hookRefusalShapes(t)

	for _, harness := range []string{"claude", "codex", "agy"} {
		stop := `{"hook_event_name":"Stop","cwd":"` + repository + `","session_id":"s-1","workspacePaths":["` + repository + `"],"conversationId":"s-1"}`
		argv := registeredHookArgv(t, guardHookGroup(home, harness, "Stop").Hooks[0].Command, home)
		code, stdout, stderr := runGuard(t, repository, argv, stop)
		assertRefusalShape(t, harness+"/Stop(well-formed)", shapes[harness]["Stop"], code, stdout, stderr)
	}
}

func hookEventsFor(harness string) []string {
	switch harness {
	case "claude":
		return claudeHookEvents
	case "codex":
		return codexHookEvents
	default:
		return antigravityHookEvents
	}
}
