package codingfleet

import (
	"strings"
	"testing"
)

// R1: the routing block is loaded into every session and is the sanctioned
// fallback when a harness cannot load a generated definition, so an enumeration
// that omits `goal` teaches the orchestrator that the verb does not exist -- and
// leaves "binds and checkpoints the goal" with no mechanism at all.
func TestGlobalRoutingBlockNamesTheGoalCheckpointMechanism(t *testing.T) {
	block := string(globalCodingRoutingBlock)
	assertContains(t, block,
		"`goal`",
		"swarm_runplane_lifecycle",
		"~/.local/state/swarm-runplane/goals/<goalId>/",
		"never through a file tool",
	)
	if strings.Contains(block, "Supported lifecycle commands are") {
		t.Error("the routing block still enumerates the lifecycle without the goal verb")
	}
}

// R2: Phase 1 item 4 moved the run-plane CLI reference out of the orchestrator
// prompt; render_test pins its absence from the rendered definition. The same
// strings were still injected into every session through the global block, so
// the two surfaces contradicted each other and the prompt-bloat fix was undone
// at install time.
func TestGlobalRoutingBlockDoesNotCarryTheRunplaneCLIReference(t *testing.T) {
	block := string(globalCodingRoutingBlock)
	assertNotContains(t, block,
		"swarm-runplane serve", "http://127.0.0.1:8083", "auth.token",
		"SWARM_RUNPLANE_STATE", "SWARM_RUNPLANE_URL", "SWARM_RUNPLANE_TOKEN", "SWARM_RUNPLANE_TOKEN_FILE",
		"events --after N JOB_ID", "send JOB_ID", "resume JOB_ID", "cancel JOB_ID", "evidence JOB_ID")
	// The two bootstrap commands and the request-file rule stay inline, exactly
	// as the rendered orchestrator keeps them.
	assertContains(t, block,
		"/home/anvil/.local/bin/swarm-runplane health",
		"/home/anvil/.local/bin/swarm-runplane capabilities",
		"/home/anvil/.local/bin/swarm-runplane start --request route.json",
		"/home/anvil/.local/share/anvil-coding-fleet/swarm-runplane-foreign-dispatch.md",
	)
}
