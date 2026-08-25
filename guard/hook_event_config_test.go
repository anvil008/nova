package guard

import (
	"encoding/json"
	"path/filepath"
	"strings"
	"testing"
)

func TestHookEventUnsealed(t *testing.T) {
	h := newHarness(t)
	// Unsealed repository: missing --event must write to stderr, exit 0, and leave stdout empty.
	for _, harness := range []string{"claude", "codex", "agy"} {
		t.Run("missing_event/"+harness, func(t *testing.T) {
			code, stdout, stderr := h.run("hook", "--harness", harness)
			if code != 0 {
				t.Fatalf("exit code = %d, want 0", code)
			}
			if strings.TrimSpace(stdout) != "" {
				t.Fatalf("stdout = %q, want empty", stdout)
			}
			if !strings.Contains(stderr, "anvil-guard hook misconfigured: --event") {
				t.Fatalf("stderr = %q, want containing 'anvil-guard hook misconfigured: --event'", stderr)
			}
		})

		t.Run("unknown_event/"+harness, func(t *testing.T) {
			code, stdout, stderr := h.run("hook", "--harness", harness, "--event", "BogusEvent")
			if code != 0 {
				t.Fatalf("exit code = %d, want 0", code)
			}
			if strings.TrimSpace(stdout) != "" {
				t.Fatalf("stdout = %q, want empty", stdout)
			}
			if !strings.Contains(stderr, "anvil-guard hook misconfigured: --event") {
				t.Fatalf("stderr = %q, want containing 'anvil-guard hook misconfigured: --event'", stderr)
			}
		})

		for _, validEvent := range []string{"PreToolUse", "PostToolUse", "Stop", "SubagentStop"} {
			t.Run("valid_event/"+harness+"/"+validEvent, func(t *testing.T) {
				code, stdout, stderr := h.run("hook", "--harness", harness, "--event", validEvent)
				if code != 0 {
					t.Fatalf("exit code = %d, want 0", code)
				}
				if strings.TrimSpace(stdout) != "" {
					t.Fatalf("stdout = %q, want empty", stdout)
				}
				if strings.TrimSpace(stderr) != "" {
					t.Fatalf("stderr = %q, want empty", stderr)
				}
			})
		}
	}
}

