package controlplane

import (
	"strings"
	"testing"
)

func fullTestGrant() AuthorityGrant {
	return AuthorityGrant{
		ToolAllow:          []string{"read", "shell", "write"},
		ToolDeny:           []string{},
		FilesystemRead:     []string{"controlplane", "runplane"},
		FilesystemWrite:    []string{"controlplane"},
		Network:            true,
		Process:            true,
		InvocableRoleKinds: []string{"technical", "domain"},
		InvocableRoleIDs:   []string{"technical-go", "domain-swarm"},
		Routes: RouteConstraint{
			Providers: []string{"openai"}, Families: []string{"gpt"},
			Models: []string{"gpt-5.6-sol"}, Efforts: []string{"high", "max"},
		},
		Budget: BudgetLimit{MaxDelegates: 10, MaxWriters: 2, MaxTokens: 100_000, MaxDurationSeconds: 3600},
		Evidence: EvidenceRequirement{
			RequiredChecks: []string{"unit"}, RequiredArtifacts: []string{"patch"}, IndependentVerification: true,
		},
	}
}

func validAuthorityEnvelope(t *testing.T) AuthorityEnvelope {
	t.Helper()
	parent := fullTestGrant()
	ceiling := fullTestGrant()
	requested := fullTestGrant()
	requested.ToolAllow = []string{"read", "write"}
	requested.FilesystemRead = []string{"controlplane"}
	requested.InvocableRoleKinds = []string{"technical"}
	requested.InvocableRoleIDs = []string{"technical-go"}
	requested.Routes.Efforts = []string{"max"}
	requested.Budget = BudgetLimit{MaxDelegates: 1, MaxWriters: 1, MaxTokens: 10_000, MaxDurationSeconds: 300}
	observed := fullTestGrant()
	envelope := AuthorityEnvelope{
		APIVersion: AuthorityAPIVersion, GrantID: "grant-1", ParentGrantID: "grant-root",
		RoleID: "workflow-executor", RoleDigest: testDigest("role"), Lane: "execution",
		CapabilityMode: CapabilityWorkspace, ParentGrant: parent, RoleCeiling: ceiling,
		RequestedGrant: requested, ObservedGrant: observed, IssuedAt: "2026-08-23T20:00:00Z",
	}
	if err := SealAuthority(&envelope); err != nil {
		t.Fatal(err)
	}
	return envelope
}

func TestAuthorityExactFourWayIntersection(t *testing.T) {
	envelope := validAuthorityEnvelope(t)
	if err := ValidateAuthority(envelope); err != nil {
		t.Fatal(err)
	}
	if got := strings.Join(envelope.EffectiveGrant.ToolAllow, ","); got != "read,write" {
		t.Fatalf("effective tools = %q", got)
	}
	if envelope.EffectiveGrant.Budget.MaxDelegates != 1 || envelope.EffectiveGrant.Budget.MaxTokens != 10_000 {
		t.Fatalf("effective budget = %+v", envelope.EffectiveGrant.Budget)
	}
}

func TestAuthorityExpansionIsDeniedAndMustBeRecorded(t *testing.T) {
	envelope := validAuthorityEnvelope(t)
	envelope.RequestedGrant.ToolAllow = append(envelope.RequestedGrant.ToolAllow, "admin")
	if err := SealAuthority(&envelope); err != nil {
		t.Fatal(err)
	}
	if len(envelope.DenialReasons) == 0 || containsString(envelope.EffectiveGrant.ToolAllow, "admin") {
		t.Fatalf("expansion was not denied: %+v", envelope)
	}
	envelope.DenialReasons = nil
	envelope.Digest, _ = digestWithoutField(envelope, "digest")
	if err := ValidateAuthority(envelope); err == nil {
		t.Fatal("unrecorded expansion accepted")
	}
}

func TestAuthorityRejectsMissingDimension(t *testing.T) {
	grant := fullTestGrant()
	grant.FilesystemWrite = nil
	if _, err := IntersectAuthority(grant, fullTestGrant(), fullTestGrant(), fullTestGrant()); err == nil {
		t.Fatal("nil authority dimension accepted")
	}
}

func testDigest(seed string) string {
	value, err := CanonicalJSONDigest([]byte(`{"seed":"` + seed + `"}`))
	if err != nil {
		panic(err)
	}
	return value
}

func containsString(values []string, wanted string) bool {
	for _, value := range values {
		if value == wanted {
			return true
		}
	}
	return false
}
