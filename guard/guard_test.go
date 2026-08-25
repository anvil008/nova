package guard

import (
	"bytes"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

type harness struct {
	t          *testing.T
	repository string
	state      string
}

func newHarness(t *testing.T) *harness {
	t.Helper()
	repository := t.TempDir()
	state := t.TempDir()
	t.Setenv(StateEnv, state)
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
	h := &harness{t: t, repository: repository, state: state}
	h.write("go.mod", "module example.test\n")
	h.write("pkg/thing_test.go", "package pkg\n\nfunc TestThing(t *testing.T) {}\n")
	h.write("pkg/thing.go", "package pkg\n")
	h.commit("baseline")
	return h
}

func (h *harness) write(relative, content string) {
	h.t.Helper()
	target := filepath.Join(h.repository, filepath.FromSlash(relative))
	if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
		h.t.Fatal(err)
	}
	if err := os.WriteFile(target, []byte(content), 0o644); err != nil {
		h.t.Fatal(err)
	}
}

func (h *harness) commit(message string) {
	h.t.Helper()
	for _, argv := range [][]string{{"git", "add", "-A"}, {"git", "commit", "-m", message}} {
		command := exec.Command(argv[0], argv[1:]...)
		command.Dir = h.repository
		if output, err := command.CombinedOutput(); err != nil {
			h.t.Fatalf("%v: %v: %s", argv, err, output)
		}
	}
}

func (h *harness) run(args ...string) (int, string, string) {
	h.t.Helper()
	stdout, stderr := &bytes.Buffer{}, &bytes.Buffer{}
	code := Run(Options{Dir: h.repository, Stdout: stdout, Stderr: stderr}, args)
	return code, stdout.String(), stderr.String()
}

func (h *harness) runStdin(payload string, args ...string) (int, string, string) {
	h.t.Helper()
	stdout, stderr := &bytes.Buffer{}, &bytes.Buffer{}
	code := Run(Options{Dir: h.repository, Stdin: strings.NewReader(payload), Stdout: stdout, Stderr: stderr}, args)
	return code, stdout.String(), stderr.String()
}

// seal drives the ordinary RED step: a failing command over the default globs.
func (h *harness) seal() {
	h.t.Helper()
	code, _, stderr := h.run("seal", "--tests", "**/*_test.go", "--red-command", "false")
	if code != 0 {
		h.t.Fatalf("seal exit %d: %s", code, stderr)
	}
}

func (h *harness) readSeal() Seal {
	h.t.Helper()
	raw, err := os.ReadFile(filepath.Join(h.stateDirectory(), sealFileName))
	if err != nil {
		h.t.Fatal(err)
	}
	var seal Seal
	if err := json.Unmarshal(raw, &seal); err != nil {
		h.t.Fatal(err)
	}
	return seal
}

func (h *harness) stateDirectory() string {
	h.t.Helper()
	directory, err := StateDirectory(h.repository)
	if err != nil {
		h.t.Fatal(err)
	}
	return directory
}

func (h *harness) status() Status {
	h.t.Helper()
	code, stdout, stderr := h.run("status")
	if code != 0 {
		h.t.Fatalf("status exit %d: %s", code, stderr)
	}
	var status Status
	if err := json.Unmarshal([]byte(stdout), &status); err != nil {
		h.t.Fatalf("decode status %q: %v", stdout, err)
	}
	return status
}

func TestHooksAreSilentWithoutASeal(t *testing.T) {
	h := newHarness(t)
	payloads := map[string]string{
		"claude": `{"hook_event_name":"PreToolUse","tool_name":"Edit","tool_input":{"file_path":"pkg/thing_test.go"},"cwd":"` + h.repository + `"}`,
		"codex":  `{"hook_event_name":"PreToolUse","tool_name":"apply_patch","tool_input":{"file_path":"pkg/thing_test.go"},"cwd":"` + h.repository + `","turn_id":"t1"}`,
		"agy":    `{"toolCall":{"name":"write_to_file","args":{"TargetFile":"pkg/thing_test.go"}},"workspacePaths":["` + h.repository + `"],"conversationId":"c1"}`,
	}
	for harnessName, payload := range payloads {
		for _, event := range []string{"PreToolUse", "PostToolUse", "Stop"} {
			code, stdout, stderr := h.runStdin(payload, "hook", "--harness", harnessName, "--event", event)
			if code != 0 || stdout != "" || stderr != "" {
				t.Fatalf("%s/%s without a seal: exit %d stdout %q stderr %q", harnessName, event, code, stdout, stderr)
			}
		}
	}
}

