package runplane

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestRouteAdmissionPrecedenceAndFailClosedValidation(t *testing.T) {
	repo := testRepository(t)
	roots := testDefinitionRoots(t)
	writeDefinition(t, roots, HarnessClaude, "workflow-executor", "opus-exact", "high")
	capability := Capability{Harness: HarnessClaude, Available: true, Models: []string{"opus-exact"}, Efforts: []string{"high"}, ModelEfforts: []ModelEffort{{Provider: "anthropic", Family: "claude", Model: "opus-exact", Effort: "high"}}, Roles: []string{"anvil-wf-executor"}}
	valid := StartRequest{Route: Route{SourceHarness: HarnessCodex, TargetHarness: HarnessClaude, Provider: "anthropic", Family: "claude", ExactModel: "opus-exact", Effort: "high", CanonicalRoleID: "workflow-executor", ParentGoalID: "goal-1", CapabilityMode: ModeWorkspaceWrite, RepositoryRoot: repo, FileOwnership: []string{"runplane"}}, Brief: "implement the bounded task"}
	admitted, err := admitRoute(valid, capability, roots)
	if err != nil {
		t.Fatal(err)
	}
	if admitted.Binding.NativeName != "anvil-wf-executor" || admitted.Definition == "" {
		t.Fatalf("admitted binding = %+v", admitted)
	}

	tests := []struct {
		name string
		edit func(*StartRequest, *Capability)
		want string
	}{
		{"same harness", func(r *StartRequest, _ *Capability) { r.Route.SourceHarness = HarnessClaude }, "must differ"},
		{"invented model", func(r *StartRequest, _ *Capability) { r.Route.ExactModel = "latest" }, "not in the discovered"},
		{"route mode overrides role", func(r *StartRequest, _ *Capability) { r.Route.CapabilityMode = ModeReadOnly }, "conflicts"},
		{"missing ownership", func(r *StartRequest, _ *Capability) { r.Route.FileOwnership = nil }, "require explicit"},
		{"escaping ownership", func(r *StartRequest, _ *Capability) { r.Route.FileOwnership = []string{"../ghost"} }, "escapes"},
		{"unavailable role", func(_ *StartRequest, c *Capability) { c.Roles = nil }, "not in the discovered"},
		{"orchestrator forbidden", func(r *StartRequest, c *Capability) {
			r.Route.CanonicalRoleID = "workflow-coding-orchestrator"
			c.Roles = []string{"anvil-coding-orchestrator"}
		}, "orchestrator"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			request, candidate := valid, capability
			test.edit(&request, &candidate)
			if _, err := admitRoute(request, candidate, roots); err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("error = %v, want containing %q", err, test.want)
			}
		})
	}
}

func TestCompactRouteProviderFamilyAdmission(t *testing.T) {
	repo := testRepository(t)
	roots := testDefinitionRoots(t)
	writeDefinition(t, roots, HarnessClaude, "workflow-research", "opus-exact", "high")
	valid := StartRequest{Route: Route{
		SourceHarness: HarnessCodex, TargetHarness: HarnessClaude,
		Provider: "anthropic", Family: "claude", ExactModel: "opus-exact", Effort: "high",
		CanonicalRoleID: "workflow-research", ParentGoalID: "goal-1", CapabilityMode: ModeReadOnly, RepositoryRoot: repo,
	}, Brief: "review"}
	capability := Capability{Harness: HarnessClaude, Available: true,
		ModelEfforts: []ModelEffort{{Provider: "anthropic", Family: "claude", Model: "opus-exact", Effort: "high"}},
		Roles:        []string{"anvil-wf-research"},
	}
	tests := []struct {
		name string
		edit func(*StartRequest, *Capability)
		want string
	}{
		{name: "valid foreign"},
		{name: "same provider", edit: func(request *StartRequest, _ *Capability) {
			request.Route.Provider, request.Route.Family = "openai", "gpt"
		}, want: "must differ from source harness provider"},
		{name: "wrong provider", edit: func(request *StartRequest, _ *Capability) {
			request.Route.Provider = "google"
		}, want: "does not match target harness provider"},
		{name: "wrong family", edit: func(request *StartRequest, _ *Capability) {
			request.Route.Family = "gemini"
		}, want: "does not match target harness family"},
		{name: "partial pair", edit: func(request *StartRequest, _ *Capability) {
			request.Route.Family = ""
		}, want: "must both be explicit"},
		{name: "capability provider mismatch", edit: func(_ *StartRequest, capability *Capability) {
			capability.ModelEfforts[0].Provider = "google"
		}, want: "exact provider/family/model/effort route pair"},
		{name: "capability family mismatch", edit: func(_ *StartRequest, capability *Capability) {
			capability.ModelEfforts[0].Family = "gemini"
		}, want: "exact provider/family/model/effort route pair"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			request := valid
			candidate := capability
			candidate.ModelEfforts = append([]ModelEffort(nil), capability.ModelEfforts...)
			if test.edit != nil {
				test.edit(&request, &candidate)
			}
			_, err := admitRoute(request, candidate, roots)
			if test.want == "" && err != nil {
				t.Fatal(err)
			}
			if test.want != "" && (err == nil || !strings.Contains(err.Error(), test.want)) {
				t.Fatalf("error = %v, want containing %q", err, test.want)
			}
		})
	}
}

