package herdrbridge

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strconv"
	"time"
)

var presentationTokens = []string{"attempt", "model", "phase", "summary", "task", "taskRef"}

func presentationTokenValues(p Presentation) map[string]string {
	return map[string]string{
		"taskRef": p.TaskRef,
		"task":    p.Task,
		"phase":   p.Phase,
		"summary": p.Summary,
		"model":   p.Model,
		"attempt": p.Attempt,
	}
}

func presentationTitle(p Presentation) string {
	if p.TaskRef == "" {
		return p.Task
	}
	if p.Task == "" {
		return p.TaskRef
	}
	return p.TaskRef + " · " + p.Task
}

// ReportMetadata updates display-only data. It does not report agent state and
// therefore cannot establish or override pane lifecycle authority.
func (c *Client) ReportMetadata(ctx context.Context, locator Locator, update MetadataUpdate) error {
	if err := locator.validate(); err != nil {
		return err
	}
	if locator.WorkspaceID != c.config.WorkspaceID {
		return errors.New("pane is outside the configured herdr workspace")
	}
	validated, err := update.validate()
	if err != nil {
		return err
	}
	args := []string{"pane", "report-metadata", locator.PaneID, "--source", MetadataSource}
	if title := presentationTitle(validated.Presentation); title != "" {
		args = append(args, "--title", title)
	} else {
		args = append(args, "--clear-title")
	}
	if validated.Presentation.Model != "" {
		args = append(args, "--display-agent", validated.Presentation.Model)
	} else {
		args = append(args, "--clear-display-agent")
	}
	tokens := presentationTokenValues(validated.Presentation)
	for _, name := range presentationTokens {
		if value := tokens[name]; value != "" {
			args = append(args, "--token", name+"="+value)
		} else {
			args = append(args, "--clear-token", name)
		}
	}
	args = append(args, "--seq", strconv.FormatUint(validated.Sequence, 10), "--ttl-ms", strconv.FormatInt(validated.TTL.Milliseconds(), 10))
	return c.runOK(ctx, args)
}

// ClearMetadata removes every field owned by MetadataSource with a caller-
// supplied monotonic sequence. Completed panes are intentionally left open.
func (c *Client) ClearMetadata(ctx context.Context, locator Locator, sequence uint64) error {
	if err := locator.validate(); err != nil {
		return err
	}
	if locator.WorkspaceID != c.config.WorkspaceID {
		return errors.New("pane is outside the configured herdr workspace")
	}
	if sequence == 0 {
		return errors.New("metadata clear sequence must be positive")
	}
	args := []string{"pane", "report-metadata", locator.PaneID, "--source", MetadataSource, "--clear-title", "--clear-display-agent"}
	for _, name := range presentationTokens {
		args = append(args, "--clear-token", name)
	}
	args = append(args, "--seq", strconv.FormatUint(sequence, 10))
	return c.runOK(ctx, args)
}

type AgentState string

const (
	AgentIdle    AgentState = "idle"
	AgentWorking AgentState = "working"
	AgentBlocked AgentState = "blocked"
	AgentUnknown AgentState = "unknown"
)

// LifecycleReport is deliberately separate from Presentation. Callers may
// invoke ReportAgent only after receiving authoritative lifecycle evidence;
// transport success alone is never such evidence.
type LifecycleReport struct {
	Agent         string
	State         AgentState
	Sequence      uint64
	Authoritative bool
}

func (c *Client) ReportAgent(ctx context.Context, locator Locator, report LifecycleReport) error {
	if err := locator.validate(); err != nil {
		return err
	}
	if locator.WorkspaceID != c.config.WorkspaceID {
		return errors.New("pane is outside the configured herdr workspace")
	}
	if !report.Authoritative {
		return errors.New("refusing to report agent lifecycle without authoritative evidence")
	}
	if err := validateDisplay("agent label", report.Agent, 128); err != nil || report.Agent == "" {
		return errors.New("agent label is required and must be safe")
	}
	switch report.State {
	case AgentIdle, AgentWorking, AgentBlocked, AgentUnknown:
	default:
		return fmt.Errorf("unsupported reported agent state %q", report.State)
	}
	if report.Sequence == 0 {
		return errors.New("agent lifecycle sequence must be positive")
	}
	args := []string{"pane", "report-agent", locator.PaneID, "--source", LifecycleSource, "--agent", report.Agent, "--state", string(report.State), "--seq", strconv.FormatUint(report.Sequence, 10)}
	return c.runOK(ctx, args)
}

