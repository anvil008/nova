// Package runplane supervises provider-native headless coding-agent processes.
//
// It deliberately does not implement an agent or an orchestrator. Every job is
// bound to one exact, repository-owned Coding Fleet role and one exact model
// advertised by the selected native harness.
package runplane

import (
	"time"

	"github.com/anvil008/swarm-coder/codingfleet"
	"github.com/anvil008/swarm-coder/controlplane"
)

const APIVersion = "anvil.run-plane/v2"

type Harness string

const (
	HarnessCodex  Harness = "codex"
	HarnessClaude Harness = "claude"
	HarnessAGY    Harness = "agy"
)

type CapabilityMode string

const (
	ModeReadOnly       CapabilityMode = "read-only"
	ModeWorkspaceWrite CapabilityMode = "workspace-write"
)

type EvidenceContract struct {
	RequiredChecks    []string `json:"requiredChecks,omitempty"`
	RequiredArtifacts []string `json:"requiredArtifacts,omitempty"`
}

// Route is the normalized, fail-closed admission contract for one foreign job.
type Route struct {
	SourceHarness        Harness                        `json:"sourceHarness"`
	TargetHarness        Harness                        `json:"targetHarness"`
	Provider             string                         `json:"provider"`
	Family               string                         `json:"family"`
	ExactModel           string                         `json:"exactModel"`
	Effort               string                         `json:"effort"`
	CanonicalRoleID      string                         `json:"canonicalRoleId"`
	ParentRoleID         string                         `json:"parentRoleId"`
	ParentGoalID         string                         `json:"parentGoalId"`
	AssignmentID         string                         `json:"assignmentId"`
	GenerationID         string                         `json:"generationId"`
	GenerationNumber     uint64                         `json:"generationNumber"`
	ParentGenerationID   string                         `json:"parentGenerationId"`
	DispatchID           string                         `json:"dispatchId"`
	ParentDispatchID     string                         `json:"parentDispatchId"`
	CapabilityMode       CapabilityMode                 `json:"capabilityMode"`
	RepositoryRoot       string                         `json:"repositoryRoot"`
	RepositoryDigest     string                         `json:"repositoryDigest"`
	FileOwnership        []string                       `json:"fileOwnership"`
	SymbolOwnership      []controlplane.SymbolClaim     `json:"symbolOwnership"`
	Budget               controlplane.BudgetAmount      `json:"budget"`
	Limits               codingfleet.AgentHandoffLimits `json:"limits"`
	Decision             controlplane.RouteDecision     `json:"decision"`
	ParentExactRoute     *controlplane.ExactRoute       `json:"parentExactRoute"`
	RefinementAuthorized bool                           `json:"refinementAuthorized"`
	RefinementReason     string                         `json:"refinementReason"`
	Evidence             EvidenceContract               `json:"evidenceContract"`
}

type StartRequest struct {
	Route        Route                          `json:"route"`
	ControlPlane *ControlPlaneAdmission         `json:"controlPlane"`
	Brief        string                         `json:"brief"`
	Presentation *codingfleet.AgentPresentation `json:"presentation,omitempty"`
	Resume       string                         `json:"-"`
}

// ControlPlaneAdmission is the dependency-neutral record bundle that must
// validate before a production supervisor can reserve resources or spawn a
// provider process.
type ControlPlaneAdmission struct {
	Authority  controlplane.AuthorityEnvelope `json:"authority"`
	Selection  controlplane.SelectionEnvelope `json:"selection"`
	Route      controlplane.RouteEnvelope     `json:"route"`
	Goal       controlplane.GoalRecord        `json:"goal"`
	Assignment controlplane.AssignmentRecord  `json:"assignment"`
	Generation controlplane.GenerationRecord  `json:"generation"`
	Dispatch   controlplane.DispatchRecord    `json:"dispatch"`
	Budget     controlplane.BudgetReservation `json:"budget"`
	Ownership  []controlplane.OwnershipClaim  `json:"ownership"`
}

type Capability struct {
	Harness        Harness       `json:"harness"`
	Available      bool          `json:"available"`
	Version        string        `json:"version,omitempty"`
	Models         []string      `json:"models,omitempty"`
	Efforts        []string      `json:"efforts,omitempty"`
	ModelEfforts   []ModelEffort `json:"modelEfforts,omitempty"`
	Roles          []string      `json:"roles,omitempty"`
	SupportsSend   bool          `json:"supportsSend"`
	SupportsResume bool          `json:"supportsResume"`
	ObservedAt     time.Time     `json:"observedAt"`
	Error          string        `json:"error,omitempty"`
}

type ModelEffort struct {
	Provider  string `json:"provider"`
	Family    string `json:"family"`
	Model     string `json:"model"`
	Effort    string `json:"effort"`
	Reference string `json:"reference,omitempty"`
}

type JobStatus string

const (
	StatusStarting  JobStatus = "starting"
	StatusRunning   JobStatus = "running"
	StatusSucceeded JobStatus = "succeeded"
	StatusFailed    JobStatus = "failed"
	StatusCanceled  JobStatus = "canceled"
	StatusRecovered JobStatus = "recovered"
)

