// Package codingfleet loads and matches the provider-neutral coding-role catalog.
package codingfleet

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"path"
	"regexp"
	"sort"
	"strings"
	"time"
	"unicode"

	"github.com/anvil008/swarm-coder/controlplane"
	"github.com/anvil008/swarm-coder/harness-agents/canonical"
)

const (
	// APIVersion identifies the public catalog document contract.
	APIVersion = "anvil.coding-fleet/v4"

	workflowCodingOrchestratorID = "workflow-coding-orchestrator"
	workflowResearchID           = "workflow-research"
	workflowPlannerID            = "workflow-planner"
	workflowExecutorID           = "workflow-executor"
	workflowCodeReviewID         = "workflow-code-review"
	workflowDebuggerID           = "workflow-debugger"
	workflowCodingEvaluatorID    = "workflow-coding-evaluator"
	workflowAgentFactoryID       = "workflow-agent-factory"

	ClassTechnical RoleClass = "technical"
	ClassDomain    RoleClass = "domain"
	ClassWorkflow  RoleClass = "workflow"

	StatusDefinitionReady RoleStatus = "definition-ready"

	RoutingStandard RoutingTier = "standard"
	RoutingAdvanced RoutingTier = "advanced"

	CapabilityReadOnly       CapabilityMode = "read-only"
	CapabilityWorkspaceWrite CapabilityMode = "workspace-write"
	CapabilityFactoryWrite   CapabilityMode = "factory-write"
	CapabilityOrchestration  CapabilityMode = "orchestration-only"

	WorkflowLaneOrchestration WorkflowLane = "orchestration"
	WorkflowLaneDiagnosis     WorkflowLane = "diagnosis"
	WorkflowLaneDiscovery     WorkflowLane = "discovery"
	WorkflowLanePlanning      WorkflowLane = "planning"
	WorkflowLaneExecution     WorkflowLane = "execution"
	WorkflowLaneAssurance     WorkflowLane = "assurance"
	WorkflowLaneEvaluation    WorkflowLane = "evaluation"
	WorkflowLaneFactory       WorkflowLane = "factory"

	SpecialistPoolTechnical SpecialistPool = "technical"
	SpecialistPoolDomain    SpecialistPool = "domain"

	GoalModeNativeDurable GoalMode = "native-durable"
	// CheckpointPolicyFileAndNativeSession makes the on-disk goal directory the
	// system of record; native session state is only a cache of it.
	CheckpointPolicyFileAndNativeSession CheckpointPolicy = "file-and-native-session"
	SchedulingPolicyDependencyAware      SchedulingPolicy = "dependency-aware"

	ModelResolutionDiscoveredAllowlistedFailClosed ModelResolutionPolicy = "discovered-allowlisted-fail-closed"
	SameProviderNativeSubagentExplicitOverride     ModelDispatchPolicy   = "native-subagent-explicit-model-effort"
	CrossProviderSupervisorExactRoleHeadless       ModelDispatchPolicy   = "supervisor-exact-role-headless"
	AgentHandoffAPIVersion                                               = "anvil.agent-handoff/v1"

	// canonicalHomeDirectory is the fleet home the committed projections cite.
	// Generated definitions must be byte identical everywhere `render --check`
	// runs, so they name one fixed home; the installer derives the same layout
	// from the real home through guardInstalledPath and skillInstalledPath.
	canonicalHomeDirectory = "/home/anvil"

	supervisorRunplaneDefaultURL       = "http://127.0.0.1:8083"
	supervisorRunplaneDefaultState     = "~/.local/state/swarm-runplane"
	supervisorRunplaneDefaultTokenFile = "~/.local/state/swarm-runplane/auth.token"
	supervisorRunplaneCapabilityPolicy = "capability-first-fail-closed"
	supervisorRunplaneBriefTransport   = "request-file-and-stdin"
	// supervisorRunplaneSkillSource is the authored document the installer
	// links; it holds the full lifecycle reference outside the orchestrator
	// prompt so it is loaded only when a foreign dispatch actually happens.
	supervisorRunplaneSkillFile   = "swarm-runplane-foreign-dispatch.md"
	supervisorRunplaneSkillSource = "harness-agents/skills/" + supervisorRunplaneSkillFile
	// checkpointGoalDirectory is where the durable goal record lives.
	checkpointGoalDirectory     = "~/.local/state/swarm-runplane/goals/<goalId>/"
	supervisorMCPServerName     = "anvil-swarm-runplane"
	supervisorMCPToolName       = "swarm_runplane_lifecycle"
	supervisorClaudeMCPToolName = "mcp__anvil-swarm-runplane__swarm_runplane_lifecycle"

	codingOrchestratorMaxParallel = 25
	workflowUnitMaxParallel       = 10
	workflowExecutorMaxParallel   = 20

	HarnessAntigravity HarnessTarget = "antigravity"
	HarnessClaude      HarnessTarget = "claude"
	HarnessCodex       HarnessTarget = "codex"
)

// Installed artifact paths the rendered prompts cite, all derived from the one
// canonical home so a prompt can never name a location the installer does not
// use.
var (
	supervisorRunplaneBinary = path.Join(canonicalHomeDirectory, ".local", "bin", "swarm-runplane")
	supervisorRunplaneSkill  = skillInstalledPath(canonicalHomeDirectory)
)

var stableIDPattern = regexp.MustCompile(`^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$`)

type workflowUnitContract struct {
	RoleID             string
	Name               string
	Lane               WorkflowLane
	CapabilityMode     CapabilityMode
	MaxParallel        int
	CreatesSpecialists bool
}

// workflowUnitContracts is the complete peer workflow layer beneath the
// orchestration-only coding front door. Units never own one another and never
// delegate to other workflow units; each selects leaf specialists dynamically.
var workflowUnitContracts = []workflowUnitContract{
	{RoleID: workflowResearchID, Name: "Research Agent", Lane: WorkflowLaneDiscovery, CapabilityMode: CapabilityReadOnly, MaxParallel: workflowUnitMaxParallel},
	{RoleID: workflowPlannerID, Name: "Planner Agent", Lane: WorkflowLanePlanning, CapabilityMode: CapabilityReadOnly, MaxParallel: workflowUnitMaxParallel},
	{RoleID: workflowExecutorID, Name: "Executor Agent", Lane: WorkflowLaneExecution, CapabilityMode: CapabilityWorkspaceWrite, MaxParallel: workflowExecutorMaxParallel},
	{RoleID: workflowCodeReviewID, Name: "Code Review Agent", Lane: WorkflowLaneAssurance, CapabilityMode: CapabilityReadOnly, MaxParallel: workflowUnitMaxParallel},
}

// Document is the versioned, provider-neutral coding-fleet contract.
// Counts are populated by Load from Roles and are not stored separately in the
// canonical source.
type Document struct {
	APIVersion        string             `json:"apiVersion"`
	CatalogVersion    string             `json:"catalogVersion"`
	GeneratedAt       string             `json:"generatedAt"`
	Source            SourceMetadata     `json:"source"`
	AuthorityProfiles []AuthorityProfile `json:"authorityProfiles"`
	Counts            Counts             `json:"counts"`
	Roles             []Role             `json:"roles"`
	KnowledgeRoles    []KnowledgeRole    `json:"knowledgeRoles,omitempty"`
}

