package codingfleet

import (
	"crypto/sha256"
	"encoding/hex"
	"path/filepath"
	"strings"
	"testing"

	"github.com/anvil008/swarm-coder/controlplane"
)

func factoryManifestFixture(t *testing.T) FactoryManifest {
	t.Helper()
	fleet := filepath.Join(t.TempDir(), "swarm")
	target := filepath.Join(t.TempDir(), "target")
	home := filepath.Join(t.TempDir(), "home")
	roleID := "technical-example"
	paths := []FactoryOperation{
		{Kind: FactoryCatalogAdd, Path: "harness-agents/canonical/catalog.json", RoleID: roleID},
		{Kind: FactoryProjectionWrite, Path: "harness-agents/rendered/claude/anvil-cf-technical-example.md", RoleID: roleID},
		{Kind: FactoryProjectionWrite, Path: "harness-agents/rendered/codex/anvil-cf-technical-example.toml", RoleID: roleID},
		{Kind: FactoryProjectionWrite, Path: "harness-agents/rendered/antigravity/anvil-cf-technical-example/agent.md", RoleID: roleID},
		{Kind: FactoryInstallManaged, Path: filepath.Join(home, ".claude", "agents", "anvil-cf-technical-example.md"), RoleID: roleID},
	}
	preimages := make([]FactoryPreimage, len(paths))
	for index, operation := range paths {
		preimages[index] = FactoryPreimage{Path: operation.Path, Exists: true, Digest: factoryTestDigest(operation.Path), Mode: 0o600}
	}
	return FactoryManifest{
		APIVersion: FactoryManifestAPIVersion, TransactionID: "factory-transaction-1", RequestedRoleID: roleID,
		RequestedRoleClass: ClassTechnical, Rationale: "the current catalog lacks an exact specialist",
		FleetRoot: fleet, TargetProjectRoot: target, HomeRoot: home, Operations: paths, Preimages: preimages,
		ValidationPlan: []string{"catalog", "render", "install", "cold-load"}, ReturnControlTo: workflowCodingOrchestratorID,
		InvokedWorkflowIDs: []string{},
	}
}

func TestFactoryPolicyAllowsOnlyOwnedSpecialistSurface(t *testing.T) {
	manifest := factoryManifestFixture(t)
	if err := ValidateFactoryManifest(manifest, nil); err != nil {
		t.Fatal(err)
	}
	for name, mutate := range map[string]func(*FactoryManifest){
		"workflow role":  func(value *FactoryManifest) { value.RequestedRoleID = workflowResearchID },
		"orchestrator":   func(value *FactoryManifest) { value.RequestedRoleID = workflowCodingOrchestratorID },
		"workflow class": func(value *FactoryManifest) { value.RequestedRoleClass = ClassWorkflow },
		"target path": func(value *FactoryManifest) {
			value.Operations[1].Path = filepath.Join(value.TargetProjectRoot, "main.go")
			value.Preimages[1].Path = value.Operations[1].Path
		},
		"path escape": func(value *FactoryManifest) {
			value.Operations[1].Path = "../target/main.go"
			value.Preimages[1].Path = value.Operations[1].Path
		},
		"workflow invocation": func(value *FactoryManifest) { value.InvokedWorkflowIDs = []string{workflowExecutorID} },
		"wrong return":        func(value *FactoryManifest) { value.ReturnControlTo = workflowExecutorID },
	} {
		t.Run(name, func(t *testing.T) {
			candidate := manifest
			candidate.Operations = append([]FactoryOperation(nil), manifest.Operations...)
			candidate.Preimages = append([]FactoryPreimage(nil), manifest.Preimages...)
			candidate.InvokedWorkflowIDs = append([]string(nil), manifest.InvokedWorkflowIDs...)
			mutate(&candidate)
			if err := ValidateFactoryManifest(candidate, nil); err == nil {
				t.Fatalf("invalid Factory manifest accepted: %+v", candidate)
			}
		})
	}
}

func TestFactoryPolicyRequiresExternalCompletionExpectation(t *testing.T) {
	manifest := factoryManifestFixture(t)
	manifest.Result = &controlplane.WorkflowResult{}
	if err := ValidateFactoryManifest(manifest, nil); err == nil || !strings.Contains(err.Error(), "self-certified") {
		t.Fatalf("self-certified result error=%v", err)
	}
	expected := controlplane.ResultExpectation{RoleID: workflowAgentFactoryID, Lane: string(WorkflowLaneFactory)}
	if err := ValidateFactoryManifest(manifest, &expected); err == nil {
		t.Fatal("invalid result envelope accepted")
	}
}

func factoryTestDigest(value string) string {
	digest := sha256.Sum256([]byte(value))
	return controlplane.CanonicalDigestPrefix + hex.EncodeToString(digest[:])
}
