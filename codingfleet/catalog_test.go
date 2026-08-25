package codingfleet

import (
	"encoding/json"
	"reflect"
	"sort"
	"strings"
	"testing"

	"github.com/anvil008/swarm-coder/harness-agents/canonical"
)

func TestLoadCatalogInventoryAndDerivedCounts(t *testing.T) {
	document := mustLoad(t)
	if got, want := document.APIVersion, APIVersion; got != want {
		t.Fatalf("APIVersion = %q, want %q", got, want)
	}
	if got, want := document.Counts, (Counts{Total: 15, Workflow: 5, Technical: 8, Domain: 2, DefinitionReady: 15}); got != want {
		t.Fatalf("Counts = %+v, want %+v", got, want)
	}

	wantWorkflow := []string{
		workflowCodeReviewID,
		workflowCodingOrchestratorID,
		workflowExecutorID,
		workflowPlannerID,
		workflowResearchID,
	}
	gotWorkflow := make([]string, 0, len(wantWorkflow))
	for _, role := range document.Roles {
		if role.Class == ClassWorkflow {
			gotWorkflow = append(gotWorkflow, role.ID)
		}
		if role.Status != StatusDefinitionReady || role.Instructions == "" {
			t.Errorf("role %q is not definition-ready with instructions", role.ID)
		}
		if len(role.Boundaries) == 0 || len(role.Evidence) == 0 || len(role.Tags) == 0 {
			t.Errorf("role %q lacks boundary, evidence, or tag metadata", role.ID)
		}
		if len(role.HarnessTargets) != 3 {
			t.Errorf("role %q harness targets = %v", role.ID, role.HarnessTargets)
		}
	}
	sort.Strings(gotWorkflow)
	sort.Strings(wantWorkflow)
	if !reflect.DeepEqual(gotWorkflow, wantWorkflow) {
		t.Fatalf("workflow IDs = %v, want %v", gotWorkflow, wantWorkflow)
	}

	var source map[string]json.RawMessage
	if err := json.Unmarshal(canonical.Bytes(), &source); err != nil {
		t.Fatalf("decode canonical source: %v", err)
	}
	if _, hardCoded := source["counts"]; hardCoded {
		t.Error("canonical source must omit derived counts")
	}
}

func TestCanonicalFlatWorkflowTopology(t *testing.T) {
	document := mustLoad(t)
	orchestrator := roleByID(document.Roles, workflowCodingOrchestratorID)
	if orchestrator.Name != "Coding Orchestrator Agent" || orchestrator.CapabilityMode != CapabilityOrchestration || orchestrator.Workflow == nil {
		t.Fatalf("orchestrator = %+v", orchestrator)
	}
	if got, want := len(orchestrator.Workflow.Delegates), len(workflowUnitContracts); got != want {
		t.Fatalf("orchestrator delegates = %d, want %d", got, want)
	}
	if len(orchestrator.Workflow.SpecialistPools) != 0 {
		t.Fatalf("orchestrator specialist pools = %v, want none", orchestrator.Workflow.SpecialistPools)
	}
	wantOrchestration := &OrchestrationSpec{
		GoalMode:            GoalModeNativeDurable,
		CheckpointPolicy:    CheckpointPolicyFileAndNativeSession,
		SchedulingPolicy:    SchedulingPolicyDependencyAware,
		ProactiveDelegation: true,
		CompletionAuthority: true,
		ModelRouting: &ModelRoutingSpec{
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
		},
	}
	if !reflect.DeepEqual(orchestrator.Workflow.Orchestration, wantOrchestration) || orchestrator.Workflow.MaxParallel != codingOrchestratorMaxParallel {
		t.Fatalf("orchestrator workflow = %+v", orchestrator.Workflow)
	}

	wantPools := []SpecialistPool{SpecialistPoolTechnical, SpecialistPoolDomain}
	wantParallel := map[string]int{
		workflowResearchID:   10,
		workflowPlannerID:    10,
		workflowExecutorID:   20,
		workflowCodeReviewID: 10,
	}
	for _, contract := range workflowUnitContracts {
		if contract.MaxParallel != wantParallel[contract.RoleID] {
			t.Errorf("workflow unit %q maxParallel = %d, want %d", contract.RoleID, contract.MaxParallel, wantParallel[contract.RoleID])
		}
		unit := roleByID(document.Roles, contract.RoleID)
		if unit.Name != contract.Name || unit.Class != ClassWorkflow || unit.CapabilityMode != contract.CapabilityMode || unit.Workflow == nil {
			t.Errorf("workflow unit %q = %+v", contract.RoleID, unit)
			continue
		}
		if unit.Workflow.Lane != contract.Lane || unit.Workflow.MaxParallel != contract.MaxParallel || unit.Workflow.CreatesSpecialists != contract.CreatesSpecialists {
			t.Errorf("workflow unit %q contract = %+v", contract.RoleID, unit.Workflow)
		}
		if len(unit.Workflow.Delegates) != 0 || unit.Workflow.Orchestration != nil {
			t.Errorf("workflow unit %q is not a flat peer leaf: %+v", contract.RoleID, unit.Workflow)
		}
		if !reflect.DeepEqual(unit.Workflow.SpecialistPools, wantPools) {
			t.Errorf("workflow unit %q pools = %v, want %v", contract.RoleID, unit.Workflow.SpecialistPools, wantPools)
		}
		if !workflowDelegatesTo(orchestrator, contract.RoleID) {
			t.Errorf("orchestrator does not delegate to %q", contract.RoleID)
		}
	}
}

