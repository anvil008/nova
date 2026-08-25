package codingfleet

import (
	"fmt"
	"path"
	"regexp"
	"sort"
	"strings"

	"github.com/anvil008/swarm-coder/controlplane"
)

// AgentHandoff is the deliberately small contract shared by native subagent
// dispatch and the foreign-harness launcher. Harnesses retain their own
// sessions, tools, and process lifecycle; this record only normalizes the
// information the parent orchestrator needs to integrate a result.
type AgentHandoff struct {
	APIVersion    string             `json:"apiVersion"`
	RunID         string             `json:"runId"`
	ParentRunID   string             `json:"parentRunId,omitempty"`
	CanonicalRole string             `json:"canonicalRole"`
	Provider      string             `json:"provider"`
	Model         string             `json:"model"`
	Effort        string             `json:"effort"`
	Mode          CapabilityMode     `json:"mode"`
	OwnedFiles    []string           `json:"ownedFiles"`
	Limits        AgentHandoffLimits `json:"limits"`
	ChangedFiles  []string           `json:"changedFiles"`
	Tests         []AgentHandoffTest `json:"tests"`
	Result        string             `json:"result"`
	Disposition   HandoffDisposition `json:"disposition"`
}

type AgentHandoffLimits struct {
	MaxMessages        int `json:"maxMessages"`
	MaxDurationSeconds int `json:"maxDurationSeconds"`
	MaxChildren        int `json:"maxChildren"`
}

// AgentHandoffTest ties a claimed result to the command that produced it. A
// self-reported boolean is not evidence, so `passed` requires a commandId.
type AgentHandoffTest struct {
	Name      string `json:"name"`
	Passed    bool   `json:"passed"`
	CommandID string `json:"commandId,omitempty"`
	Detail    string `json:"detail,omitempty"`
}

type HandoffDisposition string

const (
	HandoffSucceeded HandoffDisposition = "succeeded"
	HandoffFailed    HandoffDisposition = "failed"
	HandoffBlocked   HandoffDisposition = "blocked"
	HandoffUncertain HandoffDisposition = "uncertain"
	HandoffCancelled HandoffDisposition = "cancelled"
)

var routeTokenPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`)

// SelectModelDispatch keeps work inside the current vendor whenever possible.
// The shared launcher is selected only when the requested provider differs.
func SelectModelDispatch(currentProvider, requestedProvider string) (ModelDispatchPolicy, error) {
	currentProvider = strings.ToLower(strings.TrimSpace(currentProvider))
	requestedProvider = strings.ToLower(strings.TrimSpace(requestedProvider))
	if !routeTokenPattern.MatchString(currentProvider) || !routeTokenPattern.MatchString(requestedProvider) {
		return "", fmt.Errorf("current and requested providers must be explicit bounded identifiers")
	}
	if currentProvider == requestedProvider {
		return SameProviderNativeSubagentExplicitOverride, nil
	}
	return CrossProviderSupervisorExactRoleHeadless, nil
}

func ValidateAgentHandoff(handoff AgentHandoff) error {
	if handoff.APIVersion != AgentHandoffAPIVersion {
		return fmt.Errorf("agent handoff apiVersion %q is unsupported", handoff.APIVersion)
	}
	fields := []struct {
		name  string
		value string
	}{
		{name: "runId", value: handoff.RunID},
		{name: "canonicalRole", value: handoff.CanonicalRole},
		{name: "provider", value: handoff.Provider},
		{name: "model", value: handoff.Model},
		{name: "effort", value: handoff.Effort},
	}
	for _, field := range fields {
		if !routeTokenPattern.MatchString(field.value) {
			return fmt.Errorf("agent handoff %s is invalid", field.name)
		}
	}
	if handoff.ParentRunID != "" && !routeTokenPattern.MatchString(handoff.ParentRunID) {
		return fmt.Errorf("agent handoff parentRunId is invalid")
	}
	if handoff.Mode != CapabilityReadOnly && handoff.Mode != CapabilityWorkspaceWrite && handoff.Mode != CapabilityFactoryWrite {
		return fmt.Errorf("agent handoff mode %q is unsupported", handoff.Mode)
	}
	if handoff.OwnedFiles == nil || handoff.ChangedFiles == nil || handoff.Tests == nil {
		return fmt.Errorf("agent handoff file and test collections must be explicit")
	}
	if handoff.Mode != CapabilityReadOnly && len(handoff.OwnedFiles) == 0 {
		return fmt.Errorf("writable agent handoff requires owned files")
	}
	if err := validateHandoffPaths("ownedFiles", handoff.OwnedFiles); err != nil {
		return err
	}
	if err := validateHandoffPaths("changedFiles", handoff.ChangedFiles); err != nil {
		return err
	}
	if handoff.Limits.MaxMessages < 1 || handoff.Limits.MaxDurationSeconds < 1 || handoff.Limits.MaxChildren < 0 {
		return fmt.Errorf("agent handoff limits must be positive, with non-negative maxChildren")
	}
	for _, test := range handoff.Tests {
		if strings.TrimSpace(test.Name) == "" {
			return fmt.Errorf("agent handoff test name is required")
		}
		if test.Passed && !controlplane.ValidIdentifier(test.CommandID) {
			return fmt.Errorf("agent handoff test %q claims to pass without citing a command", test.Name)
		}
		if test.CommandID != "" && !controlplane.ValidIdentifier(test.CommandID) {
			return fmt.Errorf("agent handoff test %q cites an invalid commandId", test.Name)
		}
	}
	if strings.TrimSpace(handoff.Result) == "" {
		return fmt.Errorf("agent handoff result is required")
	}
	switch handoff.Disposition {
	case HandoffSucceeded, HandoffFailed, HandoffBlocked, HandoffUncertain, HandoffCancelled:
	default:
		return fmt.Errorf("agent handoff disposition %q is unsupported", handoff.Disposition)
	}
	if handoff.Disposition == HandoffSucceeded {
		for _, test := range handoff.Tests {
			if !test.Passed {
				return fmt.Errorf("successful agent handoff contains failed test %q", test.Name)
			}
		}
	}
	return nil
}

func validateHandoffPaths(field string, values []string) error {
	seen := make(map[string]struct{}, len(values))
	for _, value := range values {
		clean := path.Clean(value)
		if value == "" || clean != value || clean == "." || clean == ".." || strings.HasPrefix(clean, "../") || strings.HasPrefix(value, "/") {
			return fmt.Errorf("agent handoff %s contains invalid repository-relative path %q", field, value)
		}
		if _, duplicate := seen[value]; duplicate {
			return fmt.Errorf("agent handoff %s contains duplicate path %q", field, value)
		}
		seen[value] = struct{}{}
	}
	if !sort.StringsAreSorted(values) {
		return fmt.Errorf("agent handoff %s must be sorted", field)
	}
	return nil
}

// ReconcileHandoffTests rejects any passing test claim that the authoritative
// workflow result does not back with an exit-zero, current command run.
//
// The handoff and the result are both parsed from text the reporting agent
// wrote, so agreement between them proves only internal consistency. The guard
// snapshot is the corroborating record produced by a different process: when it
// is present, a cited commandId must name a run anvil-guard itself performed.
func ReconcileHandoffTests(handoff AgentHandoff, result controlplane.WorkflowResult, guard *controlplane.GuardSnapshot) error {
	commands := make(map[string]controlplane.CommandEvidence, len(result.Commands))
	for _, command := range result.Commands {
		commands[command.CommandID] = command
	}
	current := make(map[string]struct{}, len(result.Checks))
	for _, check := range result.Checks {
		if check.Passed && check.Current {
			current[check.CommandID] = struct{}{}
		}
	}
	// One run is evidence for one named check. Without this a single honest
	// `anvil-guard verify` satisfies every entry in RequiredChecks at once, and
	// the extra names cost the reporter nothing but a repeated commandId.
	claimedBy := make(map[string]string, len(handoff.Tests))
	for _, test := range handoff.Tests {
		if test.Passed && test.CommandID != "" {
			if previous, seen := claimedBy[test.CommandID]; seen && previous != test.Name {
				return fmt.Errorf("agent handoff tests %q and %q both cite command %q; one run backs one named check", previous, test.Name, test.CommandID)
			}
			claimedBy[test.CommandID] = test.Name
		}
		command, known := commands[test.CommandID]
		var record controlplane.GuardRecord
		if test.CommandID != "" {
			label := fmt.Sprintf("agent handoff test %q", test.Name)
			// A handoff test resolves to the green run it passed under or to
			// the sealed red run it failed under; the diff review is neither.
			kinds := []string{controlplane.GuardRecordGreen, controlplane.GuardRecordSealRed}
			var err error
			if known {
				record, err = controlplane.RequireGuardEvidence(guard, label, command, test.Passed, kinds...)
			} else {
				err = controlplane.RequireGuardRecord(guard, label, test.CommandID, test.Passed, kinds...)
			}
			if err != nil {
				return err
			}
		}
		if !test.Passed {
			continue
		}
		if !known {
			return fmt.Errorf("agent handoff test %q cites command %q that the result does not record", test.Name, test.CommandID)
		}
		// The guard's own record decides the outcome whenever it exists; the
		// agent's copy of the exit code is the thing under scrutiny.
		exitCode := command.ExitCode
		if record.CommandID != "" {
			exitCode = record.Evidence.ExitCode
		}
		if exitCode != 0 {
			return fmt.Errorf("agent handoff test %q claims to pass but command %q exited %d", test.Name, test.CommandID, exitCode)
		}
		if _, ok := current[test.CommandID]; !ok {
			return fmt.Errorf("agent handoff test %q lacks current passing check evidence for command %q", test.Name, test.CommandID)
		}
	}
	return nil
}
