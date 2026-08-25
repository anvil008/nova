package codingfleet

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"time"

	"github.com/anvil008/swarm-coder/controlplane"
)

type FactoryTransactionOptions struct {
	Manifest    FactoryManifest
	CatalogJSON []byte
	// afterPhase and coldLoader are package-private failure-injection seams.
	afterPhase func(string) error
	coldLoader func(context.Context, string, string) (FactoryColdLoadProof, error)
}

type FactoryColdLoadProof struct {
	ExternalProcess bool                           `json:"externalProcess"`
	Commands        []controlplane.CommandEvidence `json:"commands"`
}

type FactoryTransactionResult struct {
	TransactionID     string               `json:"transactionId"`
	CatalogDigest     string               `json:"catalogDigest"`
	ProjectionDigests map[string]string    `json:"projectionDigests"`
	InstalledDigests  int                  `json:"installedDigests"`
	ColdLoadProof     FactoryColdLoadProof `json:"coldLoadProof"`
	RolledBack        bool                 `json:"rolledBack"`
}

// BuildFactoryPreimages captures the exact bytes/link target and mode digests
// the orchestrator must bind before authorizing a Factory transaction.
func BuildFactoryPreimages(manifest FactoryManifest) ([]FactoryPreimage, error) {
	fleet, _, _, err := validateFactoryRoots(manifest)
	if err != nil {
		return nil, err
	}
	if manifest.Operations == nil || len(manifest.Operations) == 0 {
		return nil, errors.New("factory operations are required")
	}
	preimages := make([]FactoryPreimage, 0, len(manifest.Operations))
	seen := map[string]struct{}{}
	for _, operation := range manifest.Operations {
		if _, duplicate := seen[operation.Path]; duplicate {
			continue
		}
		seen[operation.Path] = struct{}{}
		pathname := resolveFactoryPath(fleet, operation.Path)
		snapshot, err := captureInstallPath(pathname)
		if err != nil {
			return nil, fmt.Errorf("capture Factory preimage %q: %w", operation.Path, err)
		}
		preimage := FactoryPreimage{Path: operation.Path, Exists: snapshot.exists}
		if snapshot.exists {
			preimage.Digest = factorySnapshotDigest(snapshot)
			preimage.Mode = uint32(snapshot.mode.Perm())
		}
		preimages = append(preimages, preimage)
	}
	sort.Slice(preimages, func(i, j int) bool { return preimages[i].Path < preimages[j].Path })
	return preimages, nil
}

// ExecuteFactoryTransaction atomically applies one specialist addition across
// the canonical catalog, deterministic projections, installed definitions,
// and a separately compiled cold-load verification. Any failure restores all
// declared preimages before returning.
func ExecuteFactoryTransaction(ctx context.Context, options FactoryTransactionOptions) (FactoryTransactionResult, error) {
	manifest := options.Manifest
	if err := ValidateFactoryManifest(manifest, nil); err != nil {
		return FactoryTransactionResult{}, err
	}
	candidate, err := decodeCatalog(options.CatalogJSON)
	if err != nil {
		return FactoryTransactionResult{}, fmt.Errorf("decode candidate Factory catalog: %w", err)
	}
	if err := validateFleetTopology(candidate.Roles); err != nil {
		return FactoryTransactionResult{}, fmt.Errorf("validate candidate Factory topology: %w", err)
	}
	current, err := Load()
	if err != nil {
		return FactoryTransactionResult{}, err
	}
	if err := validateFactoryCatalogDelta(current, candidate, manifest); err != nil {
		return FactoryTransactionResult{}, err
	}
	if err := validateFactoryOperationSet(manifest); err != nil {
		return FactoryTransactionResult{}, err
	}
	if _, err := Install(InstallOptions{HomeDir: manifest.HomeRoot, RepositoryRoot: manifest.FleetRoot, Mode: InstallCheck}); err != nil {
		return FactoryTransactionResult{}, fmt.Errorf("Factory requires a current installed baseline: %w", err)
	}

	snapshots, err := captureFactorySnapshots(manifest)
	if err != nil {
		return FactoryTransactionResult{}, err
	}
	result := FactoryTransactionResult{TransactionID: manifest.TransactionID, ProjectionDigests: map[string]string{}}
	rollback := func(cause error) (FactoryTransactionResult, error) {
		var restoreErrors []error
		for index := len(snapshots) - 1; index >= 0; index-- {
			if restoreErr := restoreInstallPath(snapshots[index]); restoreErr != nil {
				restoreErrors = append(restoreErrors, restoreErr)
			}
		}
		result.RolledBack = true
		if len(restoreErrors) != 0 {
			return result, fmt.Errorf("Factory transaction failed: %w; rollback failed: %v", cause, errors.Join(restoreErrors...))
		}
		return result, fmt.Errorf("Factory transaction failed and was rolled back: %w", cause)
	}
	phase := func(name string) error {
		if options.afterPhase != nil {
			return options.afterPhase(name)
		}
		return nil
	}

	catalogPath := filepath.Join(manifest.FleetRoot, "harness-agents", "canonical", "catalog.json")
	mode := fs.FileMode(0o644)
	if info, statErr := os.Stat(catalogPath); statErr == nil {
		mode = info.Mode().Perm()
	}
	if err := writeFileAtomic(catalogPath, append(bytes.TrimSpace(options.CatalogJSON), '\n'), mode); err != nil {
		return rollback(err)
	}
	if err := phase("catalog"); err != nil {
		return rollback(err)
	}
	rendered, err := Render(manifest.FleetRoot, candidate)
	if err != nil {
		return rollback(err)
	}
	if err := SyncRendered(manifest.FleetRoot, rendered, false); err != nil {
		return rollback(err)
	}
	if err := phase("render"); err != nil {
		return rollback(err)
	}
	installed, err := Install(InstallOptions{HomeDir: manifest.HomeRoot, RepositoryRoot: manifest.FleetRoot, Mode: InstallApply, Document: &candidate})
	if err != nil {
		return rollback(err)
	}
	result.InstalledDigests = installed.VerifiedDigests
	if err := phase("install"); err != nil {
		return rollback(err)
	}
	loader := options.coldLoader
	if loader == nil {
		loader = coldLoadFactoryState
	}
	proof, err := loader(ctx, manifest.FleetRoot, manifest.HomeRoot)
	if err != nil {
		return rollback(err)
	}
	if err := validateFactoryColdLoadProof(proof); err != nil {
		return rollback(err)
	}
	result.ColdLoadProof = proof
	if err := phase("cold-load"); err != nil {
		return rollback(err)
	}
	if err := SyncRendered(manifest.FleetRoot, rendered, true); err != nil {
		return rollback(err)
	}
	if _, err := Install(InstallOptions{HomeDir: manifest.HomeRoot, RepositoryRoot: manifest.FleetRoot, Mode: InstallCheck, Document: &candidate}); err != nil {
		return rollback(err)
	}
	result.CatalogDigest = factoryBytesDigest(bytes.TrimSpace(options.CatalogJSON))
	for _, file := range rendered.Files {
		if strings.Contains(file.Path, nativeAgentNameForID(manifest.RequestedRoleID)) {
			result.ProjectionDigests[filepath.ToSlash(filepath.Join("harness-agents", "rendered", file.Path))] = factoryBytesDigest(file.Content)
		}
	}
	return result, nil
}

