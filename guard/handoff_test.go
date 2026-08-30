package guard

import (
	"fmt"
	"strings"
	"testing"
)

// stopPayload is the minimal Stop hook envelope; the gate resolves the
// repository from `cwd` exactly as a harness would send it.
func (h *harness) stopPayload() string {
	return fmt.Sprintf(`{"session_id":"handoff","cwd":%q,"hook_event_name":"Stop"}`, h.repository)
}

func (h *harness) stop() (int, string, string) {
	h.t.Helper()
	return h.runStdin(h.stopPayload(), "hook", "--harness", "claude", "--event", "Stop")
}

// The Stop gate is written for an implementer. A test-author legitimately stops
// with a seal and no GREEN, so without a handoff it would deadlock: nothing it
// is allowed to do could ever satisfy the gate.
func TestHandoffLetsTheSealingAgentStopWithoutGreen(t *testing.T) {
	h := newHarness(t)
	h.seal()

	code, _, stderr := h.stop()
	if code == 0 {
		t.Fatal("Stop allowed a sealed state with no green and no handoff")
	}
	if !strings.Contains(stderr, "no green evidence") {
		t.Fatalf("stop reason = %q", stderr)
	}

	if code, _, stderr := h.run("handoff", "--to", "builder"); code != 0 {
		t.Fatalf("handoff exit %d: %s", code, stderr)
	}
	if code, _, stderr := h.stop(); code != 0 {
		t.Fatalf("Stop still blocked after handoff: %d %s", code, stderr)
	}
}

// A handoff relaxes the Stop gate only. Readiness is the merge gate, and it must
// stay unsatisfied until the implementation actually exists -- otherwise the
// handoff would be a way to merge untested work.
func TestHandoffNeverMakesTheChangeReady(t *testing.T) {
	h := newHarness(t)
	h.seal()
	if code, _, stderr := h.run("handoff", "--to", "builder"); code != 0 {
		t.Fatalf("handoff exit %d: %s", code, stderr)
	}

	status := h.status()
	if status.Ready {
		t.Fatal("handoff satisfied the merge gate")
	}
	if status.Handoff == nil || status.Handoff.To != "builder" {
		t.Fatalf("handoff not surfaced in status: %+v", status.Handoff)
	}
	if status.Handoff.HandedOffAt == "" {
		t.Fatal("handoff recorded no timestamp")
	}
}

func TestHandoffRefusesWithoutASealOrAfterGreen(t *testing.T) {
	h := newHarness(t)
	if code, _, stderr := h.run("handoff", "--to", "builder"); code == 0 {
		t.Fatal("handoff accepted an unsealed repository")
	} else if !strings.Contains(stderr, "seal the tests first") {
		t.Fatalf("reason = %q", stderr)
	}

	h.seal()
	h.verify()
	if code, _, stderr := h.run("handoff", "--to", "builder"); code == 0 {
		t.Fatal("handoff accepted a state that already has green evidence")
	} else if !strings.Contains(stderr, "nothing to hand off") {
		t.Fatalf("reason = %q", stderr)
	}
}

// Handing off a test that no longer matches its seal would park a broken
// Definition of Done on the next agent.
func TestHandoffRefusesWhenSealedTestsChanged(t *testing.T) {
	h := newHarness(t)
	h.seal()
	h.write("pkg/thing_test.go", "package pkg\n\n// drifted\nfunc TestThing(t *testing.T) {}\n")

	code, _, stderr := h.run("handoff", "--to", "builder")
	if code == 0 {
		t.Fatal("handoff accepted drifted sealed tests")
	}
	if !strings.Contains(stderr, "sealed tests changed") {
		t.Fatalf("reason = %q", stderr)
	}
}

// A drifted seal still blocks Stop even once a handoff is on record: the
// relaxation covers the missing implementation, never a tampered test.
func TestHandoffDoesNotExcuseLaterTestDrift(t *testing.T) {
	h := newHarness(t)
	h.seal()
	if code, _, stderr := h.run("handoff", "--to", "builder"); code != 0 {
		t.Fatalf("handoff exit %d: %s", code, stderr)
	}
	h.write("pkg/thing_test.go", "package pkg\n\n// drifted after the handoff\n")

	code, _, stderr := h.stop()
	if code == 0 {
		t.Fatal("Stop allowed a handed-off state whose sealed tests drifted")
	}
	if !strings.Contains(stderr, "sealed tests changed") {
		t.Fatalf("stop reason = %q", stderr)
	}
}

// The relaxation must not leak past the agent that recorded it. Without this the
// test-author's handoff would sit in the state and let the *builder* stop having
// implemented nothing, disabling the Stop gate for the whole issue.
func TestHandoffDoesNotCoverTheNextAgentsWork(t *testing.T) {
	h := newHarness(t)
	h.seal()
	if code, _, stderr := h.run("handoff", "--to", "builder"); code != 0 {
		t.Fatalf("handoff exit %d: %s", code, stderr)
	}
	// The sealing agent stops on the tree it handed over: allowed.
	if code, _, stderr := h.stop(); code != 0 {
		t.Fatalf("Stop blocked the handing-off agent: %d %s", code, stderr)
	}

	// The next agent writes an implementation and tries to stop without GREEN.
	h.write("pkg/thing.go", "package pkg\n\nfunc Thing() int { return 1 }\n")
	code, _, stderr := h.stop()
	if code == 0 {
		t.Fatal("Stop allowed an implementer to coast on someone else's handoff")
	}
	if !strings.Contains(stderr, "no green evidence") {
		t.Fatalf("stop reason = %q", stderr)
	}
}

// Sealing again starts a fresh cycle, so a stale handoff must not carry over
// into it and silently excuse the next agent's missing GREEN.
func TestResealClearsAPriorHandoff(t *testing.T) {
	h := newHarness(t)
	h.seal()
	if code, _, stderr := h.run("handoff", "--to", "builder"); code != 0 {
		t.Fatalf("handoff exit %d: %s", code, stderr)
	}
	h.seal()

	if status := h.status(); status.Handoff != nil {
		t.Fatalf("handoff survived a new seal: %+v", status.Handoff)
	}
	if code, _, stderr := h.stop(); code == 0 {
		t.Fatalf("Stop allowed a re-sealed state on a stale handoff: %s", stderr)
	}
}