// AuthorityProfile is a reusable, closed role ceiling. A role selects exactly
// one profile through its capabilityMode; dispatch-time authority is still the
// four-way intersection with parent, request, and observed harness grants.
type AuthorityProfile struct {
	ID             string                      `json:"id"`
	RoleClass      RoleClass                   `json:"roleClass"`
	CapabilityMode CapabilityMode              `json:"capabilityMode"`
	Grant          controlplane.AuthorityGrant `json:"grant"`
}

// SourceMetadata records the repository evidence boundary used to curate the
// static catalog. It is descriptive metadata, not a runtime scanner request.
type SourceMetadata struct {
	Repository     string `json:"repository"`
	PlanningCommit string `json:"planningCommit"`
	EvidenceBasis  string `json:"evidenceBasis"`
}

// Counts contains aggregates derived from the validated role definitions.
type Counts struct {
	Total           int `json:"total"`
	Workflow        int `json:"workflow"`
	Technical       int `json:"technical"`
	Domain          int `json:"domain"`
	DefinitionReady int `json:"definitionReady"`
}

// RoleClass separates coordinating workflows, implementation-stack
// specialists, and product or operations-domain specialists.
type RoleClass string

// RoleStatus describes definition readiness; it does not claim runtime state.
type RoleStatus string

// RoutingTier is a provider-neutral complexity hint for native renderers.
type RoutingTier string

// CapabilityMode states whether a native projection may edit the workspace.
type CapabilityMode string

// HarnessTarget names a supported native projection target.
type HarnessTarget string

// WorkflowLane gives each workflow one stable responsibility in the coding
// lifecycle. It organizes native orchestration without claiming an ADK graph.
type WorkflowLane string

// SpecialistPool names a shared catalog lane that a workflow unit may
// select from dynamically. Pools describe availability, not mandatory fan-out.
type SpecialistPool string

// GoalMode describes how the fleet's single integration owner persists the
// overall objective. Native durability deliberately relies on each harness's
// supported goal/session primitive instead of inventing another run store.
type GoalMode string

// CheckpointPolicy names the portable checkpoint contract used at native
// session, handoff, phase, interruption, and compaction boundaries.
type CheckpointPolicy string

// SchedulingPolicy describes how the durable owner releases runnable work.
type SchedulingPolicy string

// ModelResolutionPolicy describes how a natural-language model route becomes
// one available provider/family/model/effort tuple.
type ModelResolutionPolicy string

// ModelDispatchPolicy identifies the native or supervised execution boundary
// used after a model route has been resolved.
type ModelDispatchPolicy string

// OrchestrationSpec is present only on the fleet's durable integration owner.
// Workflow units and specialists return evidence to it and never claim overall
// completion authority themselves.
type OrchestrationSpec struct {
	GoalMode            GoalMode          `json:"goalMode"`
	CheckpointPolicy    CheckpointPolicy  `json:"checkpointPolicy"`
	SchedulingPolicy    SchedulingPolicy  `json:"schedulingPolicy"`
	ProactiveDelegation bool              `json:"proactiveDelegation"`
	CompletionAuthority bool              `json:"completionAuthority"`
	ModelRouting        *ModelRoutingSpec `json:"modelRouting,omitempty"`
}

// ModelRoutingSpec is the provider-neutral routing contract consumed by native
// projections and the supervised cross-harness run plane. It records policy,
// not a static model inventory: availability must be discovered at dispatch.
type ModelRoutingSpec struct {
	ExplicitUserRouteOverridesDefaults bool                   `json:"explicitUserRouteOverridesDefaults"`
	ResolutionPolicy                   ModelResolutionPolicy  `json:"resolutionPolicy"`
	NativeFirst                        bool                   `json:"nativeFirst"`
	SameProviderDispatch               ModelDispatchPolicy    `json:"sameProviderDispatch"`
	CrossProviderDispatch              ModelDispatchPolicy    `json:"crossProviderDispatch"`
	ParentRetainsAuthority             bool                   `json:"parentRetainsAuthority"`
	HandoffBoundary                    string                 `json:"handoffBoundary"`
	MaxVerificationPasses              int                    `json:"maxVerificationPasses"`
	MaxRepairAttempts                  int                    `json:"maxRepairAttempts"`
	SupervisorRunplane                 SupervisorRunplaneSpec `json:"supervisorRunplane"`
}

// SupervisorRunplaneSpec names the installed, authenticated loopback adapter
// used for cross-provider or cross-family role execution.
type SupervisorRunplaneSpec struct {
	Binary           string `json:"binary"`
	DefaultURL       string `json:"defaultUrl"`
	DefaultState     string `json:"defaultState"`
	DefaultTokenFile string `json:"defaultTokenFile"`
	StateEnv         string `json:"stateEnv"`
	URLEnv           string `json:"urlEnv"`
	TokenEnv         string `json:"tokenEnv"`
	TokenFileEnv     string `json:"tokenFileEnv"`
	CapabilityPolicy string `json:"capabilityPolicy"`
	BriefTransport   string `json:"briefTransport"`
	SkillDocument    string `json:"skillDocument"`
}

func canonicalSupervisorRunplaneSpec() SupervisorRunplaneSpec {
	return SupervisorRunplaneSpec{
		Binary:           supervisorRunplaneBinary,
		DefaultURL:       supervisorRunplaneDefaultURL,
		DefaultState:     supervisorRunplaneDefaultState,
		DefaultTokenFile: supervisorRunplaneDefaultTokenFile,
		StateEnv:         "SWARM_RUNPLANE_STATE",
		URLEnv:           "SWARM_RUNPLANE_URL",
		TokenEnv:         "SWARM_RUNPLANE_TOKEN",
		TokenFileEnv:     "SWARM_RUNPLANE_TOKEN_FILE",
		CapabilityPolicy: supervisorRunplaneCapabilityPolicy,
		BriefTransport:   supervisorRunplaneBriefTransport,
		SkillDocument:    supervisorRunplaneSkill,
	}
}

// Role is one validated coding specialist definition.
type Role struct {
	ID             string          `json:"id"`
	Name           string          `json:"name"`
	Class          RoleClass       `json:"class"`
	Summary        string          `json:"summary"`
	Status         RoleStatus      `json:"status"`
	Instructions   string          `json:"instructions"`
	Activation     Activation      `json:"activation"`
	Boundaries     []string        `json:"boundaries"`
	Evidence       []Evidence      `json:"evidence"`
	Tags           []string        `json:"tags"`
	RoutingTier    RoutingTier     `json:"routingTier"`
	CapabilityMode CapabilityMode  `json:"capabilityMode"`
	HarnessTargets []HarnessTarget `json:"harnessTargets"`
	Workflow       *WorkflowSpec   `json:"workflow,omitempty"`
}

// WorkflowSpec describes native-harness orchestration guidance. It is
// declarative adapter input, not an executable ADK graph.
type WorkflowSpec struct {
	Stages                   []string           `json:"stages"`
	Delegates                []string           `json:"delegates"`
	SpecialistPools          []SpecialistPool   `json:"specialistPools,omitempty"`
	ProposableRoleClasses    []RoleClass        `json:"proposableRoleClasses"`
	InvocableRoleIDs         []string           `json:"invocableRoleIds"`
	InvocableSpecialistPools []SpecialistPool   `json:"invocableSpecialistPools"`
	Lane                     WorkflowLane       `json:"lane"`
	Orchestration            *OrchestrationSpec `json:"orchestration,omitempty"`
	CreatesSpecialists       bool               `json:"createsSpecialists,omitempty"`
	MaxParallel              int                `json:"maxParallel"`
}