func validateFactoryCatalogDelta(current, candidate Document, manifest FactoryManifest) error {
	currentRoles := make(map[string]Role, len(current.Roles))
	for _, role := range current.Roles {
		currentRoles[role.ID] = role
	}
	added := []Role{}
	for _, role := range candidate.Roles {
		if before, exists := currentRoles[role.ID]; exists {
			if !reflect.DeepEqual(before, role) {
				return fmt.Errorf("Factory candidate modifies existing role %q", role.ID)
			}
			delete(currentRoles, role.ID)
			continue
		}
		added = append(added, role)
	}
	if len(currentRoles) != 0 || len(added) != 1 {
		return errors.New("Factory candidate must add exactly one role and remove none")
	}
	role := added[0]
	if role.ID != manifest.RequestedRoleID || role.Class != manifest.RequestedRoleClass || role.Workflow != nil {
		return errors.New("Factory catalog addition does not match the authorized technical/domain specialist")
	}
	if !reflect.DeepEqual(current.AuthorityProfiles, candidate.AuthorityProfiles) {
		return errors.New("Factory candidate may not modify authority profiles")
	}
	return nil
}

func validateFactoryOperationSet(manifest FactoryManifest) error {
	native := nativeAgentNameForID(manifest.RequestedRoleID)
	required := map[string]struct{}{
		string(FactoryCatalogAdd) + "\x00harness-agents/canonical/catalog.json":                                          {},
		string(FactoryProjectionWrite) + "\x00harness-agents/rendered/claude/" + native + ".md":                          {},
		string(FactoryProjectionWrite) + "\x00harness-agents/rendered/codex/" + native + ".toml":                         {},
		string(FactoryProjectionWrite) + "\x00harness-agents/rendered/antigravity/" + native + "/agent.md":               {},
		string(FactoryInstallManaged) + "\x00" + filepath.Join(manifest.HomeRoot, ".claude", "agents", native+".md"):     {},
		string(FactoryInstallManaged) + "\x00" + filepath.Join(manifest.HomeRoot, ".gemini", "config", "agents", native): {},
		string(FactoryInstallManaged) + "\x00" + filepath.Join(manifest.HomeRoot, ".codex", native+".config.toml"):       {},
		string(FactoryInstallManaged) + "\x00" + filepath.Join(manifest.HomeRoot, ".codex", "config.toml"):               {},
	}
	for _, operation := range manifest.Operations {
		delete(required, string(operation.Kind)+"\x00"+operation.Path)
	}
	if len(required) != 0 || len(manifest.Operations) != 8 {
		return errors.New("Factory transaction operations must exactly cover catalog, three projections, three installed roles, and Codex declarations")
	}
	return nil
}