func TestStopWarnsOnUnsealedSourceChanges(t *testing.T) {
	h := newHarness(t)
	// (c) nothing changed -> silent
	payloads := map[string]string{
		"claude": `{"hook_event_name":"Stop","cwd":"` + h.repository + `"}`,
		"codex":  `{"hook_event_name":"Stop","cwd":"` + h.repository + `","turn_id":"t1"}`,
		"agy":    `{"terminationReason":"idle","fullyIdle":true,"workspacePaths":["` + h.repository + `"]}`,
	}
	for harnessName, payload := range payloads {
		code, stdout, stderr := h.runStdin(payload, "hook", "--harness", harnessName, "--event", "Stop")
		if code != 0 || stdout != "" || stderr != "" {
			t.Fatalf("%s clean repo without seal: exit %d stdout %q stderr %q", harnessName, code, stdout, stderr)
		}
	}

	// (b) only a README.md changed -> silent
	h.write("README.md", "# new doc\n")
	for harnessName, payload := range payloads {
		code, stdout, stderr := h.runStdin(payload, "hook", "--harness", harnessName, "--event", "Stop")
		if code != 0 || stdout != "" || stderr != "" {
			t.Fatalf("%s only README.md changed: exit %d stdout %q stderr %q", harnessName, code, stdout, stderr)
		}
	}

	// (a) a changed .go file at Stop -> warning emitted, stop allowed
	h.write("pkg/thing.go", "package pkg\n\n// modified\n")
	for harnessName, payload := range payloads {
		code, stdout, stderr := h.runStdin(payload, "hook", "--harness", harnessName, "--event", "Stop")
		wantCode := 2
		if harnessName == "agy" {
			wantCode = 0
		}
		if code != wantCode {
			t.Fatalf("%s with changed source: exit %d, want %d", harnessName, code, wantCode)
		}
		if stdout != "" {
			t.Fatalf("%s with changed source: unexpected stdout %q", harnessName, stdout)
		}
		if !strings.Contains(stderr, "pkg/thing.go") || !strings.Contains(stderr, "seal") {
			t.Fatalf("%s with changed source: unexpected stderr %q", harnessName, stderr)
		}
	}
}

func TestSealRequiresTheRedCommandToFail(t *testing.T) {
	h := newHarness(t)
	code, _, stderr := h.run("seal", "--tests", "**/*_test.go", "--red-command", "true")
	if code == 0 {
		t.Fatal("seal accepted a passing red command")
	}
	if !strings.Contains(stderr, "non-zero") {
		t.Fatalf("stderr %q does not explain the red requirement", stderr)
	}
	if _, err := os.Stat(filepath.Join(h.stateDirectory(), sealFileName)); !os.IsNotExist(err) {
		t.Fatalf("a rejected seal still wrote state: %v", err)
	}
}

func TestSealRecordsTestDigestsAndRedEvidence(t *testing.T) {
	h := newHarness(t)
	h.seal()
	seal := h.readSeal()
	if len(seal.Tests) != 1 || seal.Tests[0].Path != "pkg/thing_test.go" {
		t.Fatalf("sealed tests = %+v", seal.Tests)
	}
	if seal.Red.ExitCode == 0 || seal.Red.CommandID == "" {
		t.Fatalf("red evidence = %+v", seal.Red)
	}
	if seal.Base.HeadCommit == "" || seal.Base.TreeDigest == "" || seal.SealedAt == "" {
		t.Fatalf("seal base = %+v sealedAt = %q", seal.Base, seal.SealedAt)
	}
	if seal.Amendments == nil {
		t.Fatal("amendments must be an explicit empty collection")
	}
}

