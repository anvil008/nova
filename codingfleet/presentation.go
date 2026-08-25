package codingfleet

import (
	"fmt"
	"regexp"
	"strings"
	"unicode/utf8"
)

const (
	MaxPresentationTaskRefBytes = 64
	MaxPresentationTaskBytes    = 80
	MaxPresentationSummaryBytes = 80
	MaxPresentationModelBytes   = 80
	MaxPresentationAttemptBytes = 32
)

var presentationIdentifier = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:/-]*$`)
var presentationAttempt = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._-]*$`)

var allowedPresentationPhases = map[string]struct{}{
	"research": {}, "planning": {}, "execution": {}, "review": {},
	"debugging": {}, "verification": {}, "factory": {}, "blocked": {},
	"starting": {}, "complete": {}, "completed": {}, "failed": {}, "canceled": {},
}

// AgentPresentation is the complete, intentionally small display contract
// that Swarm may publish to a terminal UI. It must never be populated from an
// agent brief, provider input, credentials, or volatile pane identifiers.
type AgentPresentation struct {
	TaskRef string `json:"taskRef"`
	Task    string `json:"task"`
	Phase   string `json:"phase"`
	Summary string `json:"summary,omitempty"`
	Model   string `json:"model"`
	Attempt string `json:"attempt"`
}

func (p AgentPresentation) Validate() error {
	if err := validatePresentationIdentifier("taskRef", p.TaskRef, MaxPresentationTaskRefBytes); err != nil {
		return err
	}
	if err := validatePresentationText("task", p.Task, 1, MaxPresentationTaskBytes); err != nil {
		return err
	}
	if _, ok := allowedPresentationPhases[p.Phase]; !ok {
		return fmt.Errorf("presentation phase %q is not allowed", p.Phase)
	}
	if p.Summary != "" {
		if err := validatePresentationText("summary", p.Summary, 1, MaxPresentationSummaryBytes); err != nil {
			return err
		}
	}
	if err := validatePresentationText("model", p.Model, 1, MaxPresentationModelBytes); err != nil {
		return err
	}
	if len(p.Attempt) == 0 || len(p.Attempt) > MaxPresentationAttemptBytes || !presentationAttempt.MatchString(p.Attempt) {
		return fmt.Errorf("presentation attempt must be 1..%d durable ASCII bytes", MaxPresentationAttemptBytes)
	}
	return nil
}

func validatePresentationIdentifier(field, value string, maximum int) error {
	if len(value) == 0 || len(value) > maximum || !presentationIdentifier.MatchString(value) {
		return fmt.Errorf("presentation %s must be 1..%d safe ASCII bytes", field, maximum)
	}
	return nil
}

func validatePresentationText(field, value string, minimum, maximum int) error {
	if len(value) < minimum || len(value) > maximum || !utf8.ValidString(value) || strings.TrimSpace(value) != value {
		return fmt.Errorf("presentation %s must be %d..%d trimmed UTF-8 bytes", field, minimum, maximum)
	}
	for _, value := range value {
		if value < 0x20 || value == 0x7f {
			return fmt.Errorf("presentation %s must not contain control characters", field)
		}
	}
	return nil
}