func TestFlatWorkflowTopologyRejectsDrift(t *testing.T) {
	tests := []struct {
		name       string
		mutate     func([]Role)
		wantErrSub string
	}{
		{
			name: "orchestrator loses durability",
			mutate: func(roles []Role) {
				roleByIDPtr(roles, workflowCodingOrchestratorID).Workflow.Orchestration = nil
			},
			wantErrSub: "orchestration =",
		},
		{
			name: "orchestrator loses model routing",
			mutate: func(roles []Role) {
				roleByIDPtr(roles, workflowCodingOrchestratorID).Workflow.Orchestration.ModelRouting = nil
			},
			wantErrSub: "model routing",
		},
		{
			name: "orchestrator permits silent substitution",
			mutate: func(roles []Role) {
				roleByIDPtr(roles, workflowCodingOrchestratorID).Workflow.Orchestration.ModelRouting.ResolutionPolicy = "best-effort"
			},
			wantErrSub: "model routing =",
		},
		{
			name: "orchestrator changes supervisor binary",
			mutate: func(roles []Role) {
				roleByIDPtr(roles, workflowCodingOrchestratorID).Workflow.Orchestration.ModelRouting.SupervisorRunplane.Binary = "/tmp/magic-runplane"
			},
			wantErrSub: "model routing =",
		},
		{
			name: "orchestrator reaches specialist pool",
			mutate: func(roles []Role) {
				roleByIDPtr(roles, workflowCodingOrchestratorID).Workflow.SpecialistPools = []SpecialistPool{SpecialistPoolTechnical, SpecialistPoolDomain}
			},
			wantErrSub: "must own only the orchestration lane",
		},
		{
			name: "unit owns another workflow",
			mutate: func(roles []Role) {
				roleByIDPtr(roles, workflowPlannerID).Workflow.Delegates = []string{workflowExecutorID}
			},
			wantErrSub: "must be a peer leaf",
		},
		{
			name: "executor becomes read only",
			mutate: func(roles []Role) {
				roleByIDPtr(roles, workflowExecutorID).CapabilityMode = CapabilityReadOnly
			},
			wantErrSub: "does not match its peer-layer contract",
		},
		{
			name: "read-only unit claims target-project writes",
			mutate: func(roles []Role) {
				roleByIDPtr(roles, workflowPlannerID).CapabilityMode = CapabilityWorkspaceWrite
			},
			wantErrSub: "does not match its peer-layer contract",
		},
		{
			name: "non-factory unit claims factory writes",
			mutate: func(roles []Role) {
				roleByIDPtr(roles, workflowExecutorID).CapabilityMode = CapabilityFactoryWrite
			},
			wantErrSub: "may not use factory-write capability",
		},
		{
			name: "executor claims specialist creation",
			mutate: func(roles []Role) {
				roleByIDPtr(roles, workflowExecutorID).Workflow.CreatesSpecialists = true
			},
			wantErrSub: "creation contract is invalid",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			document := mustLoad(t)
			test.mutate(document.Roles)
			if err := validateFleetTopology(document.Roles); err == nil || !strings.Contains(err.Error(), test.wantErrSub) {
				t.Fatalf("validateFleetTopology() error = %v, want substring %q", err, test.wantErrSub)
			}
		})
	}
}