func TestSealHonoursTheRepositoryTestOverride(t *testing.T) {
	h := newHarness(t)
	h.write("cases/case_one.check", "one\n")
	h.write(".anvil/guard.json", `{"tests":["cases/**"]}`)
	code, _, stderr := h.run("seal", "--red-command", "false")
	if code != 0 {
		t.Fatalf("seal exit %d: %s", code, stderr)
	}
	seal := h.readSeal()
	if len(seal.Tests) != 1 || seal.Tests[0].Path != "cases/case_one.check" {
		t.Fatalf("override ignored: %+v", seal.Tests)
	}
}

func TestVerifyRequiresGreenAndRecordsEvidence(t *testing.T) {
	h := newHarness(t)
	h.seal()
	if code, _, stderr := h.run("verify", "--green-command", "false"); code == 0 {
		t.Fatalf("verify accepted a failing green command: %s", stderr)
	}
	if _, err := os.Stat(filepath.Join(h.stateDirectory(), greenFileName)); !os.IsNotExist(err) {
		t.Fatalf("failed verify wrote green evidence: %v", err)
	}
	if code, _, stderr := h.run("verify", "--green-command", "true"); code != 0 {
		t.Fatalf("verify exit %d: %s", code, stderr)
	}
	status := h.status()
	if status.Green == nil || status.Green.ExitCode != 0 {
		t.Fatalf("green evidence = %+v", status.Green)
	}
	green, greenErr := time.Parse(time.RFC3339Nano, status.Green.StartedAt)
	sealed, sealErr := time.Parse(time.RFC3339Nano, status.Seal.SealedAt)
	if greenErr != nil || sealErr != nil || green.Before(sealed) {
		t.Fatalf("green %q does not postdate seal %q", status.Green.StartedAt, status.Seal.SealedAt)
	}
}

func TestVerifyRejectsAnEditedSealedTest(t *testing.T) {
	h := newHarness(t)
	h.seal()
	h.write("pkg/thing_test.go", "package pkg\n\n// weakened\n")
	code, _, stderr := h.run("verify", "--green-command", "true")
	if code == 0 {
		t.Fatal("verify accepted a modified sealed test")
	}
	if !strings.Contains(stderr, "pkg/thing_test.go") {
		t.Fatalf("stderr %q does not name the changed test", stderr)
	}
}

func TestResealRecordsAnExplicitAmendment(t *testing.T) {
	h := newHarness(t)
	h.seal()
	before := h.readSeal()
	h.write("pkg/thing_test.go", "package pkg\n\n// extended\n")
	if code, _, stderr := h.run("reseal", "--reason", "extend the reproduction case"); code != 0 {
		t.Fatalf("reseal exit %d: %s", code, stderr)
	}
	after := h.readSeal()
	if len(after.Amendments) != 1 {
		t.Fatalf("amendments = %+v", after.Amendments)
	}
	amendment := after.Amendments[0]
	if amendment.Reason != "extend the reproduction case" || amendment.At == "" {
		t.Fatalf("amendment = %+v", amendment)
	}
	if len(amendment.Before) != 1 || amendment.Before[0].Digest != before.Tests[0].Digest {
		t.Fatalf("amendment before = %+v", amendment.Before)
	}
	if len(amendment.After) != 1 || amendment.After[0].Digest == before.Tests[0].Digest {
		t.Fatalf("amendment after = %+v", amendment.After)
	}
	if after.Tests[0].Digest != amendment.After[0].Digest {
		t.Fatal("reseal did not adopt the amended digests")
	}
	if code, _, stderr := h.run("reseal"); code == 0 {
		t.Fatalf("reseal accepted a missing reason: %s", stderr)
	}
}

func TestDiffReviewRecordsTheCurrentDiff(t *testing.T) {
	h := newHarness(t)
	h.seal()
	h.write("pkg/thing.go", "package pkg\n\nfunc Thing() {}\n")
	h.write("findings.txt", "checked ownership\nchecked error handling\n")
	if code, _, stderr := h.run("diff-review", "record", "--findings", "findings.txt"); code != 0 {
		t.Fatalf("diff-review exit %d: %s", code, stderr)
	}
	status := h.status()
	if status.DiffReview == nil || status.DiffReview.DiffDigest == "" || status.DiffReview.CommandID == "" {
		t.Fatalf("diff review = %+v", status.DiffReview)
	}
	if len(status.DiffReview.Findings) != 2 {
		t.Fatalf("findings = %+v", status.DiffReview.Findings)
	}
	if status.DiffStale {
		t.Fatal("a freshly recorded review is not stale")
	}
	h.write("pkg/thing.go", "package pkg\n\nfunc Thing() int { return 1 }\n")
	if !h.status().DiffStale {
		t.Fatal("review did not go stale after the diff changed")
	}
}

