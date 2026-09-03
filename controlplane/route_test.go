package controlplane

import "testing"

func testExactRoute() ExactRoute {
	return ExactRoute{Provider: "openai", Family: "gpt", Model: "gpt-5.6-sol", Effort: "max"}
}

func testCapability(t *testing.T) CapabilitySnapshot {
	t.Helper()
	snapshot := CapabilitySnapshot{
		HarnessID: "codex", Routes: []ExactRoute{testExactRoute(), {Provider: "google", Family: "gemini", Model: "gemini-3.8-flash", Effort: "max"}},
		ObservedAt: "2026-08-23T19:59:00Z", ExpiresAt: "2026-08-23T20:05:00Z",
	}
	if err := SealCapabilitySnapshot(&snapshot); err != nil {
		t.Fatal(err)
	}
	return snapshot
}

func validRouteEnvelope(t *testing.T) RouteEnvelope {
	t.Helper()
	parent := testExactRoute()
	envelope := RouteEnvelope{
		APIVersion: RouteAPIVersion, RouteID: "route-1", GoalID: "goal-1", AssignmentID: "assignment-1",
		GenerationID: "generation-1", DispatchID: "dispatch-1", ParentDispatchID: "dispatch-root",
		SourceHarness: "codex", TargetHarness: "claude", Decision: RouteInherit, ParentRoute: &parent,
		RequestedRoute: parent, CanonicalRoleID: "workflow-executor", RoleDigest: testDigest("role"),
		AuthorityDigest: testDigest("authority"), SelectionDigest: testDigest("selection"), RepositoryDigest: testDigest("repo"),
		Capability: testCapability(t), OwnershipClaimIDs: []string{"claim-1"}, BudgetReservationID: "budget-1",
		Evidence:      EvidenceRequirement{RequiredChecks: []string{"unit"}, RequiredArtifacts: []string{"patch"}},
		OnUnavailable: RouteUnavailableReject, IssuedAt: "2026-08-23T20:00:00Z", ExpiresAt: "2026-08-23T20:04:00Z",
	}
	if err := SealRoute(&envelope); err != nil {
		t.Fatal(err)
	}
	return envelope
}

func TestRouteInheritanceIsExact(t *testing.T) {
	envelope := validRouteEnvelope(t)
	if err := ValidateRoute(envelope); err != nil {
		t.Fatal(err)
	}
	if !routeEqual(*envelope.ParentRoute, envelope.EffectiveRoute) {
		t.Fatalf("inherited route changed: %+v", envelope.EffectiveRoute)
	}
}

func TestRouteRefinementRequiresAuthorityAndDiscovery(t *testing.T) {
	parent := testExactRoute()
	requested := ExactRoute{Provider: "google", Family: "gemini", Model: "gemini-3.8-flash", Effort: "max"}
	capability := testCapability(t)
	if _, err := ResolveRoute(&parent, requested, RouteRefine, false, "", capability, "2026-08-23T20:00:00Z"); err == nil {
		t.Fatal("unauthorized refinement accepted")
	}
	got, err := ResolveRoute(&parent, requested, RouteRefine, true, "user selected exact route", capability, "2026-08-23T20:00:00Z")
	if err != nil {
		t.Fatal(err)
	}
	if !routeEqual(got, requested) {
		t.Fatalf("refined route = %+v", got)
	}
	requested.Model = "gemini-unknown"
	if _, err := ResolveRoute(&parent, requested, RouteRefine, true, "requested", capability, "2026-08-23T20:00:00Z"); err == nil {
		t.Fatal("unavailable exact route accepted")
	}
}

func TestRouteRejectsStaleDiscoveryAndSilentDowngrade(t *testing.T) {
	parent := testExactRoute()
	capability := testCapability(t)
	if _, err := ResolveRoute(&parent, parent, RouteInherit, false, "", capability, "2026-08-23T20:06:00Z"); err == nil {
		t.Fatal("stale discovery accepted")
	}
	downgraded := parent
	downgraded.Effort = "high"
	if _, err := ResolveRoute(&parent, downgraded, RouteInherit, false, "", capability, "2026-08-23T20:00:00Z"); err == nil {
		t.Fatal("silent inherited downgrade accepted")
	}
}