func TestDecodeCatalogValidation(t *testing.T) {
	tests := []struct {
		name       string
		mutate     func(*sourceDocument)
		wantErrSub string
	}{
		{name: "api version", mutate: func(source *sourceDocument) { source.APIVersion = "v0" }, wantErrSub: "apiVersion"},
		{name: "class enum", mutate: func(source *sourceDocument) { source.Roles[0].Class = "general" }, wantErrSub: "class"},
		{
			name:       "workflow metadata required",
			mutate:     func(source *sourceDocument) { source.Roles[0].Class = ClassWorkflow },
			wantErrSub: "workflow metadata",
		},
		{
			name: "workflow delegate must exist",
			mutate: func(source *sourceDocument) {
				role := &source.Roles[0]
				role.Class = ClassWorkflow
				role.CapabilityMode = CapabilityOrchestration
				role.Workflow = &WorkflowSpec{
					Stages: []string{"Orchestrate"}, Delegates: []string{"workflow-missing"},
					ProposableRoleClasses: []RoleClass{ClassTechnical, ClassDomain}, InvocableRoleIDs: []string{"workflow-missing"}, InvocableSpecialistPools: []SpecialistPool{},
					Lane: WorkflowLaneOrchestration, MaxParallel: 1,
					Orchestration: &OrchestrationSpec{GoalMode: GoalModeNativeDurable, CheckpointPolicy: CheckpointPolicyFileAndNativeSession, SchedulingPolicy: SchedulingPolicyDependencyAware},
				}
			},
			wantErrSub: "does not exist",
		},
		{
			name: "workflow unit missing shared pools",
			mutate: func(source *sourceDocument) {
				role := &source.Roles[0]
				role.Class = ClassWorkflow
				role.CapabilityMode = CapabilityReadOnly
				role.Workflow = testUnitWorkflowSpec([]SpecialistPool{}, 1, false)
			},
			wantErrSub: "specialistPools must contain exactly technical and domain",
		},
		{
			name: "workflow unit duplicate pool",
			mutate: func(source *sourceDocument) {
				role := &source.Roles[0]
				role.Class = ClassWorkflow
				role.CapabilityMode = CapabilityReadOnly
				role.Workflow = testUnitWorkflowSpec([]SpecialistPool{SpecialistPoolTechnical, SpecialistPoolTechnical}, 1, false)
			},
			wantErrSub: "duplicates",
		},
		{
			name: "workflow parallelism exceeds fleet ceiling",
			mutate: func(source *sourceDocument) {
				role := &source.Roles[0]
				role.Class = ClassWorkflow
				role.CapabilityMode = CapabilityReadOnly
				role.Workflow = testUnitWorkflowSpec([]SpecialistPool{SpecialistPoolTechnical, SpecialistPoolDomain}, 26, false)
			},
			wantErrSub: "between 1 and 25",
		},
		{
			name: "creates specialists outside factory",
			mutate: func(source *sourceDocument) {
				role := &source.Roles[0]
				role.Class = ClassWorkflow
				role.CapabilityMode = CapabilityReadOnly
				role.Workflow = testUnitWorkflowSpec([]SpecialistPool{SpecialistPoolTechnical, SpecialistPoolDomain}, 1, true)
			},
			wantErrSub: "createsSpecialists",
		},
		{name: "status enum", mutate: func(source *sourceDocument) { source.Roles[0].Status = "running" }, wantErrSub: "status"},
		{
			name: "duplicate id",
			mutate: func(source *sourceDocument) {
				duplicate := source.Roles[0]
				duplicate.Name = "Duplicate role"
				source.Roles = append(source.Roles, duplicate)
			},
			wantErrSub: "duplicate id",
		},
		{name: "instructions required", mutate: func(source *sourceDocument) { source.Roles[0].Instructions = "" }, wantErrSub: "instructions"},
		{
			name:       "activation required",
			mutate:     func(source *sourceDocument) { source.Roles[0].Activation = Activation{Threshold: 7} },
			wantErrSub: "activation",
		},
		{
			name: "glob-only threshold rejected",
			mutate: func(source *sourceDocument) {
				source.Roles[0].Activation = Activation{Threshold: 7, Files: []WeightedSignal{{Value: "**/*.go", Weight: 7}}}
			},
			wantErrSub: "file-glob score",
		},
		{name: "boundaries required", mutate: func(source *sourceDocument) { source.Roles[0].Boundaries = nil }, wantErrSub: "boundary"},
		{name: "evidence required", mutate: func(source *sourceDocument) { source.Roles[0].Evidence = nil }, wantErrSub: "evidence"},
		{name: "capability mode enum", mutate: func(source *sourceDocument) { source.Roles[0].CapabilityMode = "unrestricted" }, wantErrSub: "capabilityMode"},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			source := validTestSource()
			test.mutate(&source)
			data, err := json.Marshal(source)
			if err != nil {
				t.Fatalf("marshal source: %v", err)
			}
			_, err = decodeCatalog(data)
			if err == nil || !strings.Contains(err.Error(), test.wantErrSub) {
				t.Fatalf("decodeCatalog() error = %v, want substring %q", err, test.wantErrSub)
			}
		})
	}
}