func TestPreToolUseDeniesSealedTestEdits(t *testing.T) {
	h := newHarness(t)
	h.seal()
	cases := []struct {
		harness string
		payload string
		assert  func(t *testing.T, code int, stdout, stderr string)
	}{
		{
			harness: "claude",
			payload: `{"hook_event_name":"PreToolUse","tool_name":"Edit","tool_input":{"file_path":"` + filepath.Join(h.repository, "pkg/thing_test.go") + `"},"cwd":"` + h.repository + `"}`,
			assert: func(t *testing.T, code int, stdout, stderr string) {
				var decoded struct {
					HookSpecificOutput struct {
						HookEventName            string `json:"hookEventName"`
						PermissionDecision       string `json:"permissionDecision"`
						PermissionDecisionReason string `json:"permissionDecisionReason"`
					} `json:"hookSpecificOutput"`
				}
				if err := json.Unmarshal([]byte(stdout), &decoded); err != nil {
					t.Fatalf("decode %q: %v", stdout, err)
				}
				if decoded.HookSpecificOutput.PermissionDecision != "deny" || decoded.HookSpecificOutput.HookEventName != "PreToolUse" {
					t.Fatalf("claude decision = %+v", decoded)
				}
				if !strings.Contains(decoded.HookSpecificOutput.PermissionDecisionReason, "sealed") {
					t.Fatalf("claude reason = %q", decoded.HookSpecificOutput.PermissionDecisionReason)
				}
			},
		},
		{
			harness: "codex",
			payload: `{"hook_event_name":"PreToolUse","tool_name":"apply_patch","tool_input":{"input":"*** Begin Patch\n*** Update File: pkg/thing_test.go\n*** End Patch\n"},"cwd":"` + h.repository + `","turn_id":"t1"}`,
			assert: func(t *testing.T, code int, stdout, stderr string) {
				var decoded struct {
					Decision string `json:"decision"`
					Reason   string `json:"reason"`
				}
				if err := json.Unmarshal([]byte(stdout), &decoded); err != nil {
					t.Fatalf("decode %q: %v", stdout, err)
				}
				if decoded.Decision != "block" || !strings.Contains(decoded.Reason, "sealed") {
					t.Fatalf("codex decision = %+v", decoded)
				}
			},
		},
		{
			harness: "agy",
			payload: `{"toolCall":{"name":"replace_file_content","args":{"TargetFile":"pkg/thing_test.go"}},"workspacePaths":["` + h.repository + `"],"conversationId":"c1"}`,
			assert: func(t *testing.T, code int, stdout, stderr string) {
				var decoded struct {
					Decision string `json:"decision"`
					Reason   string `json:"reason"`
				}
				if err := json.Unmarshal([]byte(stdout), &decoded); err != nil {
					t.Fatalf("decode %q: %v", stdout, err)
				}
				if decoded.Decision != "deny" || !strings.Contains(decoded.Reason, "sealed") {
					t.Fatalf("agy decision = %+v", decoded)
				}
			},
		},
	}
	for _, testCase := range cases {
		t.Run(testCase.harness, func(t *testing.T) {
			code, stdout, stderr := h.runStdin(testCase.payload, "hook", "--harness", testCase.harness, "--event", "PreToolUse")
			testCase.assert(t, code, stdout, stderr)
		})
	}
}

func TestPreToolUseAllowsUnsealedPaths(t *testing.T) {
	h := newHarness(t)
	h.seal()
	payload := `{"hook_event_name":"PreToolUse","tool_name":"Write","tool_input":{"file_path":"pkg/thing.go"},"cwd":"` + h.repository + `"}`
	code, stdout, stderr := h.runStdin(payload, "hook", "--harness", "claude", "--event", "PreToolUse")
	if code != 0 || stdout != "" || stderr != "" {
		t.Fatalf("exit %d stdout %q stderr %q", code, stdout, stderr)
	}
}