// Activation declares weighted, explicit matching rules and the minimum score
// required to select a role.
type Activation struct {
	Threshold    int              `json:"threshold"`
	Files        []WeightedSignal `json:"files"`
	Dependencies []WeightedSignal `json:"dependencies"`
	Keywords     []WeightedSignal `json:"keywords"`
}

// WeightedSignal contributes Weight once when Value matches at least one
// normalized caller-supplied signal.
type WeightedSignal struct {
	Value  string `json:"value"`
	Weight int    `json:"weight"`
}

// Evidence points to a repository-owned manifest, implementation, or test that
// justifies including a role.
type Evidence struct {
	Repository string `json:"repository"`
	Path       string `json:"path"`
	Detail     string `json:"detail"`
}

// Signals is an explicit in-memory inventory supplied by a trusted caller.
// Selection never reads these values as paths, scans a filesystem, or launches
// a process.
type Signals struct {
	Files        []string `json:"files,omitempty"`
	Dependencies []string `json:"dependencies,omitempty"`
	Keywords     []string `json:"keywords,omitempty"`
}

// Match is one above-threshold role selection and its stable explanation.
type Match struct {
	RoleID  string   `json:"roleId"`
	Score   int      `json:"score"`
	Reasons []string `json:"reasons"`
}

// KnowledgeRole captures preserved product-domain context projected into
// repository documentation rather than live agent definitions.
type KnowledgeRole struct {
	ID           string   `json:"id"`
	Name         string   `json:"name"`
	Summary      string   `json:"summary"`
	Instructions string   `json:"instructions"`
	Boundaries   []string `json:"boundaries"`
	Repositories []string `json:"repositories"`
}

// sourceDocument deliberately omits Counts: aggregates in the public Document
// must always be derived from role definitions by Load.
type sourceDocument struct {
	APIVersion        string             `json:"apiVersion"`
	CatalogVersion    string             `json:"catalogVersion"`
	GeneratedAt       string             `json:"generatedAt"`
	Source            SourceMetadata     `json:"source"`
	AuthorityProfiles []AuthorityProfile `json:"authorityProfiles"`
	Roles             []Role             `json:"roles"`
	KnowledgeRoles    []KnowledgeRole    `json:"knowledgeRoles,omitempty"`
}

// Load decodes, validates, canonicalizes, and counts the embedded catalog.
func Load() (Document, error) {
	document, err := decodeCatalog(canonical.Bytes())
	if err != nil {
		return Document{}, err
	}
	if err := validateFleetTopology(document.Roles); err != nil {
		return Document{}, fmt.Errorf("validate coding-fleet topology: %w", err)
	}
	return document, nil
}

func decodeCatalog(data []byte) (Document, error) {
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()

	var source sourceDocument
	if err := decoder.Decode(&source); err != nil {
		return Document{}, fmt.Errorf("decode coding-fleet catalog: %w", err)
	}
	if err := requireJSONEOF(decoder); err != nil {
		return Document{}, err
	}

	document := Document{
		APIVersion:        source.APIVersion,
		CatalogVersion:    source.CatalogVersion,
		GeneratedAt:       source.GeneratedAt,
		Source:            source.Source,
		AuthorityProfiles: source.AuthorityProfiles,
		Roles:             source.Roles,
		KnowledgeRoles:    source.KnowledgeRoles,
	}
	if err := validateDocument(document); err != nil {
		return Document{}, fmt.Errorf("validate coding-fleet catalog: %w", err)
	}
	normalizeDocument(&document)
	return document, nil
}

func requireJSONEOF(decoder *json.Decoder) error {
	var extra any
	if err := decoder.Decode(&extra); err != io.EOF {
		if err == nil {
			return fmt.Errorf("decode coding-fleet catalog: multiple JSON values")
		}
		return fmt.Errorf("decode coding-fleet catalog trailing data: %w", err)
	}
	return nil
}

func validateDocument(document Document) error {
	if document.APIVersion != APIVersion {
		return fmt.Errorf("apiVersion %q must equal %q", document.APIVersion, APIVersion)
	}
	if strings.TrimSpace(document.CatalogVersion) == "" {
		return fmt.Errorf("catalogVersion is required")
	}
	if _, err := time.Parse(time.RFC3339, document.GeneratedAt); err != nil {
		return fmt.Errorf("generatedAt must be RFC3339: %w", err)
	}
	if strings.TrimSpace(document.Source.Repository) == "" ||
		strings.TrimSpace(document.Source.PlanningCommit) == "" ||
		strings.TrimSpace(document.Source.EvidenceBasis) == "" {
		return fmt.Errorf("source repository, planningCommit, and evidenceBasis are required")
	}
	if len(document.Roles) == 0 {
		return fmt.Errorf("roles must not be empty")
	}
	if err := validateAuthorityProfiles(document.AuthorityProfiles); err != nil {
		return err
	}

	ids := make(map[string]struct{}, len(document.Roles)+len(document.KnowledgeRoles))
	names := make(map[string]struct{}, len(document.Roles)+len(document.KnowledgeRoles))
	for index := range document.Roles {
		role := document.Roles[index]
		if err := validateRole(role); err != nil {
			return fmt.Errorf("role[%d] %q: %w", index, role.ID, err)
		}
		if _, exists := ids[role.ID]; exists {
			return fmt.Errorf("role[%d] %q: duplicate id", index, role.ID)
		}
		ids[role.ID] = struct{}{}
		nameKey := normalizeText(role.Name)
		if _, exists := names[nameKey]; exists {
			return fmt.Errorf("role[%d] %q: duplicate name %q", index, role.ID, role.Name)
		}
		names[nameKey] = struct{}{}
	}
	for index, kr := range document.KnowledgeRoles {
		if err := validateKnowledgeRole(kr); err != nil {
			return fmt.Errorf("knowledgeRole[%d] %q: %w", index, kr.ID, err)
		}
		if _, exists := ids[kr.ID]; exists {
			return fmt.Errorf("knowledgeRole[%d] %q: duplicate id or conflicts with role id", index, kr.ID)
		}
		ids[kr.ID] = struct{}{}
		nameKey := normalizeText(kr.Name)
		if _, exists := names[nameKey]; exists {
			return fmt.Errorf("knowledgeRole[%d] %q: duplicate name %q", index, kr.ID, kr.Name)
		}
		names[nameKey] = struct{}{}
	}
	for _, role := range document.Roles {
		if _, err := AuthorityForRole(document, role.ID); err != nil {
			return err
		}
	}
	for index, role := range document.Roles {
		if role.Workflow == nil {
			continue
		}
		for delegateIndex, delegate := range role.Workflow.Delegates {
			if delegate == role.ID {
				return fmt.Errorf("role[%d] %q: workflow delegate[%d] cannot reference itself", index, role.ID, delegateIndex)
			}
			if _, exists := ids[delegate]; !exists {
				return fmt.Errorf("role[%d] %q: workflow delegate[%d] %q does not exist", index, role.ID, delegateIndex, delegate)
			}
		}
	}
	if err := validateWorkflowGraph(document.Roles); err != nil {
		return err
	}
	return nil
}