func captureFactorySnapshots(manifest FactoryManifest) ([]installPathSnapshot, error) {
	preimages := make(map[string]FactoryPreimage, len(manifest.Preimages))
	for _, preimage := range manifest.Preimages {
		preimages[preimage.Path] = preimage
	}
	snapshots := make([]installPathSnapshot, 0, len(manifest.Operations))
	seen := map[string]struct{}{}
	for _, operation := range manifest.Operations {
		if _, duplicate := seen[operation.Path]; duplicate {
			continue
		}
		seen[operation.Path] = struct{}{}
		pathname := resolveFactoryPath(manifest.FleetRoot, operation.Path)
		snapshot, err := captureInstallPath(pathname)
		if err != nil {
			return nil, err
		}
		declared := preimages[operation.Path]
		if snapshot.exists != declared.Exists || (snapshot.exists && (factorySnapshotDigest(snapshot) != declared.Digest || uint32(snapshot.mode.Perm()) != declared.Mode)) {
			return nil, fmt.Errorf("Factory preimage %q is stale", operation.Path)
		}
		snapshots = append(snapshots, snapshot)
	}
	return snapshots, nil
}

func resolveFactoryPath(fleetRoot, path string) string {
	if filepath.IsAbs(path) {
		return filepath.Clean(path)
	}
	return filepath.Join(fleetRoot, filepath.FromSlash(path))
}

func factorySnapshotDigest(snapshot installPathSnapshot) string {
	if snapshot.linkTarget != "" {
		return factoryBytesDigest([]byte(snapshot.linkTarget))
	}
	return factoryBytesDigest(snapshot.content)
}

func factoryBytesDigest(data []byte) string {
	digest := sha256.Sum256(data)
	return controlplane.CanonicalDigestPrefix + hex.EncodeToString(digest[:])
}

func coldLoadFactoryState(ctx context.Context, repositoryRoot, home string) (FactoryColdLoadProof, error) {
	commands := [][]string{
		{"go", "run", "./cmd/codingfleet", "render", "--root", repositoryRoot, "--check"},
		{"go", "run", "./cmd/codingfleet", "install", "--root", repositoryRoot, "--home", home, "--check"},
	}
	proof := FactoryColdLoadProof{ExternalProcess: true, Commands: make([]controlplane.CommandEvidence, 0, len(commands))}
	for index, argv := range commands {
		started := time.Now().UTC()
		commandCtx, cancel := context.WithTimeout(ctx, 2*time.Minute)
		command := exec.CommandContext(commandCtx, argv[0], argv[1:]...)
		command.Dir = repositoryRoot
		stdout, stderr := &boundedCommandBuffer{limit: 1 << 20}, &boundedCommandBuffer{limit: 1 << 20}
		command.Stdout, command.Stderr = stdout, stderr
		err := command.Run()
		cancel()
		finished := time.Now().UTC()
		exitCode := 0
		if err != nil {
			exitCode = -1
			var exitErr *exec.ExitError
			if errors.As(err, &exitErr) {
				exitCode = exitErr.ExitCode()
			}
		}
		evidence := controlplane.CommandEvidence{
			CommandID: fmt.Sprintf("factory-cold-%d", index+1), ArgvDigest: factoryBytesDigest([]byte(strings.Join(argv, "\x00"))), ExitCode: exitCode,
			StartedAt: started.Format(time.RFC3339Nano), FinishedAt: finished.Format(time.RFC3339Nano),
			StdoutDigest: factoryBytesDigest(stdout.data), StderrDigest: factoryBytesDigest(stderr.data),
		}
		proof.Commands = append(proof.Commands, evidence)
		if err != nil {
			return proof, fmt.Errorf("cold-load command %d failed with exit %d", index+1, exitCode)
		}
	}
	return proof, nil
}

func validateFactoryColdLoadProof(proof FactoryColdLoadProof) error {
	if !proof.ExternalProcess || len(proof.Commands) != 2 {
		return errors.New("Factory cold-load proof must come from two fresh external process checks")
	}
	for _, command := range proof.Commands {
		if command.ExitCode != 0 {
			return errors.New("Factory cold-load proof contains a failed command")
		}
		for _, digest := range []string{command.ArgvDigest, command.StdoutDigest, command.StderrDigest} {
			if err := controlplane.ValidateDigest(digest); err != nil {
				return err
			}
		}
		if _, err := time.Parse(time.RFC3339Nano, command.StartedAt); err != nil {
			return err
		}
		if _, err := time.Parse(time.RFC3339Nano, command.FinishedAt); err != nil {
			return err
		}
	}
	return nil
}

type boundedCommandBuffer struct {
	data  []byte
	limit int
}

func (buffer *boundedCommandBuffer) Write(data []byte) (int, error) {
	remaining := buffer.limit - len(buffer.data)
	if remaining <= 0 {
		return 0, errors.New("command output exceeds bounded capture")
	}
	written := len(data)
	if len(data) > remaining {
		buffer.data = append(buffer.data, data[:remaining]...)
		return remaining, errors.New("command output exceeds bounded capture")
	}
	buffer.data = append(buffer.data, data...)
	return written, nil
}

var _ io.Writer = (*boundedCommandBuffer)(nil)