func TestPostToolUseShellReportsChangedSealedTests(t *testing.T) {
	h := newHarness(t)
	h.seal()
	payload := `{"hook_event_name":"PostToolUse","tool_name":"Bash","tool_input":{"command":"sed -i s/x/y/ pkg/thing_test.go"},"cwd":"` + h.repository + `"}`
	if code, _, stderr := h.runStdin(payload, "hook", "--harness", "claude", "--event", "PostToolUse"); code != 0 || stderr != "" {
		t.Fatalf("unchanged tests reported: exit %d stderr %q", code, stderr)
	}
	h.write("pkg/thing_test.go", "package pkg\n\n// rewritten\n")
	code, stdout, stderr := h.runStdin(payload, "hook", "--harness", "claude", "--event", "PostToolUse")
	if code != 2 {
		t.Fatalf("changed sealed tests exit %d, want the advisory message code", code)
	}
	if stdout != "" || !strings.Contains(stderr, "pkg/thing_test.go") {
		t.Fatalf("stdout %q stderr %q", stdout, stderr)
	}
}

func TestStopRefusesUntilTheContractIsSatisfied(t *testing.T) {
	h := newHarness(t)
	h.seal()
	stopPayload := `{"hook_event_name":"Stop","cwd":"` + h.repository + `"}`

	code, _, stderr := h.runStdin(stopPayload, "hook", "--harness", "claude", "--event", "Stop")
	if code != 2 || !strings.Contains(stderr, "green") {
		t.Fatalf("missing green evidence: exit %d stderr %q", code, stderr)
	}

	if code, _, stderr := h.run("verify", "--green-command", "true"); code != 0 {
		t.Fatalf("verify exit %d: %s", code, stderr)
	}
	code, _, stderr = h.runStdin(stopPayload, "hook", "--harness", "claude", "--event", "Stop")
	if code != 2 || !strings.Contains(stderr, "diff review") {
		t.Fatalf("missing diff review: exit %d stderr %q", code, stderr)
	}

	h.write("findings.txt", "reviewed\n")
	if code, _, stderr := h.run("diff-review", "record", "--findings", "findings.txt"); code != 0 {
		t.Fatalf("diff-review exit %d: %s", code, stderr)
	}
	if code, stdout, stderr := h.runStdin(stopPayload, "hook", "--harness", "claude", "--event", "Stop"); code != 0 || stdout != "" || stderr != "" {
		t.Fatalf("satisfied contract still refused: exit %d stdout %q stderr %q", code, stdout, stderr)
	}

	h.write("pkg/thing_test.go", "package pkg\n\n// changed after sealing\n")
	code, _, stderr = h.runStdin(stopPayload, "hook", "--harness", "claude", "--event", "Stop")
	if code != 2 || !strings.Contains(stderr, "sealed") {
		t.Fatalf("changed sealed test: exit %d stderr %q", code, stderr)
	}
}

func TestStopDialectsMatchEachHarness(t *testing.T) {
	h := newHarness(t)
	h.seal()
	codexCode, codexOut, _ := h.runStdin(`{"hook_event_name":"Stop","cwd":"`+h.repository+`"}`, "hook", "--harness", "codex", "--event", "Stop")
	var codex struct {
		Continue *bool  `json:"continue"`
		Reason   string `json:"reason"`
	}
	if err := json.Unmarshal([]byte(codexOut), &codex); err != nil {
		t.Fatalf("decode %q: %v", codexOut, err)
	}
	if codexCode != 0 || codex.Continue == nil || *codex.Continue || codex.Reason == "" {
		t.Fatalf("codex stop = exit %d %+v", codexCode, codex)
	}

	agyCode, agyOut, _ := h.runStdin(`{"terminationReason":"idle","fullyIdle":true,"workspacePaths":["`+h.repository+`"]}`, "hook", "--harness", "agy", "--event", "Stop")
	var agy struct {
		Decision string `json:"decision"`
		Reason   string `json:"reason"`
	}
	if err := json.Unmarshal([]byte(agyOut), &agy); err != nil {
		t.Fatalf("decode %q: %v", agyOut, err)
	}
	if agyCode != 0 || agy.Decision != "continue" || agy.Reason == "" {
		t.Fatalf("agy stop = exit %d %+v", agyCode, agy)
	}
}

