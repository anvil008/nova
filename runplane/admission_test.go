package runplane

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/anvil008/swarm-coder/codingfleet"
	"github.com/anvil008/swarm-coder/controlplane"
)

func strictTestRoute(repo string) Route {
	return Route{
		SourceHarness: HarnessCodex, TargetHarness: HarnessClaude,
		Provider: "anthropic", Family: "claude", ExactModel: "opus-exact", Effort: "high",
		CanonicalRoleID: "workflow-executor", ParentRoleID: "workflow-coding-orchestrator",
		ParentGoalID: "goal-1", AssignmentID: "assignment-1", GenerationID: "generation-1", GenerationNumber: 1,
		DispatchID: "dispatch-1", ParentDispatchID: "dispatch-root", CapabilityMode: ModeWorkspaceWrite,
		RepositoryRoot: repo, RepositoryDigest: controlplaneDigest("repo"), FileOwnership: []string{"runplane"}, SymbolOwnership: []controlplane.SymbolClaim{},
		Budget:   controlplane.BudgetAmount{Delegates: 1, Writers: 1, Tokens: 10_000, DurationSeconds: 300},
		Limits:   codingfleet.AgentHandoffLimits{MaxMessages: 100, MaxDurationSeconds: 300, MaxChildren: 1},
		Decision: controlplane.RouteInherit,
		Evidence: EvidenceContract{RequiredChecks: []string{"unit"}, RequiredArtifacts: []string{"patch"}},
	}
}

func strictTestCapability(observed time.Time) Capability {
	return Capability{
		Harness: HarnessClaude, Available: true, Models: []string{"opus-exact"}, Efforts: []string{"high"},
		ModelEfforts: []ModelEffort{{Provider: "anthropic", Family: "claude", Model: "opus-exact", Effort: "high", Reference: "exact"}},
		Roles:        []string{"anvil-wf-executor"}, ObservedAt: observed,
	}
}

func TestBuildControlPlaneAdmissionValidatesAgainstLiveCatalogAndCapability(t *testing.T) {
	repo := testRepository(t)
	roots := testDefinitionRoots(t)
	writeDefinition(t, roots, HarnessClaude, "workflow-executor", "", "")
	observed := time.Date(2026, 8, 23, 20, 0, 0, 0, time.UTC)
	capability := strictTestCapability(observed)
	route := strictTestRoute(repo)
	admission, err := BuildControlPlaneAdmission(route, capability, observed.Add(time.Minute))
	if err != nil {
		t.Fatal(err)
	}
	request := StartRequest{Route: route, ControlPlane: &admission, Brief: "implement the bounded task"}
	admitted, err := admitRoute(request, capability, roots)
	if err != nil {
		t.Fatal(err)
	}
	if admitted.RoleDigest != admission.Authority.RoleDigest || admitted.Route.Provider != "anthropic" {
		t.Fatalf("admission drift: %+v", admitted)
	}
}

func TestControlPlaneAdmissionRejectsTamperAndStaleObservation(t *testing.T) {
	repo := testRepository(t)
	roots := testDefinitionRoots(t)
	writeDefinition(t, roots, HarnessClaude, "workflow-executor", "", "")
	observed := time.Date(2026, 8, 23, 20, 0, 0, 0, time.UTC)
	capability := strictTestCapability(observed)
	route := strictTestRoute(repo)
	admission, err := BuildControlPlaneAdmission(route, capability, observed.Add(time.Minute))
	if err != nil {
		t.Fatal(err)
	}
	request := StartRequest{Route: route, ControlPlane: &admission, Brief: "implement"}
	request.ControlPlane.Authority.Digest = controlplaneDigest("forged")
	if _, err := admitRoute(request, capability, roots); err == nil || !strings.Contains(err.Error(), "digest") {
		t.Fatalf("forged authority error = %v", err)
	}
	admission, err = BuildControlPlaneAdmission(route, capability, observed.Add(time.Minute))
	if err != nil {
		t.Fatal(err)
	}
	request.ControlPlane = &admission
	request.Route.Effort = "medium"
	if _, err := admitRoute(request, capability, roots); err == nil {
		t.Fatal("compact route/control-plane mismatch accepted")
	}
	request.Route = route
	capability.ObservedAt = observed.Add(time.Second)
	if _, err := admitRoute(request, capability, roots); err == nil || !strings.Contains(err.Error(), "current observation") {
		t.Fatalf("stale capability error = %v", err)
	}
}

func TestProductionSupervisorRejectsMalformedSmallBoundaryBeforeDiscoveryOrLaunch(t *testing.T) {
	discoveryCalls := 0
	runner := countingRunner{calls: &discoveryCalls}
	supervisor, err := NewSupervisor(Options{StateDir: t.TempDir(), Discoverer: Discoverer{Runner: runner}})
	if err != nil {
		t.Fatal(err)
	}
	defer supervisor.Close()
	_, err = supervisor.Start(context.Background(), StartRequest{Route: Route{TargetHarness: HarnessClaude}, Brief: "legacy"})
	if err == nil || !strings.Contains(err.Error(), "source harness") {
		t.Fatalf("malformed production admission error = %v", err)
	}
	if discoveryCalls != 0 || len(supervisor.List()) != 0 {
		t.Fatalf("legacy rejection performed work: discovery=%d jobs=%d", discoveryCalls, len(supervisor.List()))
	}
}

type countingRunner struct{ calls *int }

func (runner countingRunner) Output(context.Context, string, ...string) ([]byte, error) {
	*runner.calls++
	return nil, nil
}

func controlplaneDigest(seed string) string {
	digest, err := controlplane.CanonicalDigest([]byte(`{"seed":"` + seed + `"}`))
	if err != nil {
		panic(err)
	}
	return digest
}
