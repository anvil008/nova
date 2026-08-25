package codingfleet

import (
	"strings"
	"testing"
)

func TestAgentPresentationAcceptsOnlySafeExplicitFields(t *testing.T) {
	presentation := AgentPresentation{
		TaskRef: "SWM-501", Task: "Expose foreign agent work", Phase: "execution",
		Summary: "running provider-free transport tests", Model: "claude-opus-4-1", Attempt: "attempt-02",
	}
	if err := presentation.Validate(); err != nil {
		t.Fatalf("Validate() error = %v", err)
	}
}

func TestAgentPresentationRejectsUnsafeOrUnboundedValues(t *testing.T) {
	valid := AgentPresentation{TaskRef: "SWM-501", Task: "Expose work", Phase: "execution", Model: "model-1", Attempt: "attempt-1"}
	tests := map[string]func(*AgentPresentation){
		"missing task ref": func(value *AgentPresentation) { value.TaskRef = "" },
		"unsafe task ref":  func(value *AgentPresentation) { value.TaskRef = "SWM 501" },
		"long task ref":    func(value *AgentPresentation) { value.TaskRef = strings.Repeat("a", MaxPresentationTaskRefBytes+1) },
		"multiline task":   func(value *AgentPresentation) { value.Task = "visible\nsecret" },
		"unknown phase":    func(value *AgentPresentation) { value.Phase = "doing-stuff" },
		"long summary":     func(value *AgentPresentation) { value.Summary = strings.Repeat("s", MaxPresentationSummaryBytes+1) },
		"control in model": func(value *AgentPresentation) { value.Model = "model\x00secret" },
		"pane attempt":     func(value *AgentPresentation) { value.Attempt = "w1:p2" },
	}
	for name, mutate := range tests {
		t.Run(name, func(t *testing.T) {
			value := valid
			mutate(&value)
			if err := value.Validate(); err == nil {
				t.Fatal("Validate() unexpectedly succeeded")
			}
		})
	}
}