func TestSubagentStopUsesTheStopGate(t *testing.T) {
	h := newHarness(t)
	h.seal()
	code, _, stderr := h.runStdin(`{"hook_event_name":"SubagentStop","cwd":"`+h.repository+`"}`, "hook", "--harness", "claude", "--event", "SubagentStop")
	if code != 2 || !strings.Contains(stderr, "green") {
		t.Fatalf("exit %d stderr %q", code, stderr)
	}
}

func TestStatusReportsUnsealedRepositories(t *testing.T) {
	h := newHarness(t)
	status := h.status()
	if status.Sealed || status.Seal != nil || status.Repository != h.repository {
		t.Fatalf("status = %+v", status)
	}
	if status.APIVersion != APIVersion {
		t.Fatalf("apiVersion = %q", status.APIVersion)
	}
}

func TestStateDirectoryIsPerRepositoryAndOverridable(t *testing.T) {
	base := t.TempDir()
	t.Setenv(StateEnv, base)
	first, err := StateDirectory("/repositories/alpha")
	if err != nil {
		t.Fatal(err)
	}
	second, err := StateDirectory("/repositories/beta")
	if err != nil {
		t.Fatal(err)
	}
	if first == second || filepath.Dir(first) != base || filepath.Dir(second) != base {
		t.Fatalf("state directories %q and %q are not distinct children of %q", first, second, base)
	}
	if again, err := StateDirectory("/repositories/alpha"); err != nil || again != first {
		t.Fatalf("state directory is not stable: %q %q %v", again, first, err)
	}
}

func TestMatchTestPattern(t *testing.T) {
	cases := []struct {
		pattern string
		path    string
		want    bool
	}{
		{"**/*_test.go", "pkg/thing_test.go", true},
		{"**/*_test.go", "thing_test.go", true},
		{"**/*_test.go", "pkg/deep/thing_test.go", true},
		{"**/*_test.go", "pkg/thing.go", false},
		{"**/tests/**", "app/tests/unit/case.py", true},
		{"**/tests/**", "app/tests", false},
		{"**/testdata/**", "runplane/testdata/state/v3.json", true},
		{"pkg/thing_test.go", "pkg/thing_test.go", true},
		{"pkg/thing_test.go", "other/pkg/thing_test.go", false},
		{"**/*.spec.*", "web/src/app.spec.ts", true},
		{"**/test_*.py", "svc/test_api.py", true},
	}
	for _, testCase := range cases {
		if got := matchTestPattern(testCase.pattern, testCase.path); got != testCase.want {
			t.Errorf("matchTestPattern(%q, %q) = %v, want %v", testCase.pattern, testCase.path, got, testCase.want)
		}
	}
}

func TestResealRecordsADeletedSealedTest(t *testing.T) {
	h := newHarness(t)
	h.write("pkg/obsolete_test.go", "package pkg\n")
	h.commit("add a second test")
	h.seal()
	if len(h.readSeal().Tests) != 2 {
		t.Fatalf("expected both tests sealed: %+v", h.readSeal().Tests)
	}
	if err := os.Remove(filepath.Join(h.repository, "pkg", "obsolete_test.go")); err != nil {
		t.Fatal(err)
	}
	if code, _, stderr := h.run("reseal", "--reason", "the case is obsolete"); code != 0 {
		t.Fatalf("reseal exit %d: %s", code, stderr)
	}
	seal := h.readSeal()
	if len(seal.Tests) != 1 || seal.Tests[0].Path != "pkg/thing_test.go" {
		t.Fatalf("deleted test was not dropped: %+v", seal.Tests)
	}
	amendment := seal.Amendments[0]
	if len(amendment.Before) != 2 || len(amendment.After) != 1 {
		t.Fatalf("amendment does not record the removal: %+v", amendment)
	}
	if status := h.status(); len(status.ChangedTests) != 0 {
		t.Fatalf("resealed state still reports drift: %+v", status.ChangedTests)
	}
}
