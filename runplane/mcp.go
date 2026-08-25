package runplane

import (
	"context"
	"errors"
	"fmt"

	"path/filepath"

	"github.com/google/jsonschema-go/jsonschema"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

const MCPToolName = "swarm_runplane_lifecycle"

type LifecycleOperation string

const (
	OperationHealth       LifecycleOperation = "health"
	OperationCapabilities LifecycleOperation = "capabilities"
	OperationStart        LifecycleOperation = "start"
	OperationList         LifecycleOperation = "list"
	OperationStatus       LifecycleOperation = "status"
	OperationEvents       LifecycleOperation = "events"
	OperationSend         LifecycleOperation = "send"
	OperationResume       LifecycleOperation = "resume"
	OperationCancel       LifecycleOperation = "cancel"
	OperationEvidence     LifecycleOperation = "evidence"
	// OperationGoal implements the orchestrator's existing `goal` authority. It
	// is served from local state, so it works with no service running.
	OperationGoal LifecycleOperation = "goal"
)

// MCPToolDescription must enumerate exactly the operations the enum carries;
// an orchestrator that reads one and calls the other has no way to recover.
const MCPToolDescription = "Operate the authenticated loopback Swarm supervisor through exactly health, capabilities, start, list, status, events, send, resume, cancel, evidence, or goal. The goal operation reads and writes the durable goal record on local disk and needs no running service; this tool cannot execute commands or select arbitrary URLs."

var lifecycleOperations = []LifecycleOperation{
	OperationHealth,
	OperationCapabilities,
	OperationStart,
	OperationList,
	OperationStatus,
	OperationEvents,
	OperationSend,
	OperationResume,
	OperationCancel,
	OperationEvidence,
	OperationGoal,
}

// LifecycleInput is deliberately closed over the supervisor lifecycle. It has
// no command, executable, URL, path, environment, or arbitrary argument field.
type LifecycleInput struct {
	Operation LifecycleOperation `json:"operation" jsonschema:"one of the eleven bounded supervisor lifecycle operations"`
	JobID     string             `json:"jobId,omitempty" jsonschema:"the exact supervisor job identifier for job-scoped operations"`
	After     uint64             `json:"after,omitempty" jsonschema:"the last event sequence already observed"`
	Start     *StartRequest      `json:"start,omitempty" jsonschema:"the complete fail-closed start admission envelope"`
	Message   string             `json:"message,omitempty" jsonschema:"a bounded message for a live job"`
	Brief     string             `json:"brief,omitempty" jsonschema:"a bounded continuation brief for a terminal job"`
	Goal      *GoalRequest       `json:"goal,omitempty" jsonschema:"the durable goal checkpoint or show envelope"`
}

type LifecycleOutput struct {
	Operation    LifecycleOperation `json:"operation"`
	Health       *Health            `json:"health,omitempty"`
	Capabilities []Capability       `json:"capabilities,omitempty"`
	Job          *Job               `json:"job,omitempty"`
	Jobs         []Job              `json:"jobs,omitempty"`
	Events       []Event            `json:"events,omitempty"`
	Evidence     *Evidence          `json:"evidence,omitempty"`
	Goal         *GoalRecord        `json:"goal,omitempty"`
	Accepted     bool               `json:"accepted,omitempty"`
}

// NewMCPServer exposes exactly one constrained tool backed by the authenticated
// loopback client. The typed SDK binding performs JSON Schema validation before
// the operation-specific validation below.
func NewMCPServer(client *Client, stateDir string) (*mcp.Server, error) {
	if client == nil {
		return nil, errors.New("run-plane client is required")
	}
	if stateDir == "" || !filepath.IsAbs(stateDir) {
		return nil, errors.New("an absolute run-plane state directory is required for the goal operation")
	}
	inputSchema, err := jsonschema.For[LifecycleInput](nil)
	if err != nil {
		return nil, fmt.Errorf("infer MCP lifecycle schema: %w", err)
	}
	operationSchema := inputSchema.Properties["operation"]
	if operationSchema == nil {
		return nil, errors.New("MCP lifecycle schema lacks operation property")
	}
	operationSchema.Enum = make([]any, len(lifecycleOperations))
	for index, operation := range lifecycleOperations {
		operationSchema.Enum[index] = string(operation)
	}
	if schema := inputSchema.Properties["jobId"]; schema != nil {
		maximum := 32
		schema.MinLength = &maximum
		schema.MaxLength = &maximum
		schema.Pattern = `^[a-f0-9]{32}$`
	}
	if schema := inputSchema.Properties["message"]; schema != nil {
		minimum, maximum := 1, maxMessageSize
		schema.MinLength, schema.MaxLength = &minimum, &maximum
	}
	if schema := inputSchema.Properties["brief"]; schema != nil {
		minimum, maximum := 1, maxBriefSize
		schema.MinLength, schema.MaxLength = &minimum, &maximum
	}

	server := mcp.NewServer(&mcp.Implementation{Name: "anvil-swarm-runplane", Version: APIVersion}, nil)
	mcp.AddTool(server, &mcp.Tool{
		Name:        MCPToolName,
		Description: MCPToolDescription,
		InputSchema: inputSchema,
	}, func(ctx context.Context, _ *mcp.CallToolRequest, input LifecycleInput) (*mcp.CallToolResult, LifecycleOutput, error) {
		output, err := executeLifecycle(ctx, client, stateDir, input)
		return nil, output, err
	})
	return server, nil
}

func executeLifecycle(ctx context.Context, client *Client, stateDir string, input LifecycleInput) (LifecycleOutput, error) {
	if err := validateLifecycleInput(input); err != nil {
		return LifecycleOutput{}, err
	}
	output := LifecycleOutput{Operation: input.Operation}
	switch input.Operation {
	case OperationHealth:
		value, err := client.Health(ctx)
		output.Health = &value
		return output, err
	case OperationCapabilities:
		value, err := client.Capabilities(ctx)
		output.Capabilities = value
		return output, err
	case OperationStart:
		value, err := client.Start(ctx, *input.Start)
		output.Job = &value
		return output, err
	case OperationList:
		value, err := client.List(ctx)
		output.Jobs = value
		return output, err
	case OperationStatus:
		value, err := client.Status(ctx, input.JobID)
		output.Job = &value
		return output, err
	case OperationEvents:
		value, err := client.Events(ctx, input.JobID, input.After)
		output.Events = value
		return output, err
	case OperationSend:
		err := client.Send(ctx, input.JobID, input.Message)
		output.Accepted = err == nil
		return output, err
	case OperationResume:
		value, err := client.Resume(ctx, input.JobID, input.Brief)
		output.Job = &value
		return output, err
	case OperationCancel:
		err := client.Cancel(ctx, input.JobID)
		output.Accepted = err == nil
		return output, err
	case OperationEvidence:
		value, err := client.Evidence(ctx, input.JobID)
		output.Evidence = &value
		return output, err
	case OperationGoal:
		value, err := ApplyGoal(stateDir, *input.Goal)
		if err != nil {
			return LifecycleOutput{}, err
		}
		output.Goal = &value
		return output, nil
	default:
		return LifecycleOutput{}, fmt.Errorf("unsupported lifecycle operation %q", input.Operation)
	}
}

func validateLifecycleInput(input LifecycleInput) error {
	valid := false
	for _, operation := range lifecycleOperations {
		if input.Operation == operation {
			valid = true
			break
		}
	}
	if !valid {
		return fmt.Errorf("unsupported lifecycle operation %q", input.Operation)
	}
	requiresJob := input.Operation == OperationStatus || input.Operation == OperationEvents || input.Operation == OperationSend || input.Operation == OperationResume || input.Operation == OperationCancel || input.Operation == OperationEvidence
	if requiresJob != (input.JobID != "") {
		if requiresJob {
			return errors.New("jobId is required for the selected operation")
		}
		return errors.New("jobId is forbidden for the selected operation")
	}
	if input.JobID != "" && !jobIDPattern.MatchString(input.JobID) {
		return errors.New("jobId must be exactly 32 lowercase hexadecimal characters")
	}
	if (input.Operation == OperationStart) != (input.Start != nil) {
		if input.Operation == OperationStart {
			return errors.New("start envelope is required for start")
		}
		return errors.New("start envelope is forbidden for the selected operation")
	}
	if (input.Operation == OperationSend) != (input.Message != "") {
		if input.Operation == OperationSend {
			return errors.New("message is required for send")
		}
		return errors.New("message is forbidden for the selected operation")
	}
	if len(input.Message) > maxMessageSize {
		return fmt.Errorf("message exceeds %d bytes", maxMessageSize)
	}
	if (input.Operation == OperationResume) != (input.Brief != "") {
		if input.Operation == OperationResume {
			return errors.New("brief is required for resume")
		}
		return errors.New("brief is forbidden for the selected operation")
	}
	if len(input.Brief) > maxBriefSize {
		return fmt.Errorf("brief exceeds %d bytes", maxBriefSize)
	}
	if (input.Operation == OperationGoal) != (input.Goal != nil) {
		if input.Operation == OperationGoal {
			return errors.New("goal envelope is required for goal")
		}
		return errors.New("goal envelope is forbidden for the selected operation")
	}
	if input.Operation != OperationEvents && input.After != 0 {
		return errors.New("after is allowed only for events")
	}
	return nil
}
