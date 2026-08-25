package codingfleet

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"testing"
	"time"

	"github.com/anvil008/swarm-coder/controlplane"
	"github.com/anvil008/swarm-coder/harness-agents/canonical"
)

func TestFactoryTransactionUpdatesCatalogRenderInstallAndColdLoad(t *testing.T) {
	manifest, candidate := factoryTransactionFixture(t)
	called := false
	result, err := ExecuteFactoryTransaction(context.Background(), FactoryTransactionOptions{
		Manifest: manifest, CatalogJSON: candidate,
		coldLoader: func(_ context.Context, repositoryRoot, home string) (FactoryColdLoadProof, error) {
			called = true
			if _, err := os.Stat(filepath.Join(repositoryRoot, "harness-agents", "rendered", "claude", "anvil-cf-technical-factory-sample.md")); err != nil {
				return FactoryColdLoadProof{}, err
			}
			if _, err := os.Lstat(filepath.Join(home, ".claude", "agents", "anvil-cf-technical-factory-sample.md")); err != nil {
				return FactoryColdLoadProof{}, err
			}
			return factoryColdProof(), nil
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	if !called || result.RolledBack || result.InstalledDigests != 48 || len(result.ProjectionDigests) != 3 {
		t.Fatalf("transaction result=%+v called=%v", result, called)
	}
	written, err := os.ReadFile(filepath.Join(manifest.FleetRoot, "harness-agents", "canonical", "catalog.json"))
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(bytes.TrimSpace(written), bytes.TrimSpace(candidate)) {
		t.Fatal("candidate catalog was not installed")
	}
	if _, err := Install(InstallOptions{HomeDir: manifest.HomeRoot, RepositoryRoot: manifest.FleetRoot, Mode: InstallCheck, Document: mustDecodeCandidate(t, candidate)}); err != nil {
		t.Fatalf("installed candidate check: %v", err)
	}
}

func TestFactoryTransactionRollsBackEveryInjectedPhase(t *testing.T) {
	for _, failedPhase := range []string{"catalog", "render", "install", "cold-load"} {
		t.Run(failedPhase, func(t *testing.T) {
			manifest, candidate := factoryTransactionFixture(t)
			before := factoryOperationSnapshots(t, manifest)
			_, err := ExecuteFactoryTransaction(context.Background(), FactoryTransactionOptions{
				Manifest: manifest, CatalogJSON: candidate, coldLoader: func(context.Context, string, string) (FactoryColdLoadProof, error) { return factoryColdProof(), nil },
				afterPhase: func(phase string) error {
					if phase == failedPhase {
						return errors.New("injected " + phase + " failure")
					}
					return nil
				},
			})
			if err == nil || !bytes.Contains([]byte(err.Error()), []byte("rolled back")) {
				t.Fatalf("transaction error=%v", err)
			}
			after := factoryOperationSnapshots(t, manifest)
			if !reflect.DeepEqual(after, before) {
				t.Fatalf("rollback mismatch\nbefore=%+v\nafter=%+v", before, after)
			}
		})
	}
}

func TestFactoryTransactionRejectsHotLoadProofAndStalePreimage(t *testing.T) {
	manifest, candidate := factoryTransactionFixture(t)
	before := factoryOperationSnapshots(t, manifest)
	_, err := ExecuteFactoryTransaction(context.Background(), FactoryTransactionOptions{
		Manifest: manifest, CatalogJSON: candidate,
		coldLoader: func(context.Context, string, string) (FactoryColdLoadProof, error) {
			proof := factoryColdProof()
			proof.ExternalProcess = false
			return proof, nil
		},
	})
	if err == nil {
		t.Fatal("hot-load proof accepted")
	}
	if after := factoryOperationSnapshots(t, manifest); !reflect.DeepEqual(after, before) {
		t.Fatal("hot-load rejection did not roll back")
	}

	manifest, candidate = factoryTransactionFixture(t)
	manifest.Preimages[0].Digest = factoryTestDigest("stale")
	if _, err := ExecuteFactoryTransaction(context.Background(), FactoryTransactionOptions{Manifest: manifest, CatalogJSON: candidate}); err == nil {
		t.Fatal("stale preimage accepted")
	}
}

func factoryTransactionFixture(t *testing.T) (FactoryManifest, []byte) {
	t.Helper()
	root := t.TempDir()
	repositoryRoot, home, target := filepath.Join(root, "swarm"), filepath.Join(root, "home"), filepath.Join(root, "target")
	for _, path := range []string{repositoryRoot, home, target, filepath.Join(repositoryRoot, "harness-agents", "canonical")} {
		if err := os.MkdirAll(path, 0o755); err != nil {
			t.Fatal(err)
		}
	}
	if err := os.WriteFile(filepath.Join(repositoryRoot, "harness-agents", "canonical", "catalog.json"), canonical.Bytes(), 0o644); err != nil {
		t.Fatal(err)
	}
	current := mustLoad(t)
	rendered, err := Render(repositoryRoot, current)
	if err != nil {
		t.Fatal(err)
	}
	if err := SyncRendered(repositoryRoot, rendered, false); err != nil {
		t.Fatal(err)
	}
	writeGuardBinary(t, repositoryRoot)
	writeRunplaneSkill(t, repositoryRoot)
	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallApply}); err != nil {
		t.Fatal(err)
	}

	candidate := current
	candidate.CatalogVersion += ".factory-test"
	var added Role
	for _, role := range current.Roles {
		if role.ID == "toolchain-go" {
			added = role
			break
		}
	}
	added.ID = "technical-factory-sample"
	added.Name = "Factory Sample Specialist"
	added.Summary = "Provides a deterministic Factory transaction test specialist."
	added.Instructions = "Implement only the explicitly assigned deterministic Factory sample work."
	added.Activation.Keywords = append([]WeightedSignal(nil), added.Activation.Keywords...)
	added.Activation.Keywords = append(added.Activation.Keywords, WeightedSignal{Value: "factory-sample", Weight: 10})
	added.Tags = append([]string(nil), added.Tags...)
	added.Tags = append(added.Tags, "factory-sample")
	candidate.Roles = append(append([]Role(nil), current.Roles...), added)
	source := sourceDocument{
		APIVersion: candidate.APIVersion, CatalogVersion: candidate.CatalogVersion, GeneratedAt: candidate.GeneratedAt,
		Source: candidate.Source, AuthorityProfiles: candidate.AuthorityProfiles, Roles: candidate.Roles, KnowledgeRoles: candidate.KnowledgeRoles, ModelTiers: candidate.ModelTiers,
	}
	candidateJSON, err := json.MarshalIndent(source, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if _, err := decodeCatalog(candidateJSON); err != nil {
		t.Fatalf("candidate: %v", err)
	}

	native := "anvil-cf-technical-factory-sample"
	manifest := FactoryManifest{
		APIVersion: FactoryManifestAPIVersion, TransactionID: "factory-transaction-test", RequestedRoleID: added.ID,
		RequestedRoleClass: ClassTechnical, Rationale: "test the exact missing specialist transaction",
		FleetRoot: repositoryRoot, TargetProjectRoot: target, HomeRoot: home,
		Operations: []FactoryOperation{
			{Kind: FactoryCatalogAdd, Path: "harness-agents/canonical/catalog.json", RoleID: added.ID},
			{Kind: FactoryProjectionWrite, Path: "harness-agents/rendered/claude/" + native + ".md", RoleID: added.ID},
			{Kind: FactoryProjectionWrite, Path: "harness-agents/rendered/codex/" + native + ".toml", RoleID: added.ID},
			{Kind: FactoryProjectionWrite, Path: "harness-agents/rendered/antigravity/" + native + "/agent.md", RoleID: added.ID},
			{Kind: FactoryInstallManaged, Path: filepath.Join(home, ".claude", "agents", native+".md"), RoleID: added.ID},
			{Kind: FactoryInstallManaged, Path: filepath.Join(home, ".gemini", "config", "agents", native), RoleID: added.ID},
			{Kind: FactoryInstallManaged, Path: filepath.Join(home, ".codex", native+".config.toml"), RoleID: added.ID},
			{Kind: FactoryInstallManaged, Path: filepath.Join(home, ".codex", "config.toml"), RoleID: added.ID},
		},
		ValidationPlan: []string{"catalog", "render", "install", "cold-load"}, ReturnControlTo: workflowCodingOrchestratorID,
		InvokedWorkflowIDs: []string{},
	}
	manifest.Preimages, err = BuildFactoryPreimages(manifest)
	if err != nil {
		t.Fatal(err)
	}
	return manifest, candidateJSON
}

func factoryOperationSnapshots(t *testing.T, manifest FactoryManifest) []installPathSnapshot {
	t.Helper()
	result := make([]installPathSnapshot, 0, len(manifest.Operations))
	seen := map[string]bool{}
	for _, operation := range manifest.Operations {
		if seen[operation.Path] {
			continue
		}
		seen[operation.Path] = true
		snapshot, err := captureInstallPath(resolveFactoryPath(manifest.FleetRoot, operation.Path))
		if err != nil {
			t.Fatal(err)
		}
		result = append(result, snapshot)
	}
	return result
}

func factoryColdProof() FactoryColdLoadProof {
	started, finished := time.Now().UTC(), time.Now().UTC().Add(time.Millisecond)
	commands := make([]controlplane.CommandEvidence, 2)
	for index := range commands {
		commands[index] = controlplane.CommandEvidence{
			CommandID: "cold-command-" + string(rune('a'+index)), ArgvDigest: factoryTestDigest("argv"), ExitCode: 0,
			StartedAt: started.Format(time.RFC3339Nano), FinishedAt: finished.Format(time.RFC3339Nano),
			StdoutDigest: factoryTestDigest("stdout"), StderrDigest: factoryTestDigest("stderr"),
		}
	}
	return FactoryColdLoadProof{ExternalProcess: true, Commands: commands}
}

func mustDecodeCandidate(t *testing.T, data []byte) *Document {
	t.Helper()
	document, err := decodeCatalog(data)
	if err != nil {
		t.Fatal(err)
	}
	if err := validateFleetTopology(document.Roles); err != nil {
		t.Fatal(err)
	}
	return &document
}