func TestDecodeCatalogRejectsStoredCountsAndCanonicalizesOrder(t *testing.T) {
	source := validTestSource()
	second := source.Roles[0]
	second.ID = "technical-alpha"
	second.Name = "Alpha"
	source.Roles = append(source.Roles, second)
	data, err := json.Marshal(source)
	if err != nil {
		t.Fatalf("marshal source: %v", err)
	}
	document, err := decodeCatalog(data)
	if err != nil {
		t.Fatalf("decodeCatalog() error = %v", err)
	}
	if got, want := []string{document.Roles[0].ID, document.Roles[1].ID}, []string{"technical-alpha", "technical-test"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("role order = %v, want %v", got, want)
	}
	if got, want := document.Counts, (Counts{Total: 2, Technical: 2, DefinitionReady: 2}); got != want {
		t.Fatalf("counts = %+v, want %+v", got, want)
	}
	var raw map[string]any
	if err := json.Unmarshal(data, &raw); err != nil {
		t.Fatalf("unmarshal source: %v", err)
	}
	raw["counts"] = map[string]any{"total": 99}
	withCounts, err := json.Marshal(raw)
	if err != nil {
		t.Fatalf("marshal stored counts source: %v", err)
	}
	if _, err := decodeCatalog(withCounts); err == nil || !strings.Contains(err.Error(), "unknown field \"counts\"") {
		t.Fatalf("decode stored counts error = %v", err)
	}
}

func TestSelectRepresentativeSignals(t *testing.T) {
	document := mustLoad(t)
	tests := []struct {
		name      string
		signals   Signals
		wantID    string
		wantScore int
	}{
		{name: "go files", signals: Signals{Files: []string{" ./GO.MOD ", `CMD\MAIN.GO`}}, wantID: "toolchain-go", wantScore: 12},
		{name: "react files", signals: Signals{Files: []string{"package.json", "src/App.tsx"}}, wantID: "toolchain-web", wantScore: 12},
		{name: "postgres dependency", signals: Signals{Dependencies: []string{"PSYCOPG"}}, wantID: "toolchain-database", wantScore: 9},
		{name: "proxmox keyword", signals: Signals{Keywords: []string{"Proxmox"}}, wantID: "env-homelab", wantScore: 9},
		{name: "coding orchestrator", signals: Signals{Keywords: []string{"coding orchestrator"}}, wantID: workflowCodingOrchestratorID, wantScore: 10},
		{name: "realtime dependency", signals: Signals{Dependencies: []string{"golang.org/x/net"}}, wantID: "toolchain-go", wantScore: 9},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			matches := Select(document, test.signals)
			if len(matches) == 0 {
				t.Fatal("Select() returned no matches")
			}
			if got := matches[0]; got.RoleID != test.wantID || got.Score != test.wantScore {
				t.Fatalf("first match = %+v, want role=%q score=%d; all=%+v", got, test.wantID, test.wantScore, matches)
			}
		})
	}
}