func (c *Client) ReleaseAgent(ctx context.Context, locator Locator, agent string, sequence uint64) error {
	if err := locator.validate(); err != nil {
		return err
	}
	if locator.WorkspaceID != c.config.WorkspaceID {
		return errors.New("pane is outside the configured herdr workspace")
	}
	if err := validateDisplay("agent label", agent, 128); err != nil || agent == "" {
		return errors.New("agent label is required and must be safe")
	}
	if sequence == 0 {
		return errors.New("agent lifecycle release sequence must be positive")
	}
	return c.runOK(ctx, []string{"pane", "release-agent", locator.PaneID, "--source", LifecycleSource, "--agent", agent, "--seq", strconv.FormatUint(sequence, 10)})
}

// HandoffAgent transfers this bridge's single lifecycle authority by releasing
// the previous label before reporting the new label as unknown. Unknown is a
// conservative handoff state, never evidence of completion.
func (c *Client) HandoffAgent(ctx context.Context, locator Locator, previousAgent, nextAgent string, releaseSequence, nextSequence uint64, authoritative bool) error {
	if !authoritative {
		return errors.New("refusing lifecycle handoff without authoritative evidence")
	}
	if nextSequence <= releaseSequence {
		return errors.New("lifecycle handoff sequence must advance")
	}
	if err := c.ReleaseAgent(ctx, locator, previousAgent, releaseSequence); err != nil {
		return fmt.Errorf("release previous lifecycle authority: %w", err)
	}
	if err := c.ReportAgent(ctx, locator, LifecycleReport{
		Agent: nextAgent, State: AgentUnknown, Sequence: nextSequence, Authoritative: true,
	}); err != nil {
		return fmt.Errorf("report next lifecycle authority: %w", err)
	}
	return nil
}

func (c *Client) runOK(ctx context.Context, args []string) error {
	stdout, stderr, err := c.run(ctx, args)
	if err != nil {
		return fmt.Errorf("run injected herdr binary: %w: %s", err, boundedText(stderr))
	}
	var response struct {
		Result struct {
			Type string `json:"type"`
		} `json:"result"`
		Error *wireError `json:"error,omitempty"`
	}
	if err := json.Unmarshal(stdout, &response); err != nil {
		return fmt.Errorf("decode herdr CLI response: %w", err)
	}
	if response.Error != nil {
		return fmt.Errorf("herdr CLI error %s: %s", response.Error.Code, response.Error.Message)
	}
	if response.Result.Type != "ok" {
		return fmt.Errorf("herdr CLI returned unexpected result %q", response.Result.Type)
	}
	return nil
}

// SequenceOrder is useful to callers persisting visibility events. It sorts a
// copy by sequence and rejects duplicates, making restart replay deterministic.
func SequenceOrder(updates []MetadataUpdate) ([]MetadataUpdate, error) {
	ordered := append([]MetadataUpdate(nil), updates...)
	sort.Slice(ordered, func(i, j int) bool { return ordered[i].Sequence < ordered[j].Sequence })
	for index, update := range ordered {
		if _, err := update.validate(); err != nil {
			return nil, err
		}
		if index > 0 && ordered[index-1].Sequence == update.Sequence {
			return nil, fmt.Errorf("duplicate metadata sequence %d", update.Sequence)
		}
	}
	return ordered, nil
}

// ReplayMetadata reapplies persisted display updates in ascending sequence
// after a confirmed Herdr restart. It never reports lifecycle state.
func (c *Client) ReplayMetadata(ctx context.Context, locator Locator, updates []MetadataUpdate) error {
	ordered, err := SequenceOrder(updates)
	if err != nil {
		return err
	}
	for _, update := range ordered {
		if err := c.ReportMetadata(ctx, locator, update); err != nil {
			return fmt.Errorf("replay metadata sequence %d: %w", update.Sequence, err)
		}
	}
	return nil
}

func ttlMilliseconds(ttl time.Duration) (uint64, error) {
	if ttl == 0 {
		ttl = DefaultTTL
	}
	if ttl != ActiveTTL && ttl != TerminalTTL {
		return 0, fmt.Errorf("metadata TTL must be active %s or terminal %s", ActiveTTL, TerminalTTL)
	}
	return uint64(ttl.Milliseconds()), nil
}