func TestCompactRouteRejectsRequiredArtifacts(t *testing.T) {
	repo := testRepository(t)
	roots := testDefinitionRoots(t)
	writeDefinition(t, roots, HarnessClaude, "workflow-research", "opus-exact", "high")
	request := StartRequest{Route: Route{
		SourceHarness: HarnessCodex, TargetHarness: HarnessClaude,
		Provider: "anthropic", Family: "claude", ExactModel: "opus-exact", Effort: "high",
		CanonicalRoleID: "workflow-research", ParentGoalID: "goal-1", CapabilityMode: ModeReadOnly, RepositoryRoot: repo,
		Evidence: EvidenceContract{RequiredArtifacts: []string{"patch"}},
	}, Brief: "review"}
	capability := Capability{Harness: HarnessClaude, Available: true,
		ModelEfforts: []ModelEffort{{Provider: "anthropic", Family: "claude", Model: "opus-exact", Effort: "high"}},
		Roles:        []string{"anvil-wf-research"},
	}
	if _, err := admitRoute(request, capability, roots); err == nil || !strings.Contains(err.Error(), "cannot satisfy required artifacts") {
		t.Fatalf("compact artifact error = %v", err)
	}
}

func TestExactDefinitionDriftFailsClosed(t *testing.T) {
	repo := testRepository(t)
	roots := testDefinitionRoots(t)
	path := writeDefinition(t, roots, HarnessClaude, "workflow-research", "sonnet-exact", "high")
	if err := os.WriteFile(path, []byte("---\nname: anvil-wf-research\nmodel: sonnet-exact\n---\ndrifted"), 0o600); err != nil {
		t.Fatal(err)
	}
	request := StartRequest{Route: Route{SourceHarness: HarnessCodex, TargetHarness: HarnessClaude, Provider: "anthropic", Family: "claude", ExactModel: "sonnet-exact", Effort: "high", CanonicalRoleID: "workflow-research", ParentGoalID: "goal-1", CapabilityMode: ModeReadOnly, RepositoryRoot: repo}, Brief: "review"}
	capability := Capability{Harness: HarnessClaude, Available: true, Models: []string{"sonnet-exact"}, Efforts: []string{"high"}, ModelEfforts: []ModelEffort{{Model: "sonnet-exact", Effort: "high"}}, Roles: []string{"anvil-wf-research"}}
	if _, err := admitRoute(request, capability, roots); err == nil || !strings.Contains(err.Error(), "byte-for-byte") {
		t.Fatalf("error = %v", err)
	}
}

func TestExactDefinitionRejectsPrefixAndSuffixTampering(t *testing.T) {
	for _, tamper := range []func([]byte) []byte{
		func(data []byte) []byte { return append([]byte("# prefix\n"), data...) },
		func(data []byte) []byte { return append(data, []byte("\n# suffix")...) },
	} {
		roots := testDefinitionRoots(t)
		path := writeDefinition(t, roots, HarnessClaude, "workflow-research", "", "")
		data, _ := os.ReadFile(path)
		if err := os.WriteFile(path, tamper(data), 0o600); err != nil {
			t.Fatal(err)
		}
		binding, _ := loadRoleBinding("workflow-research")
		if _, err := roots.verifyExactDefinition(HarnessClaude, binding); err == nil || !strings.Contains(err.Error(), "byte-for-byte") {
			t.Fatalf("tamper error=%v", err)
		}
	}
}

func TestOwnershipCanonicalizesSymlinksAndRejectsEscape(t *testing.T) {
	repo := testRepository(t)
	if err := os.Mkdir(filepath.Join(repo, "real"), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink("real", filepath.Join(repo, "alias")); err != nil {
		t.Fatal(err)
	}
	got, err := normalizeOwnership(repo, []string{"alias/new.go"})
	if err != nil || len(got) != 1 || got[0] != "real/new.go" {
		t.Fatalf("canonical = %v, err=%v", got, err)
	}
	outside := t.TempDir()
	if err := os.Symlink(outside, filepath.Join(repo, "outside")); err != nil {
		t.Fatal(err)
	}
	if _, err := normalizeOwnership(repo, []string{"outside/file.go"}); err == nil || !strings.Contains(err.Error(), "outside") {
		t.Fatalf("escape error = %v", err)
	}
}

func TestModelEffortPairDoesNotUseCartesianProduct(t *testing.T) {
	capability := Capability{Harness: HarnessAGY, Available: true, Models: []string{"gemini-exact-low"}, Efforts: []string{"low", "high"}, ModelEfforts: []ModelEffort{{Model: "gemini-exact-low", Effort: "low"}}, Roles: []string{"anvil-wf-research"}}
	request := StartRequest{Route: Route{SourceHarness: HarnessCodex, TargetHarness: HarnessAGY, Provider: "google", Family: "gemini", ExactModel: "gemini-exact-low", Effort: "high", CanonicalRoleID: "workflow-research", ParentGoalID: "goal-1", CapabilityMode: ModeReadOnly, RepositoryRoot: testRepository(t)}, Brief: "read"}
	if _, err := admitRoute(request, capability, testDefinitionRoots(t)); err == nil || !strings.Contains(err.Error(), "pair") {
		t.Fatalf("pair error = %v", err)
	}
}

func TestOwnershipConflictRules(t *testing.T) {
	if !ownershipConflicts([]string{"runplane"}, []string{"runplane/store.go"}) {
		t.Fatal("parent/child ownership must conflict")
	}
	if ownershipConflicts([]string{"runplane"}, []string{"cmd/swarm-runplane"}) {
		t.Fatal("disjoint ownership must not conflict")
	}
}

func testRepository(t *testing.T) string {
	t.Helper()
	repo := t.TempDir()
	if err := os.Mkdir(filepath.Join(repo, ".git"), 0o700); err != nil {
		t.Fatal(err)
	}
	return repo
}