type Job struct {
	APIVersion          string                           `json:"apiVersion"`
	ID                  string                           `json:"id"`
	Route               Route                            `json:"route"`
	NativeRole          string                           `json:"nativeRole"`
	RoleDigest          string                           `json:"roleDigest"`
	ControlPlane        *ControlPlaneAdmission           `json:"controlPlane,omitempty"`
	WorkflowResult      *controlplane.WorkflowResult     `json:"workflowResult,omitempty"`
	WorkflowDisposition controlplane.WorkflowDisposition `json:"workflowDisposition"`
	WorkflowFailure     string                           `json:"workflowFailure,omitempty"`
	Handoff             *codingfleet.AgentHandoff        `json:"handoff,omitempty"`
	HandoffFailure      string                           `json:"handoffFailure,omitempty"`
	Cancellation        *controlplane.CancellationFence  `json:"cancellation,omitempty"`
	Status              JobStatus                        `json:"status"`
	SessionID           string                           `json:"sessionId,omitempty"`
	PID                 int                              `json:"pid,omitempty"`
	PGID                int                              `json:"pgid,omitempty"`
	ProcessStart        string                           `json:"processStart,omitempty"`
	PromptDigest        string                           `json:"promptDigest"`
	StartedAt           time.Time                        `json:"startedAt"`
	UpdatedAt           time.Time                        `json:"updatedAt"`
	FinishedAt          *time.Time                       `json:"finishedAt,omitempty"`
	ExitCode            *int                             `json:"exitCode,omitempty"`
	Failure             string                           `json:"failure,omitempty"`
	RecoveryNote        string                           `json:"recoveryNote,omitempty"`
	ResumeOf            string                           `json:"resumeOf,omitempty"`
	EvidenceSummary     []string                         `json:"evidenceSummary,omitempty"`
	Visibility          *PresentationState               `json:"visibility,omitempty"`
	Worker              *WorkerState                     `json:"worker,omitempty"`
}

// WorkerState contains only durable protocol progress. The nonce, socket,
// provider command, input, and volatile pane locator remain in the protected
// worker claim or supervisor memory and are never returned by the API.
type WorkerState struct {
	LastReceived uint64 `json:"lastReceived"`
	LastSent     uint64 `json:"lastSent"`
}

type VisibilityMode string

const (
	VisibilityOff      VisibilityMode = "off"
	VisibilityAuto     VisibilityMode = "auto"
	VisibilityRequired VisibilityMode = "required"
)

const TaskDisplaySource = "swarm:task-display"

const (
	ActiveVisibilityTTL       = 10 * time.Minute
	TerminalVisibilityTTL     = time.Hour
	VisibilityRefreshInterval = 3 * time.Minute
)

// VisibilityConfig is immutable for the lifetime of a supervisor. Every
// Herdr identity is injected explicitly; the run plane never discovers a
// binary from PATH, a focused pane, a current workspace, or live config.
type VisibilityConfig struct {
	Mode         VisibilityMode `json:"mode"`
	HerdrEnv     bool           `json:"-"`
	BinaryPath   string         `json:"-"`
	SocketPath   string         `json:"-"`
	SessionID    string         `json:"-"`
	WorkspaceID  string         `json:"-"`
	WorkerBinary string         `json:"-"`
	Timeout      time.Duration  `json:"-"`
}

// VisibilityHealth intentionally omits socket, session, workspace, pane, and
// binary values. It is safe to expose over the authenticated health endpoint.
type VisibilityHealth struct {
	Mode            VisibilityMode `json:"mode"`
	Ready           bool           `json:"ready"`
	ForeignJobsOnly bool           `json:"foreignJobsOnly"`
	Error           string         `json:"error,omitempty"`
}

// PresentationState is durable observer state. It is deliberately separate
// from both terminal work authority and the volatile Herdr locator.
type PresentationState struct {
	Mode            VisibilityMode                `json:"mode"`
	Presentation    codingfleet.AgentPresentation `json:"presentation"`
	Source          string                        `json:"source"`
	Sequence        uint64                        `json:"sequence"`
	TTLMillis       int64                         `json:"ttlMillis"`
	LastPublishedAt *time.Time                    `json:"lastPublishedAt,omitempty"`
	Terminal        bool                          `json:"terminal"`
	LastError       string                        `json:"lastError,omitempty"`
}

// VisibilityLocator is volatile routing evidence returned by Herdr. It is
// never serialized into Job state and none of its opaque values are IDs for
// durable goals, runs, dispatches, generations, tasks, or attempts.
type VisibilityLocator struct {
	WorkspaceID string
	TabID       string
	PaneID      string
	TerminalID  string
	JobLabel    string
}

type Event struct {
	Sequence uint64         `json:"sequence"`
	JobID    string         `json:"jobId"`
	At       time.Time      `json:"at"`
	Kind     string         `json:"kind"`
	Payload  map[string]any `json:"payload,omitempty"`
}

type Evidence struct {
	Job               Job      `json:"job"`
	Events            []Event  `json:"events"`
	RequiredChecks    []string `json:"requiredChecks,omitempty"`
	RequiredArtifacts []string `json:"requiredArtifacts,omitempty"`
}