func validateWorkflowGraph(roles []Role) error {
	byID := make(map[string]Role, len(roles))
	for _, role := range roles {
		byID[role.ID] = role
	}
	state := make(map[string]uint8, len(roles))
	stack := make([]string, 0)
	var visit func(string) error
	visit = func(roleID string) error {
		switch state[roleID] {
		case 1:
			return fmt.Errorf("workflow delegate graph contains a cycle through %q: %s", roleID, strings.Join(append(stack, roleID), " -> "))
		case 2:
			return nil
		}
		role := byID[roleID]
		if role.Workflow == nil {
			state[roleID] = 2
			return nil
		}
		state[roleID] = 1
		stack = append(stack, roleID)
		for _, delegate := range role.Workflow.Delegates {
			if err := visit(delegate); err != nil {
				return err
			}
		}
		stack = stack[:len(stack)-1]
		state[roleID] = 2
		return nil
	}
	for _, role := range roles {
		if role.Workflow != nil {
			if err := visit(role.ID); err != nil {
				return err
			}
		}
	}
	return nil
}

func validateAuthorityProfiles(profiles []AuthorityProfile) error {
	if len(profiles) != 5 {
		return fmt.Errorf("authorityProfiles must contain exactly five class/capability ceilings")
	}
	wanted := map[string]struct{}{
		authorityProfileKey(ClassWorkflow, CapabilityOrchestration):   {},
		authorityProfileKey(ClassWorkflow, CapabilityReadOnly):        {},
		authorityProfileKey(ClassWorkflow, CapabilityWorkspaceWrite):  {},
		authorityProfileKey(ClassTechnical, CapabilityReadOnly):       {},
		authorityProfileKey(ClassTechnical, CapabilityWorkspaceWrite): {},
	}
	// Domain and technical leaves deliberately share the two leaf profiles;
	// domain lookup falls back to the matching technical profile.
	seenIDs := make(map[string]struct{}, len(profiles))
	seenKeys := make(map[string]struct{}, len(profiles))
	for index, profile := range profiles {
		if !stableIDPattern.MatchString(profile.ID) {
			return fmt.Errorf("authorityProfiles[%d] id %q is invalid", index, profile.ID)
		}
		if _, duplicate := seenIDs[profile.ID]; duplicate {
			return fmt.Errorf("authorityProfiles[%d] duplicates id %q", index, profile.ID)
		}
		seenIDs[profile.ID] = struct{}{}
		key := authorityProfileKey(profile.RoleClass, profile.CapabilityMode)
		if _, expected := wanted[key]; !expected {
			return fmt.Errorf("authorityProfiles[%d] has unsupported class/mode %s", index, key)
		}
		if _, duplicate := seenKeys[key]; duplicate {
			return fmt.Errorf("authorityProfiles[%d] duplicates class/mode %s", index, key)
		}
		seenKeys[key] = struct{}{}
		if _, err := controlplane.IntersectAuthority(profile.Grant, profile.Grant, profile.Grant, profile.Grant); err != nil {
			return fmt.Errorf("authorityProfiles[%d] grant: %w", index, err)
		}
	}
	for key := range wanted {
		if _, ok := seenKeys[key]; !ok {
			return fmt.Errorf("authorityProfiles missing %s", key)
		}
	}
	return nil
}

func authorityProfileKey(class RoleClass, mode CapabilityMode) string {
	return string(class) + "/" + string(mode)
}

// AuthorityForRole returns the canonical role ceiling. Domain and technical
// leaves intentionally share identical leaf ceilings.
func AuthorityForRole(document Document, roleID string) (AuthorityProfile, error) {
	var role *Role
	for index := range document.Roles {
		if document.Roles[index].ID == roleID {
			role = &document.Roles[index]
			break
		}
	}
	if role == nil {
		return AuthorityProfile{}, fmt.Errorf("role %q does not exist", roleID)
	}
	class := role.Class
	if class == ClassDomain {
		class = ClassTechnical
	}
	key := authorityProfileKey(class, role.CapabilityMode)
	for _, profile := range document.AuthorityProfiles {
		if authorityProfileKey(profile.RoleClass, profile.CapabilityMode) == key {
			return profile, nil
		}
	}
	return AuthorityProfile{}, fmt.Errorf("role %q has no authority profile for %s", roleID, key)
}

func validateFleetTopology(roles []Role) error {
	byID := make(map[string]Role, len(roles))
	workflowCount := 0
	for _, role := range roles {
		byID[role.ID] = role
		if role.Class == ClassWorkflow {
			workflowCount++
		}
		if role.CapabilityMode == CapabilityFactoryWrite && role.ID != workflowAgentFactoryID {
			return fmt.Errorf("role %q may not use factory-write capability", role.ID)
		}
		if role.CapabilityMode == CapabilityOrchestration && role.ID != workflowCodingOrchestratorID {
			return fmt.Errorf("role %q may not use orchestration-only capability", role.ID)
		}
	}
	if want := len(workflowUnitContracts) + 1; workflowCount != want {
		return fmt.Errorf("coding fleet must contain one orchestrator and %d workflow units, got %d workflow roles", len(workflowUnitContracts), workflowCount)
	}

	orchestrator, exists := byID[workflowCodingOrchestratorID]
	if !exists || orchestrator.Class != ClassWorkflow || orchestrator.Workflow == nil {
		return fmt.Errorf("coding orchestrator %q must be a workflow role", workflowCodingOrchestratorID)
	}
	if orchestrator.Name != "Coding Orchestrator Agent" || orchestrator.CapabilityMode != CapabilityOrchestration {
		return fmt.Errorf("coding orchestrator must be named Coding Orchestrator Agent and use orchestration-only capability")
	}
	if orchestrator.Workflow.Lane != WorkflowLaneOrchestration || len(orchestrator.Workflow.SpecialistPools) != 0 || orchestrator.Workflow.CreatesSpecialists || orchestrator.Workflow.MaxParallel != codingOrchestratorMaxParallel {
		return fmt.Errorf("coding orchestrator must own only the orchestration lane, four workflow delegates, and maxParallel %d", codingOrchestratorMaxParallel)
	}
	if !roleClassesEqual(orchestrator.Workflow.ProposableRoleClasses, []RoleClass{ClassTechnical, ClassDomain}) {
		return fmt.Errorf("coding orchestrator must be able to propose technical and domain lenses")
	}
	if !stringSetsEqual(orchestrator.Workflow.InvocableRoleIDs, orchestrator.Workflow.Delegates) || len(orchestrator.Workflow.InvocableSpecialistPools) != 0 {
		return fmt.Errorf("coding orchestrator may invoke exactly the four workflow units and no specialist pool")
	}
	wantOrchestration := OrchestrationSpec{
		GoalMode:            GoalModeNativeDurable,
		CheckpointPolicy:    CheckpointPolicyFileAndNativeSession,
		SchedulingPolicy:    SchedulingPolicyDependencyAware,
		ProactiveDelegation: true,
		CompletionAuthority: true,
	}
	wantModelRouting := ModelRoutingSpec{
		ExplicitUserRouteOverridesDefaults: true,
		ResolutionPolicy:                   ModelResolutionDiscoveredAllowlistedFailClosed,
		NativeFirst:                        true,
		SameProviderDispatch:               SameProviderNativeSubagentExplicitOverride,
		CrossProviderDispatch:              CrossProviderSupervisorExactRoleHeadless,
		ParentRetainsAuthority:             true,
		HandoffBoundary:                    AgentHandoffAPIVersion,
		MaxVerificationPasses:              2,
		MaxRepairAttempts:                  1,
		SupervisorRunplane:                 canonicalSupervisorRunplaneSpec(),
	}
	gotOrchestration := orchestrator.Workflow.Orchestration
	if gotOrchestration == nil {
		return fmt.Errorf("coding orchestrator orchestration = %+v, want %+v", orchestrator.Workflow.Orchestration, wantOrchestration)
	}
	gotModelRouting := gotOrchestration.ModelRouting
	gotWithoutModelRouting := *gotOrchestration
	gotWithoutModelRouting.ModelRouting = nil
	if gotWithoutModelRouting != wantOrchestration || gotModelRouting == nil || *gotModelRouting != wantModelRouting {
		return fmt.Errorf("coding orchestrator orchestration = %+v, model routing = %+v; want %+v, model routing = %+v", gotWithoutModelRouting, gotModelRouting, wantOrchestration, wantModelRouting)
	}

	wantDelegates := make(map[string]struct{}, len(workflowUnitContracts))
	for _, contract := range workflowUnitContracts {
		wantDelegates[contract.RoleID] = struct{}{}
		unit, exists := byID[contract.RoleID]
		if !exists || unit.Class != ClassWorkflow || unit.Workflow == nil {
			return fmt.Errorf("workflow unit %q is required", contract.RoleID)
		}
		if unit.Name != contract.Name || unit.Workflow.Lane != contract.Lane || unit.CapabilityMode != contract.CapabilityMode {
			return fmt.Errorf("workflow unit %q identity, lane, or capability does not match its peer-layer contract", contract.RoleID)
		}
		if unit.Workflow.MaxParallel != contract.MaxParallel || unit.Workflow.CreatesSpecialists != contract.CreatesSpecialists {
			return fmt.Errorf("workflow unit %q parallelism or creation contract is invalid", contract.RoleID)
		}
		if len(unit.Workflow.Delegates) != 0 || unit.Workflow.Orchestration != nil {
			return fmt.Errorf("workflow unit %q must be a peer leaf beneath the orchestrator", contract.RoleID)
		}
		if err := validateSpecialistPools(unit.Workflow.SpecialistPools); err != nil {
			return fmt.Errorf("workflow unit %q: %w", contract.RoleID, err)
		}
		if !roleClassesEqual(unit.Workflow.ProposableRoleClasses, []RoleClass{ClassTechnical, ClassDomain}) || len(unit.Workflow.InvocableRoleIDs) != 0 {
			return fmt.Errorf("workflow unit %q must propose leaf classes and invoke no role IDs", contract.RoleID)
		}
		if err := validateSpecialistPools(unit.Workflow.InvocableSpecialistPools); err != nil {
			return fmt.Errorf("workflow unit %q invocable pools: %w", contract.RoleID, err)
		}
		if !workflowDelegatesTo(orchestrator, contract.RoleID) {
			return fmt.Errorf("coding orchestrator must delegate to workflow unit %q", contract.RoleID)
		}
	}
	if len(orchestrator.Workflow.Delegates) != len(wantDelegates) {
		return fmt.Errorf("coding orchestrator delegates = %d, want exactly %d workflow units", len(orchestrator.Workflow.Delegates), len(wantDelegates))
	}
	for _, delegateID := range orchestrator.Workflow.Delegates {
		if _, expected := wantDelegates[delegateID]; !expected {
			return fmt.Errorf("coding orchestrator has unexpected delegate %q", delegateID)
		}
	}
	for _, role := range roles {
		if role.Class == ClassWorkflow && role.ID != workflowCodingOrchestratorID {
			if _, expected := wantDelegates[role.ID]; !expected {
				return fmt.Errorf("unexpected workflow role %q outside the flat peer layer", role.ID)
			}
		}
	}

	return nil
}