func TestSelectDeterministicScoreOrderAndReasons(t *testing.T) {
	document := mustLoad(t)
	first := Select(document, Signals{Files: []string{"Agents/Foo_Agent.go", "./GO.MOD", "Cargo.toml"}, Dependencies: []string{" GOLANG.ORG/X/NET "}, Keywords: []string{" GOLANG "}})
	second := Select(document, Signals{Files: []string{"go.mod", "AGENTS\\FOO_AGENT.GO", "Cargo.toml"}, Dependencies: []string{"golang.org/x/net"}, Keywords: []string{"golang"}})
	if !reflect.DeepEqual(first, second) {
		t.Fatalf("normalized results differ:\n%+v\n%+v", first, second)
	}
	if len(first) < 2 || first[0].RoleID != "toolchain-go" || first[0].Score != 30 || first[1].RoleID != "toolchain-rust" || first[1].Score != 7 {
		t.Fatalf("match ordering/scores = %+v", first)
	}
}

func TestSelectThresholdAndBroadSignals(t *testing.T) {
	document := mustLoad(t)
	if matches := Select(document, Signals{Files: []string{"main.go", "src/app.tsx", "tests/widget_test.go"}}); len(matches) != 0 {
		t.Fatalf("broad file globs crossed a threshold: %+v", matches)
	}
	strong := Select(document, Signals{Files: []string{"main.go", "src/app.tsx"}, Dependencies: []string{"react"}})
	if len(strong) == 0 || strong[0].RoleID != "toolchain-web" || strong[0].Score != 14 {
		t.Fatalf("strong dependency did not outrank broad globs: %+v", strong)
	}
	for _, role := range document.Roles {
		globScore := 0
		for _, signal := range role.Activation.Files {
			if isGlob(signal.Value) {
				globScore += signal.Weight
			}
		}
		if globScore >= role.Activation.Threshold {
			t.Errorf("role %q broad glob score %d reaches threshold %d", role.ID, globScore, role.Activation.Threshold)
		}
	}
}

func validTestSource() sourceDocument {
	var canonicalSource sourceDocument
	if err := json.Unmarshal(canonical.Bytes(), &canonicalSource); err != nil {
		panic(err)
	}
	return sourceDocument{
		APIVersion: APIVersion, CatalogVersion: "test-v1", GeneratedAt: "2026-08-13T00:00:00Z",
		Source:            SourceMetadata{Repository: "test", PlanningCommit: "0123456789012345678901234567890123456789", EvidenceBasis: "test fixture"},
		AuthorityProfiles: canonicalSource.AuthorityProfiles,
		Roles: []Role{{
			ID: "technical-test", Name: "Test", Class: ClassTechnical, Summary: "Tests validation.", Status: StatusDefinitionReady,
			Instructions: "Validate the fixture.",
			Activation:   Activation{Threshold: 7, Files: []WeightedSignal{{Value: "**/*.go", Weight: 2}}, Keywords: []WeightedSignal{{Value: "test fixture", Weight: 8}}},
			Boundaries:   []string{"Do not escape the fixture."}, Evidence: []Evidence{{Repository: "swarm", Path: "go.mod", Detail: "Test evidence."}}, Tags: []string{"test"},
			RoutingTier: RoutingStandard, CapabilityMode: CapabilityWorkspaceWrite, HarnessTargets: []HarnessTarget{HarnessAntigravity, HarnessClaude, HarnessCodex},
		}},
	}
}

func testUnitWorkflowSpec(pools []SpecialistPool, maxParallel int, creates bool) *WorkflowSpec {
	return &WorkflowSpec{
		Stages: []string{"Inspect"}, Delegates: []string{}, SpecialistPools: pools,
		ProposableRoleClasses: []RoleClass{ClassTechnical, ClassDomain}, InvocableRoleIDs: []string{},
		InvocableSpecialistPools: []SpecialistPool{SpecialistPoolTechnical, SpecialistPoolDomain},
		Lane:                     WorkflowLaneExecution, CreatesSpecialists: creates, MaxParallel: maxParallel,
	}
}

func mustLoad(t *testing.T) Document {
	t.Helper()
	document, err := Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	return document
}

func roleByID(roles []Role, roleID string) Role {
	for _, role := range roles {
		if role.ID == roleID {
			return role
		}
	}
	return Role{}
}

func roleByIDPtr(roles []Role, roleID string) *Role {
	for index := range roles {
		if roles[index].ID == roleID {
			return &roles[index]
		}
	}
	return nil
}