func TestHookEventSealed(t *testing.T) {
	h := newHarness(t)
	h.seal()

	for _, harness := range []string{"claude", "codex", "agy"} {
		t.Run("missing_event_sealed/"+harness, func(t *testing.T) {
			payload := `{"hook_event_name":"PreToolUse","cwd":"` + h.repository + `","session_id":"s-1"}`
			code, stdout, _ := h.runStdin(payload, "hook", "--harness", harness)
			switch harness {
			case "claude":
				if code != 0 {
					t.Fatalf("exit code = %d, want 0", code)
				}
				var decoded map[string]any
				if err := json.Unmarshal([]byte(stdout), &decoded); err != nil {
					t.Fatalf("decode stdout %q: %v", stdout, err)
				}
				inner := decoded["hookSpecificOutput"].(map[string]any)
				if inner["permissionDecision"] != "deny" {
					t.Fatalf("decision = %v, want deny", inner["permissionDecision"])
				}
				reason := inner["permissionDecisionReason"].(string)
				if !strings.HasPrefix(reason, "anvil-guard hook misconfigured: --event") {
					t.Fatalf("reason = %q, want prefix 'anvil-guard hook misconfigured: --event'", reason)
				}
			case "codex":
				if code != 0 {
					t.Fatalf("exit code = %d, want 0", code)
				}
				var decoded map[string]any
				if err := json.Unmarshal([]byte(stdout), &decoded); err != nil {
					t.Fatalf("decode stdout %q: %v", stdout, err)
				}
				if decoded["decision"] != "block" {
					t.Fatalf("decision = %v, want block", decoded["decision"])
				}
				reason := decoded["reason"].(string)
				if !strings.HasPrefix(reason, "anvil-guard hook misconfigured: --event") {
					t.Fatalf("reason = %q, want prefix 'anvil-guard hook misconfigured: --event'", reason)
				}
			case "agy":
				if code != 0 {
					t.Fatalf("exit code = %d, want 0", code)
				}
				var decoded map[string]any
				if err := json.Unmarshal([]byte(stdout), &decoded); err != nil {
					t.Fatalf("decode stdout %q: %v", stdout, err)
				}
				if decoded["decision"] != "deny" {
					t.Fatalf("decision = %v, want deny", decoded["decision"])
				}
				reason := decoded["reason"].(string)
				if !strings.HasPrefix(reason, "anvil-guard hook misconfigured: --event") {
					t.Fatalf("reason = %q, want prefix 'anvil-guard hook misconfigured: --event'", reason)
				}
			}
		})

		t.Run("unknown_event_sealed/"+harness, func(t *testing.T) {
			payload := `{"hook_event_name":"PreToolUse","cwd":"` + h.repository + `","session_id":"s-1"}`
			code, stdout, _ := h.runStdin(payload, "hook", "--harness", harness, "--event", "UnknownEvent")
			switch harness {
			case "claude":
				if code != 0 {
					t.Fatalf("exit code = %d, want 0", code)
				}
				var decoded map[string]any
				if err := json.Unmarshal([]byte(stdout), &decoded); err != nil {
					t.Fatalf("decode stdout %q: %v", stdout, err)
				}
				inner := decoded["hookSpecificOutput"].(map[string]any)
				if inner["permissionDecision"] != "deny" {
					t.Fatalf("decision = %v, want deny", inner["permissionDecision"])
				}
				reason := inner["permissionDecisionReason"].(string)
				if !strings.HasPrefix(reason, "anvil-guard hook misconfigured: --event") {
					t.Fatalf("reason = %q, want prefix 'anvil-guard hook misconfigured: --event'", reason)
				}
			case "codex":
				if code != 0 {
					t.Fatalf("exit code = %d, want 0", code)
				}
				var decoded map[string]any
				if err := json.Unmarshal([]byte(stdout), &decoded); err != nil {
					t.Fatalf("decode stdout %q: %v", stdout, err)
				}
				if decoded["decision"] != "block" {
					t.Fatalf("decision = %v, want block", decoded["decision"])
				}
				reason := decoded["reason"].(string)
				if !strings.HasPrefix(reason, "anvil-guard hook misconfigured: --event") {
					t.Fatalf("reason = %q, want prefix 'anvil-guard hook misconfigured: --event'", reason)
				}
			case "agy":
				if code != 0 {
					t.Fatalf("exit code = %d, want 0", code)
				}
				var decoded map[string]any
				if err := json.Unmarshal([]byte(stdout), &decoded); err != nil {
					t.Fatalf("decode stdout %q: %v", stdout, err)
				}
				if decoded["decision"] != "deny" {
					t.Fatalf("decision = %v, want deny", decoded["decision"])
				}
				reason := decoded["reason"].(string)
				if !strings.HasPrefix(reason, "anvil-guard hook misconfigured: --event") {
					t.Fatalf("reason = %q, want prefix 'anvil-guard hook misconfigured: --event'", reason)
				}
			}
		})

		for _, validEvent := range []string{"PreToolUse", "PostToolUse", "Stop", "SubagentStop"} {
			t.Run("valid_event_sealed/"+harness+"/"+validEvent, func(t *testing.T) {
				var payload string
				switch validEvent {
				case "PreToolUse":
					// Edit of non-sealed file should be allowed.
					payload = `{"hook_event_name":"PreToolUse","tool_name":"Edit","tool_input":{"file_path":"pkg/thing.go"},"cwd":"` + h.repository + `","session_id":"s-1"}`
				case "PostToolUse":
					payload = `{"hook_event_name":"PostToolUse","tool_name":"Bash","cwd":"` + h.repository + `","session_id":"s-1"}`
				case "Stop", "SubagentStop":
					// Stop with active seal without green should refuse.
					payload = `{"hook_event_name":"` + validEvent + `","cwd":"` + h.repository + `","session_id":"s-1"}`
				}
				code, stdout, stderr := h.runStdin(payload, "hook", "--harness", harness, "--event", validEvent)
				if validEvent == "Stop" || validEvent == "SubagentStop" {
					// Should refuse stop because no green evidence
					if harness == "claude" {
						if code != 2 || !strings.Contains(stderr, "anvil-guard:") {
							t.Fatalf("claude stop refusal exit=%d stderr=%q", code, stderr)
						}
					} else if harness == "codex" {
						var decoded map[string]any
						_ = json.Unmarshal([]byte(stdout), &decoded)
						if decoded["continue"] != false {
							t.Fatalf("codex stop refusal stdout=%q", stdout)
						}
					} else if harness == "agy" {
						var decoded map[string]any
						_ = json.Unmarshal([]byte(stdout), &decoded)
						if decoded["decision"] != "continue" {
							t.Fatalf("agy stop refusal stdout=%q", stdout)
						}
					}
				} else {
					// PreToolUse on allowed file and PostToolUse without test changes should pass
					if code != 0 {
						t.Fatalf("exit code = %d, want 0 (stderr %q)", code, stderr)
					}
				}
			})
		}
	}
}

func TestHookEventTargetRepositorySealedFromOutsideCwd(t *testing.T) {
	h := newHarness(t)
	h.seal()
	outside := t.TempDir()

	// Tool call from outside cwd targeting sealed repo with missing --event:
	payload := `{"hook_event_name":"PreToolUse","tool_name":"Edit","tool_input":{"file_path":"` + filepath.Join(h.repository, "pkg/thing.go") + `"},"cwd":"` + outside + `","session_id":"s-outside"}`
	code, stdout, _ := h.runStdin(payload, "hook", "--harness", "claude")
	if code != 0 {
		t.Fatalf("exit code = %d, want 0", code)
	}
	var decoded map[string]any
	if err := json.Unmarshal([]byte(stdout), &decoded); err != nil {
		t.Fatalf("decode stdout %q: %v", stdout, err)
	}
	inner := decoded["hookSpecificOutput"].(map[string]any)
	if inner["permissionDecision"] != "deny" {
		t.Fatalf("decision = %v, want deny", inner["permissionDecision"])
	}
	reason := inner["permissionDecisionReason"].(string)
	if !strings.HasPrefix(reason, "anvil-guard hook misconfigured: --event") {
		t.Fatalf("reason = %q, want prefix 'anvil-guard hook misconfigured: --event'", reason)
	}
}
