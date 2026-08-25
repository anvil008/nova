package codingfleet

import (
	"fmt"
	"path"
	"regexp"
	"sort"
	"strings"
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

type AgentHandoffTest struct {
	Name   string `json:"name"`
	Passed bool   `json:"passed"`
	Detail string `json:"detail,omitempty"`
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
