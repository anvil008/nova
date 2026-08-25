package runplane

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func sampleGoalRequest(goalID string) GoalRequest {
	return GoalRequest{
		GoalID: goalID, Action: GoalCheckpointAction,
		Checkpoint: &GoalCheckpoint{
			Objective:   "close the three Phase 1 review findings",
			Constraints: []string{"no commit", "no service start"},
			Decisions:   []string{"seal lookup keys on the edit target"},
			Evidence:    []string{"go test -race ./... exit 0"},
			Runnable:    []string{"render the definitions"},
			Blocked:     []string{},
			Delegates:   []GoalDelegate{{DispatchID: "dispatch-1", RoleID: "workflow-executor", OwnedFiles: []string{"guard"}}},
			NextAction:  "run the offline conformance suite",
		},
		Plan: "# plan\n\n1. guard\n2. control plane\n3. goal verb\n",
	}
}

// The checkpoint directive is only executable if the goal verb writes the files
// itself, with no HTTP service anywhere in the path.
func TestGoalCheckpointPersistsWithoutTheService(t *testing.T) {
	stateDir := t.TempDir()
	record, err := ApplyGoal(stateDir, sampleGoalRequest("goal-phase-1-repair"))
	if err != nil {
		t.Fatal(err)
	}
	directory := filepath.Join(stateDir, "goals", "goal-phase-1-repair")
	if record.Directory != directory {
		t.Fatalf("record directory %q, want %q", record.Directory, directory)
	}
	raw, err := os.ReadFile(filepath.Join(directory, "checkpoint.json"))
	if err != nil {
		t.Fatal(err)
	}
	var stored GoalCheckpoint
	if err := json.Unmarshal(raw, &stored); err != nil {
		t.Fatal(err)
	}
	if stored.GoalID != "goal-phase-1-repair" || stored.NextAction == "" || stored.UpdatedAt == "" {
		t.Fatalf("stored checkpoint = %+v", stored)
	}
	plan, err := os.ReadFile(filepath.Join(directory, "plan.md"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.HasPrefix(string(plan), "# plan") {
		t.Fatalf("plan.md = %q", plan)
	}

	shown, err := ApplyGoal(stateDir, GoalRequest{GoalID: "goal-phase-1-repair", Action: GoalShowAction})
	if err != nil {
		t.Fatal(err)
	}
	if shown.Checkpoint == nil || shown.Checkpoint.Objective != stored.Objective || shown.Plan != string(plan) {
		t.Fatalf("shown record = %+v", shown)
	}
}

func TestGoalRejectsUnsafeIdentifiersAndIncompleteCheckpoints(t *testing.T) {
	stateDir := t.TempDir()
	for _, goalID := range []string{"", "..", "../escape", "goal/../escape", "goal id", strings.Repeat("g", 200)} {
		request := sampleGoalRequest(goalID)
		if _, err := ApplyGoal(stateDir, request); err == nil {
			t.Errorf("goalId %q was accepted", goalID)
		}
	}
	missingPlan := sampleGoalRequest("goal-1")
	missingPlan.Plan = ""
	if _, err := ApplyGoal(stateDir, missingPlan); err == nil {
		t.Error("a checkpoint without the short plan was accepted")
	}
	missingCheckpoint := sampleGoalRequest("goal-1")
	missingCheckpoint.Checkpoint = nil
	if _, err := ApplyGoal(stateDir, missingCheckpoint); err == nil {
		t.Error("a checkpoint action without a checkpoint was accepted")
	}
	if _, err := ApplyGoal(stateDir, GoalRequest{GoalID: "goal-absent", Action: GoalShowAction}); err == nil {
		t.Error("show invented a goal that was never checkpointed")
	}
}

// The MCP tool is one of the two surfaces the orchestrator has; the goal verb
// must work there without the loopback client being reachable.
func TestGoalLifecycleOperationNeedsNoRunningService(t *testing.T) {
	stateDir := t.TempDir()
	request := sampleGoalRequest("goal-mcp")
	output, err := executeLifecycle(context.Background(), &Client{}, stateDir, LifecycleInput{Operation: OperationGoal, Goal: &request})
	if err != nil {
		t.Fatal(err)
	}
	if output.Goal == nil || output.Goal.Checkpoint == nil {
		t.Fatalf("lifecycle goal output = %+v", output)
	}
	show := GoalRequest{GoalID: "goal-mcp", Action: GoalShowAction}
	output, err = executeLifecycle(context.Background(), &Client{}, stateDir, LifecycleInput{Operation: OperationGoal, Goal: &show})
	if err != nil {
		t.Fatal(err)
	}
	if output.Goal == nil || output.Goal.Plan == "" {
		t.Fatalf("lifecycle show output = %+v", output)
	}
	if _, err := executeLifecycle(context.Background(), &Client{}, stateDir, LifecycleInput{Operation: OperationGoal}); err == nil {
		t.Fatal("the goal operation accepted a missing goal envelope")
	}
	if _, err := executeLifecycle(context.Background(), &Client{}, stateDir, LifecycleInput{Operation: OperationHealth, Goal: &show}); err == nil {
		t.Fatal("a goal envelope was accepted on an unrelated operation")
	}
}

// The tool description and the operation set are what the orchestrator reads;
// they may not disagree about which verbs exist.
func TestLifecycleOperationSetIncludesGoal(t *testing.T) {
	found := false
	for _, operation := range lifecycleOperations {
		if operation == OperationGoal {
			found = true
		}
	}
	if !found {
		t.Fatal("the lifecycle operation set has no goal verb")
	}
	if !strings.Contains(MCPToolDescription, "goal") {
		t.Fatalf("tool description %q does not name the goal verb", MCPToolDescription)
	}
}