func workflowDelegatesTo(role Role, wanted string) bool {
	if role.Workflow == nil {
		return false
	}
	for _, delegateID := range role.Workflow.Delegates {
		if delegateID == wanted {
			return true
		}
	}
	return false
}

func validateRole(role Role) error {
	if !stableIDPattern.MatchString(role.ID) {
		return fmt.Errorf("id must be a stable kebab-case identifier")
	}
	if strings.TrimSpace(role.Name) == "" || strings.TrimSpace(role.Summary) == "" || strings.TrimSpace(role.Instructions) == "" {
		return fmt.Errorf("name, summary, and instructions are required")
	}
	if role.Class != ClassTechnical && role.Class != ClassDomain && role.Class != ClassWorkflow {
		return fmt.Errorf("class %q is not allowed", role.Class)
	}
	if role.Class == ClassWorkflow {
		if role.Workflow == nil {
			return fmt.Errorf("workflow metadata is required for workflow roles")
		}
		if role.Workflow.MaxParallel < 1 || role.Workflow.MaxParallel > codingOrchestratorMaxParallel {
			return fmt.Errorf("workflow maxParallel must be between 1 and %d", codingOrchestratorMaxParallel)
		}
		switch role.Workflow.Lane {
		case WorkflowLaneOrchestration, WorkflowLaneDiagnosis, WorkflowLaneDiscovery,
			WorkflowLanePlanning, WorkflowLaneExecution, WorkflowLaneAssurance,
			WorkflowLaneEvaluation, WorkflowLaneFactory:
		default:
			return fmt.Errorf("workflow lane %q is not allowed", role.Workflow.Lane)
		}
		if err := validateStrings("workflow stage", role.Workflow.Stages, false); err != nil {
			return err
		}
		if role.Workflow.ProposableRoleClasses == nil || role.Workflow.InvocableRoleIDs == nil || role.Workflow.InvocableSpecialistPools == nil {
			return fmt.Errorf("workflow proposal and invocation sets must be explicit")
		}
		if !roleClassesEqual(role.Workflow.ProposableRoleClasses, []RoleClass{ClassTechnical, ClassDomain}) {
			return fmt.Errorf("workflow proposableRoleClasses must contain exactly technical and domain")
		}
		if role.Workflow.Orchestration != nil {
			spec := role.Workflow.Orchestration
			if spec.GoalMode != GoalModeNativeDurable {
				return fmt.Errorf("workflow orchestration goalMode %q is not allowed", spec.GoalMode)
			}
			if spec.CheckpointPolicy != CheckpointPolicyFileAndNativeSession {
				return fmt.Errorf("workflow orchestration checkpointPolicy %q is not allowed", spec.CheckpointPolicy)
			}
			if spec.SchedulingPolicy != SchedulingPolicyDependencyAware {
				return fmt.Errorf("workflow orchestration schedulingPolicy %q is not allowed", spec.SchedulingPolicy)
			}
			if spec.ModelRouting != nil {
				routing := spec.ModelRouting
				if !routing.ExplicitUserRouteOverridesDefaults ||
					routing.ResolutionPolicy != ModelResolutionDiscoveredAllowlistedFailClosed ||
					!routing.NativeFirst ||
					routing.SameProviderDispatch != SameProviderNativeSubagentExplicitOverride ||
					routing.CrossProviderDispatch != CrossProviderSupervisorExactRoleHeadless ||
					!routing.ParentRetainsAuthority ||
					routing.HandoffBoundary != AgentHandoffAPIVersion ||
					routing.MaxVerificationPasses != 2 || routing.MaxRepairAttempts != 1 ||
					routing.SupervisorRunplane != canonicalSupervisorRunplaneSpec() {
					return fmt.Errorf("workflow orchestration modelRouting contract is invalid")
				}
			}
		}
		if role.Workflow.Lane == WorkflowLaneOrchestration {
			if role.Workflow.Orchestration == nil || len(role.Workflow.Delegates) == 0 || len(role.Workflow.SpecialistPools) != 0 || role.Workflow.CreatesSpecialists || len(role.Workflow.InvocableSpecialistPools) != 0 {
				return fmt.Errorf("orchestration workflow must declare orchestration metadata and workflow delegates only")
			}
			if !stringSetsEqual(role.Workflow.InvocableRoleIDs, role.Workflow.Delegates) {
				return fmt.Errorf("orchestration workflow invocableRoleIds must equal delegates")
			}
			if role.CapabilityMode != CapabilityOrchestration {
				return fmt.Errorf("orchestration workflow must use orchestration-only capability")
			}
		} else {
			if role.Workflow.Orchestration != nil || len(role.Workflow.Delegates) != 0 || len(role.Workflow.InvocableRoleIDs) != 0 {
				return fmt.Errorf("workflow unit must be a peer leaf without workflow delegates or orchestration metadata")
			}
			if err := validateSpecialistPools(role.Workflow.SpecialistPools); err != nil {
				return err
			}
			if err := validateSpecialistPools(role.Workflow.InvocableSpecialistPools); err != nil {
				return fmt.Errorf("invocable pools: %w", err)
			}
			if role.CapabilityMode == CapabilityOrchestration {
				return fmt.Errorf("workflow unit may not use orchestration-only capability")
			}
		}
		if role.Workflow.CreatesSpecialists && role.Workflow.Lane != WorkflowLaneFactory {
			return fmt.Errorf("createsSpecialists is allowed only in the factory lane")
		}
		if err := validateWorkflowDelegates(role.Workflow.Delegates); err != nil {
			return err
		}
	} else if role.Workflow != nil {
		return fmt.Errorf("workflow metadata is allowed only on workflow roles")
	}
	if role.Status != StatusDefinitionReady {
		return fmt.Errorf("status %q is not allowed", role.Status)
	}
	if role.RoutingTier != RoutingStandard && role.RoutingTier != RoutingAdvanced {
		return fmt.Errorf("routingTier %q is not allowed", role.RoutingTier)
	}
	if role.CapabilityMode != CapabilityReadOnly && role.CapabilityMode != CapabilityWorkspaceWrite && role.CapabilityMode != CapabilityFactoryWrite && role.CapabilityMode != CapabilityOrchestration {
		return fmt.Errorf("capabilityMode %q is not allowed", role.CapabilityMode)
	}
	if role.Class != ClassWorkflow && role.CapabilityMode == CapabilityOrchestration {
		return fmt.Errorf("orchestration-only capability is allowed only on workflow roles")
	}
	if role.Activation.Threshold <= 0 || role.Activation.Threshold > 100 {
		return fmt.Errorf("activation threshold must be between 1 and 100")
	}
	if len(role.Activation.Files)+len(role.Activation.Dependencies)+len(role.Activation.Keywords) == 0 {
		return fmt.Errorf("activation must contain at least one signal")
	}

	if err := validateWeightedSignals("file", role.Activation.Files, normalizeFile); err != nil {
		return err
	}
	if err := validateWeightedSignals("dependency", role.Activation.Dependencies, normalizeDependency); err != nil {
		return err
	}
	if err := validateWeightedSignals("keyword", role.Activation.Keywords, normalizeText); err != nil {
		return err
	}

	globScore := 0
	for _, signal := range role.Activation.Files {
		pattern := normalizeFile(signal.Value)
		if path.IsAbs(pattern) || hasParentSegment(pattern) {
			return fmt.Errorf("file signal %q must be a relative pattern without parent traversal", signal.Value)
		}
		if _, err := path.Match(pattern, "candidate"); err != nil {
			return fmt.Errorf("file signal %q is not a valid glob: %w", signal.Value, err)
		}
		if isGlob(pattern) {
			globScore += signal.Weight
		}
	}
	if globScore >= role.Activation.Threshold {
		return fmt.Errorf("broad file-glob score %d must stay below threshold %d", globScore, role.Activation.Threshold)
	}
	for _, signal := range append(append([]WeightedSignal(nil), role.Activation.Dependencies...), role.Activation.Keywords...) {
		if globScore > 0 && signal.Weight <= globScore {
			return fmt.Errorf("exact dependency/keyword weight %d must exceed broad file-glob score %d", signal.Weight, globScore)
		}
	}

	if err := validateStrings("boundary", role.Boundaries, false); err != nil {
		return err
	}
	if err := validateStrings("tag", role.Tags, true); err != nil {
		return err
	}
	if len(role.Evidence) == 0 {
		return fmt.Errorf("evidence must not be empty")
	}
	evidenceKeys := make(map[string]struct{}, len(role.Evidence))
	for index, evidence := range role.Evidence {
		if strings.TrimSpace(evidence.Repository) == "" || strings.TrimSpace(evidence.Path) == "" || strings.TrimSpace(evidence.Detail) == "" {
			return fmt.Errorf("evidence[%d] repository, path, and detail are required", index)
		}
		if !stableIDPattern.MatchString(evidence.Repository) {
			return fmt.Errorf("evidence[%d] repository %q must be a stable identifier", index, evidence.Repository)
		}
		cleanPath := strings.TrimSpace(strings.ReplaceAll(evidence.Path, `\`, "/"))
		if path.IsAbs(cleanPath) || hasParentSegment(cleanPath) {
			return fmt.Errorf("evidence[%d] path %q must be repository-relative", index, evidence.Path)
		}
		key := evidence.Repository + "\x00" + cleanPath + "\x00" + strings.TrimSpace(evidence.Detail)
		if _, exists := evidenceKeys[key]; exists {
			return fmt.Errorf("evidence[%d] duplicates an earlier entry", index)
		}
		evidenceKeys[key] = struct{}{}
	}

	if len(role.HarnessTargets) != 3 {
		return fmt.Errorf("harnessTargets must contain antigravity, claude, and codex")
	}
	targets := make(map[HarnessTarget]struct{}, len(role.HarnessTargets))
	for _, target := range role.HarnessTargets {
		if target != HarnessAntigravity && target != HarnessClaude && target != HarnessCodex {
			return fmt.Errorf("harness target %q is not allowed", target)
		}
		if _, exists := targets[target]; exists {
			return fmt.Errorf("harness target %q is duplicated", target)
		}
		targets[target] = struct{}{}
	}
	return nil
}

func validateKnowledgeRole(role KnowledgeRole) error {
	if !stableIDPattern.MatchString(role.ID) {
		return fmt.Errorf("id must be a stable kebab-case identifier")
	}
	if strings.TrimSpace(role.Name) == "" || strings.TrimSpace(role.Summary) == "" || strings.TrimSpace(role.Instructions) == "" {
		return fmt.Errorf("name, summary, and instructions are required")
	}
	if len(role.Repositories) == 0 {
		return fmt.Errorf("at least one repository is required")
	}
	if err := validateStrings("repository", role.Repositories, false); err != nil {
		return err
	}
	for index, repo := range role.Repositories {
		if !stableIDPattern.MatchString(repo) {
			return fmt.Errorf("repository[%d] %q must be a stable identifier", index, repo)
		}
	}
	if len(role.Boundaries) > 0 {
		if err := validateStrings("boundary", role.Boundaries, false); err != nil {
			return err
		}
	}
	return nil
}

func validateWorkflowDelegates(delegates []string) error {
	seen := make(map[string]struct{}, len(delegates))
	for index, delegate := range delegates {
		if !stableIDPattern.MatchString(delegate) {
			return fmt.Errorf("workflow delegate[%d] must be a stable role id", index)
		}
		if _, exists := seen[delegate]; exists {
			return fmt.Errorf("workflow delegate[%d] duplicates %q", index, delegate)
		}
		seen[delegate] = struct{}{}
	}
	return nil
}

func validateSpecialistPools(pools []SpecialistPool) error {
	if len(pools) != 2 {
		return fmt.Errorf("workflow specialistPools must contain exactly technical and domain")
	}
	seen := make(map[SpecialistPool]struct{}, len(pools))
	for index, pool := range pools {
		switch pool {
		case SpecialistPoolTechnical, SpecialistPoolDomain:
		default:
			return fmt.Errorf("workflow specialistPools[%d] %q is not allowed", index, pool)
		}
		if _, exists := seen[pool]; exists {
			return fmt.Errorf("workflow specialistPools[%d] duplicates %q", index, pool)
		}
		seen[pool] = struct{}{}
	}
	if _, exists := seen[SpecialistPoolTechnical]; !exists {
		return fmt.Errorf("workflow specialistPools must include technical")
	}
	if _, exists := seen[SpecialistPoolDomain]; !exists {
		return fmt.Errorf("workflow specialistPools must include domain")
	}
	return nil
}

func roleClassesEqual(left, right []RoleClass) bool {
	if left == nil || right == nil || len(left) != len(right) {
		return false
	}
	wanted := make(map[RoleClass]int, len(right))
	for _, value := range right {
		wanted[value]++
	}
	for _, value := range left {
		if wanted[value] == 0 {
			return false
		}
		wanted[value]--
	}
	return true
}

func stringSetsEqual(left, right []string) bool {
	if left == nil || right == nil || len(left) != len(right) {
		return false
	}
	wanted := make(map[string]int, len(right))
	for _, value := range right {
		wanted[value]++
	}
	for _, value := range left {
		if wanted[value] == 0 {
			return false
		}
		wanted[value]--
	}
	return true
}

func validateWeightedSignals(kind string, signals []WeightedSignal, normalize func(string) string) error {
	seen := make(map[string]struct{}, len(signals))
	for index, signal := range signals {
		value := normalize(signal.Value)
		if value == "" {
			return fmt.Errorf("%s signal[%d] value is required", kind, index)
		}
		if strings.ContainsRune(value, '\x00') {
			return fmt.Errorf("%s signal[%d] contains a NUL byte", kind, index)
		}
		if signal.Weight <= 0 || signal.Weight > 100 {
			return fmt.Errorf("%s signal[%d] weight must be between 1 and 100", kind, index)
		}
		if _, exists := seen[value]; exists {
			return fmt.Errorf("%s signal[%d] duplicates %q", kind, index, value)
		}
		seen[value] = struct{}{}
	}
	return nil
}

func validateStrings(kind string, values []string, normalizeAsText bool) error {
	if len(values) == 0 {
		return fmt.Errorf("%ss must not be empty", kind)
	}
	seen := make(map[string]struct{}, len(values))
	for index, value := range values {
		key := strings.TrimSpace(value)
		if normalizeAsText {
			key = normalizeText(value)
		}
		if key == "" {
			return fmt.Errorf("%s[%d] must not be empty", kind, index)
		}
		if _, exists := seen[key]; exists {
			return fmt.Errorf("%s[%d] duplicates an earlier value", kind, index)
		}
		seen[key] = struct{}{}
	}
	return nil
}

func normalizeDocument(document *Document) {
	document.APIVersion = strings.TrimSpace(document.APIVersion)
	document.CatalogVersion = strings.TrimSpace(document.CatalogVersion)
	document.GeneratedAt = strings.TrimSpace(document.GeneratedAt)
	document.Source.Repository = strings.TrimSpace(document.Source.Repository)
	document.Source.PlanningCommit = strings.TrimSpace(document.Source.PlanningCommit)
	document.Source.EvidenceBasis = strings.TrimSpace(document.Source.EvidenceBasis)
	for index := range document.AuthorityProfiles {
		document.AuthorityProfiles[index].ID = strings.TrimSpace(document.AuthorityProfiles[index].ID)
	}
	sort.Slice(document.AuthorityProfiles, func(left, right int) bool {
		return document.AuthorityProfiles[left].ID < document.AuthorityProfiles[right].ID
	})

	for index := range document.Roles {
		role := &document.Roles[index]
		role.Name = strings.TrimSpace(role.Name)
		role.Summary = strings.TrimSpace(role.Summary)
		role.Instructions = strings.TrimSpace(role.Instructions)
		normalizeRules(role.Activation.Files, normalizeFile)
		normalizeRules(role.Activation.Dependencies, normalizeDependency)
		normalizeRules(role.Activation.Keywords, normalizeText)
		sortRules(role.Activation.Files)
		sortRules(role.Activation.Dependencies)
		sortRules(role.Activation.Keywords)
		for item := range role.Boundaries {
			role.Boundaries[item] = strings.TrimSpace(role.Boundaries[item])
		}
		sort.Strings(role.Boundaries)
		for item := range role.Tags {
			role.Tags[item] = normalizeText(role.Tags[item])
		}
		sort.Strings(role.Tags)
		for item := range role.Evidence {
			role.Evidence[item].Repository = strings.TrimSpace(role.Evidence[item].Repository)
			role.Evidence[item].Path = strings.TrimSpace(strings.ReplaceAll(role.Evidence[item].Path, `\`, "/"))
			role.Evidence[item].Detail = strings.TrimSpace(role.Evidence[item].Detail)
		}
		sort.Slice(role.Evidence, func(left, right int) bool {
			a, b := role.Evidence[left], role.Evidence[right]
			if a.Repository != b.Repository {
				return a.Repository < b.Repository
			}
			if a.Path != b.Path {
				return a.Path < b.Path
			}
			return a.Detail < b.Detail
		})
		sort.Slice(role.HarnessTargets, func(left, right int) bool {
			return role.HarnessTargets[left] < role.HarnessTargets[right]
		})
		if role.Workflow != nil {
			for item := range role.Workflow.Stages {
				role.Workflow.Stages[item] = strings.TrimSpace(role.Workflow.Stages[item])
			}
			for item := range role.Workflow.Delegates {
				role.Workflow.Delegates[item] = strings.TrimSpace(role.Workflow.Delegates[item])
			}
			for item := range role.Workflow.InvocableRoleIDs {
				role.Workflow.InvocableRoleIDs[item] = strings.TrimSpace(role.Workflow.InvocableRoleIDs[item])
			}
			sort.SliceStable(role.Workflow.SpecialistPools, func(left, right int) bool {
				return role.Workflow.SpecialistPools[left] == SpecialistPoolTechnical && role.Workflow.SpecialistPools[right] == SpecialistPoolDomain
			})
			sort.SliceStable(role.Workflow.InvocableSpecialistPools, func(left, right int) bool {
				return role.Workflow.InvocableSpecialistPools[left] == SpecialistPoolTechnical && role.Workflow.InvocableSpecialistPools[right] == SpecialistPoolDomain
			})
			sort.Slice(role.Workflow.ProposableRoleClasses, func(left, right int) bool {
				return role.Workflow.ProposableRoleClasses[left] < role.Workflow.ProposableRoleClasses[right]
			})
			sort.Strings(role.Workflow.Delegates)
			sort.Strings(role.Workflow.InvocableRoleIDs)
		}
	}

	sort.Slice(document.Roles, func(left, right int) bool {
		a, b := document.Roles[left], document.Roles[right]
		if a.Class != b.Class {
			return a.Class < b.Class
		}
		leftName, rightName := normalizeText(a.Name), normalizeText(b.Name)
		if leftName != rightName {
			return leftName < rightName
		}
		return a.ID < b.ID
	})

	for index := range document.KnowledgeRoles {
		kr := &document.KnowledgeRoles[index]
		kr.ID = strings.TrimSpace(kr.ID)
		kr.Name = strings.TrimSpace(kr.Name)
		kr.Summary = strings.TrimSpace(kr.Summary)
		kr.Instructions = strings.TrimSpace(kr.Instructions)
		for item := range kr.Boundaries {
			kr.Boundaries[item] = strings.TrimSpace(kr.Boundaries[item])
		}
		sort.Strings(kr.Boundaries)
		for item := range kr.Repositories {
			kr.Repositories[item] = strings.TrimSpace(kr.Repositories[item])
		}
		sort.Strings(kr.Repositories)
	}
	sort.Slice(document.KnowledgeRoles, func(left, right int) bool {
		return document.KnowledgeRoles[left].ID < document.KnowledgeRoles[right].ID
	})

	document.Counts = Counts{Total: len(document.Roles)}
	for _, role := range document.Roles {
		switch role.Class {
		case ClassWorkflow:
			document.Counts.Workflow++
		case ClassTechnical:
			document.Counts.Technical++
		case ClassDomain:
			document.Counts.Domain++
		}
		if role.Status == StatusDefinitionReady {
			document.Counts.DefinitionReady++
		}
	}
}

func normalizeRules(rules []WeightedSignal, normalize func(string) string) {
	for index := range rules {
		rules[index].Value = normalize(rules[index].Value)
	}
}

func sortRules(rules []WeightedSignal) {
	sort.Slice(rules, func(left, right int) bool {
		if rules[left].Value != rules[right].Value {
			return rules[left].Value < rules[right].Value
		}
		return rules[left].Weight < rules[right].Weight
	})
}

// Select scores only the explicit Signals supplied by the caller and returns
// above-threshold matches ordered by descending score and then stable role ID.
func Select(document Document, signals Signals) []Match {
	normalized := normalizeInput(signals)
	matches := make([]Match, 0)
	for _, role := range document.Roles {
		score, reasons := scoreRole(role, normalized)
		if score < role.Activation.Threshold {
			continue
		}
		matches = append(matches, Match{RoleID: role.ID, Score: score, Reasons: reasons})
	}
	sort.Slice(matches, func(left, right int) bool {
		if matches[left].Score != matches[right].Score {
			return matches[left].Score > matches[right].Score
		}
		return matches[left].RoleID < matches[right].RoleID
	})
	return matches
}

func scoreRole(role Role, signals Signals) (int, []string) {
	score := 0
	reasons := make([]string, 0)

	for _, rule := range role.Activation.Dependencies {
		if containsSorted(signals.Dependencies, normalizeDependency(rule.Value)) {
			score += rule.Weight
			reasons = append(reasons, fmt.Sprintf("dependency %q (+%d)", normalizeDependency(rule.Value), rule.Weight))
		}
	}
	for _, rule := range role.Activation.Keywords {
		value := normalizeText(rule.Value)
		if matched := firstKeywordMatch(signals.Keywords, value); matched != "" {
			score += rule.Weight
			if matched == value {
				reasons = append(reasons, fmt.Sprintf("keyword %q (+%d)", value, rule.Weight))
			} else {
				reasons = append(reasons, fmt.Sprintf("keyword %q in %q (+%d)", value, matched, rule.Weight))
			}
		}
	}
	for _, rule := range role.Activation.Files {
		pattern := normalizeFile(rule.Value)
		if isGlob(pattern) {
			continue
		}
		if containsSorted(signals.Files, pattern) {
			score += rule.Weight
			reasons = append(reasons, fmt.Sprintf("file %q (+%d)", pattern, rule.Weight))
		}
	}
	for _, rule := range role.Activation.Files {
		pattern := normalizeFile(rule.Value)
		if !isGlob(pattern) {
			continue
		}
		if matched := firstFileMatch(signals.Files, pattern); matched != "" {
			score += rule.Weight
			reasons = append(reasons, fmt.Sprintf("file glob %q matched %q (+%d)", pattern, matched, rule.Weight))
		}
	}
	return score, reasons
}

func normalizeInput(signals Signals) Signals {
	return Signals{
		Files:        normalizeUnique(signals.Files, normalizeFile),
		Dependencies: normalizeUnique(signals.Dependencies, normalizeDependency),
		Keywords:     normalizeUnique(signals.Keywords, normalizeText),
	}
}

func normalizeUnique(values []string, normalize func(string) string) []string {
	unique := make(map[string]struct{}, len(values))
	for _, value := range values {
		if normalized := normalize(value); normalized != "" {
			unique[normalized] = struct{}{}
		}
	}
	result := make([]string, 0, len(unique))
	for value := range unique {
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}

func normalizeFile(value string) string {
	value = strings.ToLower(strings.TrimSpace(strings.ReplaceAll(value, `\`, "/")))
	for strings.HasPrefix(value, "./") {
		value = strings.TrimPrefix(value, "./")
	}
	if value == "" {
		return ""
	}
	return path.Clean(value)
}

func normalizeDependency(value string) string {
	return strings.ToLower(strings.TrimSpace(value))
}

func normalizeText(value string) string {
	var builder strings.Builder
	space := true
	for _, current := range strings.ToLower(strings.TrimSpace(value)) {
		if unicode.IsLetter(current) || unicode.IsDigit(current) || current == '+' || current == '#' {
			builder.WriteRune(current)
			space = false
			continue
		}
		if !space {
			builder.WriteByte(' ')
			space = true
		}
	}
	return strings.TrimSpace(builder.String())
}

func containsSorted(values []string, wanted string) bool {
	index := sort.SearchStrings(values, wanted)
	return index < len(values) && values[index] == wanted
}

func firstKeywordMatch(values []string, phrase string) string {
	wanted := " " + phrase + " "
	for _, value := range values {
		if strings.Contains(" "+value+" ", wanted) {
			return value
		}
	}
	return ""
}

func firstFileMatch(values []string, pattern string) string {
	for _, value := range values {
		if matchFile(pattern, value) {
			return value
		}
	}
	return ""
}

func matchFile(pattern, value string) bool {
	if matched, _ := path.Match(pattern, value); matched {
		return true
	}
	if !strings.Contains(pattern, "/") {
		if matched, _ := path.Match(pattern, path.Base(value)); matched {
			return true
		}
	}
	if !strings.HasPrefix(pattern, "**/") {
		return false
	}
	tail := strings.TrimPrefix(pattern, "**/")
	if matched, _ := path.Match(tail, value); matched {
		return true
	}
	for offset := strings.IndexByte(value, '/'); offset >= 0; offset = nextSlash(value, offset+1) {
		if matched, _ := path.Match(tail, value[offset+1:]); matched {
			return true
		}
	}
	return false
}

func nextSlash(value string, start int) int {
	if start >= len(value) {
		return -1
	}
	relative := strings.IndexByte(value[start:], '/')
	if relative < 0 {
		return -1
	}
	return start + relative
}

func isGlob(value string) bool {
	return strings.ContainsAny(value, "*?[")
}

func hasParentSegment(value string) bool {
	for _, segment := range strings.Split(value, "/") {
		if segment == ".." {
			return true
		}
	}
	return false
}
