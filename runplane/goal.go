package runplane

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

// The durable goal record lives on disk, not in a conversation window. It is
// deliberately independent of the supervisor process: the orchestrator has no
// filesystem write authority and must be able to checkpoint whether or not the
// loopback service is running.
const (
	goalsDirectory     = "goals"
	goalCheckpointFile = "checkpoint.json"
	goalPlanFile       = "plan.md"

	maxGoalCheckpointBytes = 256 << 10
	maxGoalPlanBytes       = 64 << 10
)

// GoalAction is the bounded set of things the goal verb can do.
type GoalAction string

const (
	GoalCheckpointAction GoalAction = "checkpoint"
	GoalShowAction       GoalAction = "show"
)

// GoalDelegate is one live child and the files it owns, so a resumed
// orchestrator knows what is already claimed.
type GoalDelegate struct {
	DispatchID string   `json:"dispatchId"`
	RoleID     string   `json:"roleId"`
	OwnedFiles []string `json:"ownedFiles"`
}

// GoalCheckpoint is the system of record for a durable goal. Native session
// state is a cache of it.
type GoalCheckpoint struct {
	GoalID      string         `json:"goalId"`
	UpdatedAt   string         `json:"updatedAt"`
	Objective   string         `json:"objective"`
	Constraints []string       `json:"constraints"`
	Decisions   []string       `json:"decisions"`
	Evidence    []string       `json:"evidence"`
	Runnable    []string       `json:"runnable"`
	Blocked     []string       `json:"blocked"`
	Delegates   []GoalDelegate `json:"delegates"`
	NextAction  string         `json:"nextAction"`
}

// GoalRequest is one goal-verb invocation.
type GoalRequest struct {
	GoalID     string          `json:"goalId"`
	Action     GoalAction      `json:"action,omitempty" jsonschema:"checkpoint to persist the durable goal record, show to read it back"`
	Checkpoint *GoalCheckpoint `json:"checkpoint,omitempty" jsonschema:"the record to persist, required for checkpoint"`
	Plan       string          `json:"plan,omitempty" jsonschema:"the short plan.md body, required for checkpoint"`
}

// GoalRecord is what is on disk after the call.
type GoalRecord struct {
	GoalID     string          `json:"goalId"`
	Directory  string          `json:"directory"`
	Checkpoint *GoalCheckpoint `json:"checkpoint,omitempty"`
	Plan       string          `json:"plan,omitempty"`
}

// ApplyGoal persists or reads a durable goal record under stateDir. It touches
// nothing but that goal's own directory and never contacts the HTTP service.
func ApplyGoal(stateDir string, request GoalRequest) (GoalRecord, error) {
	if stateDir == "" || !filepath.IsAbs(stateDir) {
		return GoalRecord{}, fmt.Errorf("goal state directory %q must be absolute", stateDir)
	}
	// goalIDPattern is the admission-time identifier shape; it excludes path
	// separators and traversal, so the id can only name one directory directly
	// under the goals root.
	if !goalIDPattern.MatchString(request.GoalID) {
		return GoalRecord{}, fmt.Errorf("goalId %q must be a bounded identifier without separators", request.GoalID)
	}
	directory := filepath.Join(stateDir, goalsDirectory, request.GoalID)
	switch request.Action {
	case GoalCheckpointAction:
		return writeGoalCheckpoint(directory, request)
	case GoalShowAction:
		if request.Checkpoint != nil || request.Plan != "" {
			return GoalRecord{}, errors.New("show reads the goal record and takes no checkpoint or plan")
		}
		return readGoalCheckpoint(directory, request.GoalID)
	default:
		return GoalRecord{}, fmt.Errorf("goal action must be checkpoint or show, got %q", request.Action)
	}
}

func writeGoalCheckpoint(directory string, request GoalRequest) (GoalRecord, error) {
	if request.Checkpoint == nil {
		return GoalRecord{}, errors.New("checkpoint requires the goal record to persist")
	}
	if request.Plan == "" {
		return GoalRecord{}, errors.New("checkpoint requires the short plan.md body")
	}
	if len(request.Plan) > maxGoalPlanBytes {
		return GoalRecord{}, fmt.Errorf("plan exceeds %d bytes", maxGoalPlanBytes)
	}
	record := *request.Checkpoint
	if record.Objective == "" || record.NextAction == "" {
		return GoalRecord{}, errors.New("a checkpoint must record the objective and the exact next action")
	}
	record.GoalID = request.GoalID
	if record.UpdatedAt == "" {
		record.UpdatedAt = time.Now().UTC().Format(time.RFC3339Nano)
	}
	for _, collection := range []*[]string{&record.Constraints, &record.Decisions, &record.Evidence, &record.Runnable, &record.Blocked} {
		if *collection == nil {
			*collection = []string{}
		}
	}
	if record.Delegates == nil {
		record.Delegates = []GoalDelegate{}
	}
	encoded, err := json.MarshalIndent(record, "", "  ")
	if err != nil {
		return GoalRecord{}, err
	}
	if len(encoded) > maxGoalCheckpointBytes {
		return GoalRecord{}, fmt.Errorf("checkpoint exceeds %d bytes", maxGoalCheckpointBytes)
	}
	if err := os.MkdirAll(directory, 0o700); err != nil {
		return GoalRecord{}, err
	}
	if err := replaceFile(filepath.Join(directory, goalCheckpointFile), append(encoded, '\n')); err != nil {
		return GoalRecord{}, err
	}
	if err := replaceFile(filepath.Join(directory, goalPlanFile), []byte(request.Plan)); err != nil {
		return GoalRecord{}, err
	}
	return GoalRecord{GoalID: record.GoalID, Directory: directory, Checkpoint: &record, Plan: request.Plan}, nil
}

func readGoalCheckpoint(directory, goalID string) (GoalRecord, error) {
	raw, err := os.ReadFile(filepath.Join(directory, goalCheckpointFile))
	if err != nil {
		return GoalRecord{}, fmt.Errorf("read goal %q: %w", goalID, err)
	}
	var record GoalCheckpoint
	if err := json.Unmarshal(raw, &record); err != nil {
		return GoalRecord{}, fmt.Errorf("decode goal %q: %w", goalID, err)
	}
	plan, err := os.ReadFile(filepath.Join(directory, goalPlanFile))
	if err != nil {
		return GoalRecord{}, fmt.Errorf("read goal plan %q: %w", goalID, err)
	}
	return GoalRecord{GoalID: goalID, Directory: directory, Checkpoint: &record, Plan: string(plan)}, nil
}

// replaceFile writes atomically so a resumed orchestrator never reads half a
// checkpoint that was being rewritten when its predecessor was interrupted.
func replaceFile(pathname string, content []byte) error {
	temporary, err := os.CreateTemp(filepath.Dir(pathname), ".swarm-goal-*")
	if err != nil {
		return err
	}
	temporaryPath := temporary.Name()
	writeErr := errors.Join(temporary.Chmod(0o600), writeAndSync(temporary, content), temporary.Close())
	if writeErr != nil {
		_ = os.Remove(temporaryPath)
		return writeErr
	}
	if err := os.Rename(temporaryPath, pathname); err != nil {
		_ = os.Remove(temporaryPath)
		return err
	}
	return nil
}

func writeAndSync(file *os.File, content []byte) error {
	if _, err := file.Write(content); err != nil {
		return err
	}
	return file.Sync()
}
