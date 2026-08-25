package codingfleet

import (
	"errors"
	"fmt"
	"path/filepath"
	"slices"
	"strings"

	"github.com/anvil008/swarm-coder/controlplane"
)

const FactoryManifestAPIVersion = "anvil.factory-manifest/v1"

type FactoryOperationKind string

const (
	FactoryCatalogAdd      FactoryOperationKind = "catalog-add"
	FactoryProjectionWrite FactoryOperationKind = "projection-write"
	FactoryInstallManaged  FactoryOperationKind = "install-managed"
)

type FactoryOperation struct {
	Kind   FactoryOperationKind `json:"kind"`
	Path   string               `json:"path"`
	RoleID string               `json:"roleId"`
}

type FactoryPreimage struct {
	Path   string `json:"path"`
	Exists bool   `json:"exists"`
	Digest string `json:"digest,omitempty"`
	Mode   uint32 `json:"mode,omitempty"`
}

// FactoryManifest is both the pre-mutation authority request and the final
// handoff record. Validate with a nil expectation before mutation and with the
// current result expectation after the transaction.
type FactoryManifest struct {
	APIVersion         string                       `json:"apiVersion"`
	TransactionID      string                       `json:"transactionId"`
	RequestedRoleID    string                       `json:"requestedRoleId"`
	RequestedRoleClass RoleClass                    `json:"requestedRoleClass"`
	Rationale          string                       `json:"rationale"`
	FleetRoot          string                       `json:"fleetRoot"`
	TargetProjectRoot  string                       `json:"targetProjectRoot"`
	HomeRoot           string                       `json:"homeRoot"`
	Operations         []FactoryOperation           `json:"operations"`
	Preimages          []FactoryPreimage            `json:"preimages"`
	ValidationPlan     []string                     `json:"validationPlan"`
	ReturnControlTo    string                       `json:"returnControlTo"`
	InvokedWorkflowIDs []string                     `json:"invokedWorkflowIds"`
	Result             *controlplane.WorkflowResult `json:"result,omitempty"`
}

// ValidateFactoryManifest rejects authority expansion before mutation. When
// expected is non-nil it additionally requires a current, validated workflow
// result and an orchestrator handoff.
func ValidateFactoryManifest(manifest FactoryManifest, expected *controlplane.ResultExpectation) error {
	if manifest.APIVersion != FactoryManifestAPIVersion {
		return fmt.Errorf("factory manifest apiVersion %q", manifest.APIVersion)
	}
	if err := controlplane.ValidateIdentifier(manifest.TransactionID); err != nil {
		return fmt.Errorf("factory transaction: %w", err)
	}
	if !stableIDPattern.MatchString(manifest.RequestedRoleID) || strings.HasPrefix(manifest.RequestedRoleID, "workflow-") {
		return fmt.Errorf("factory requested role %q must be a non-workflow stable ID", manifest.RequestedRoleID)
	}
	if manifest.RequestedRoleClass != ClassTechnical && manifest.RequestedRoleClass != ClassDomain {
		return fmt.Errorf("factory may create only technical or domain roles")
	}
	if strings.TrimSpace(manifest.Rationale) == "" {
		return errors.New("factory rationale is required")
	}
	fleet, target, home, err := validateFactoryRoots(manifest)
	if err != nil {
		return err
	}
	if manifest.Operations == nil || len(manifest.Operations) == 0 || manifest.Preimages == nil || manifest.ValidationPlan == nil || len(manifest.ValidationPlan) == 0 || manifest.InvokedWorkflowIDs == nil {
		return errors.New("factory operations, preimages, validation plan, and invoked workflow IDs must be explicit")
	}
	if manifest.ReturnControlTo != workflowCodingOrchestratorID || len(manifest.InvokedWorkflowIDs) != 0 {
		return errors.New("Factory must return control to the coding orchestrator without invoking a workflow")
	}
	preimages := make(map[string]FactoryPreimage, len(manifest.Preimages))
	for _, preimage := range manifest.Preimages {
		if preimage.Path == "" || preimages[preimage.Path].Path != "" {
			return fmt.Errorf("factory preimage paths must be non-empty and unique")
		}
		if preimage.Exists {
			if err := controlplane.ValidateDigest(preimage.Digest); err != nil {
				return fmt.Errorf("factory preimage %q: %w", preimage.Path, err)
			}
		} else if preimage.Digest != "" || preimage.Mode != 0 {
			return fmt.Errorf("absent factory preimage %q may not assert metadata", preimage.Path)
		}
		preimages[preimage.Path] = preimage
	}
	seen := map[string]struct{}{}
	for _, operation := range manifest.Operations {
		if operation.RoleID != manifest.RequestedRoleID {
			return fmt.Errorf("factory operation role %q does not match requested role", operation.RoleID)
		}
		key := string(operation.Kind) + "\x00" + operation.Path
		if _, duplicate := seen[key]; duplicate {
			return fmt.Errorf("duplicate factory operation %s %q", operation.Kind, operation.Path)
		}
		seen[key] = struct{}{}
		if err := validateFactoryOperation(operation, manifest.RequestedRoleID, fleet, target, home); err != nil {
			return err
		}
		if _, ok := preimages[operation.Path]; !ok {
			return fmt.Errorf("factory operation %q lacks a preimage", operation.Path)
		}
	}
	if expected == nil {
		if manifest.Result != nil {
			return errors.New("pre-mutation factory authorization may not contain a self-certified result")
		}
		return nil
	}
	if manifest.Result == nil {
		return errors.New("completed factory manifest lacks workflow result")
	}
	if expected.RoleID != workflowAgentFactoryID || expected.Lane != string(WorkflowLaneFactory) {
		return errors.New("Factory result expectation must identify the canonical Factory workflow")
	}
	if err := controlplane.ValidateWorkflowResult(*manifest.Result, *expected); err != nil {
		return fmt.Errorf("validate Factory workflow result: %w", err)
	}
	for _, path := range manifest.Result.Files {
		if _, ok := seen[string(FactoryCatalogAdd)+"\x00"+path]; ok {
			continue
		}
		if _, ok := seen[string(FactoryProjectionWrite)+"\x00"+path]; !ok {
			return fmt.Errorf("Factory result reports unowned file %q", path)
		}
	}
	return nil
}

func validateFactoryRoots(manifest FactoryManifest) (string, string, string, error) {
	for name, value := range map[string]string{"fleetRoot": manifest.FleetRoot, "targetProjectRoot": manifest.TargetProjectRoot, "homeRoot": manifest.HomeRoot} {
		if !filepath.IsAbs(value) || filepath.Clean(value) == string(filepath.Separator) {
			return "", "", "", fmt.Errorf("factory %s must be an absolute non-root path", name)
		}
	}
	fleet, target, home := filepath.Clean(manifest.FleetRoot), filepath.Clean(manifest.TargetProjectRoot), filepath.Clean(manifest.HomeRoot)
	if fleet == target || pathWithin(fleet, target) || pathWithin(target, fleet) {
		return "", "", "", errors.New("Swarm fleet root and target-project root must be distinct and non-nested")
	}
	return fleet, target, home, nil
}

func validateFactoryOperation(operation FactoryOperation, roleID, fleet, target, home string) error {
	native := nativeAgentNameForID(roleID)
	switch operation.Kind {
	case FactoryCatalogAdd:
		if operation.Path != "harness-agents/canonical/catalog.json" {
			return fmt.Errorf("Factory catalog operation may own only the canonical catalog")
		}
	case FactoryProjectionWrite:
		allowed := []string{
			filepath.ToSlash(filepath.Join("harness-agents", "rendered", "claude", native+".md")),
			filepath.ToSlash(filepath.Join("harness-agents", "rendered", "codex", native+".toml")),
			filepath.ToSlash(filepath.Join("harness-agents", "rendered", "antigravity", native, "agent.md")),
		}
		if !slices.Contains(allowed, filepath.ToSlash(operation.Path)) {
			return fmt.Errorf("Factory projection path %q is not the requested role projection", operation.Path)
		}
	case FactoryInstallManaged:
		if !filepath.IsAbs(operation.Path) || !factoryInstallerPathAllowed(filepath.Clean(operation.Path), home, native) {
			return fmt.Errorf("Factory install path %q is outside installer ownership", operation.Path)
		}
	default:
		return fmt.Errorf("unsupported Factory operation %q", operation.Kind)
	}
	resolved := operation.Path
	if !filepath.IsAbs(resolved) {
		resolved = filepath.Join(fleet, filepath.FromSlash(resolved))
	}
	resolved = filepath.Clean(resolved)
	if pathWithin(target, resolved) || resolved == target {
		return fmt.Errorf("Factory operation %q reaches the target project", operation.Path)
	}
	return nil
}

func factoryInstallerPathAllowed(path, home, native string) bool {
	allowed := []string{
		filepath.Join(home, ".claude", "agents", native+".md"),
		filepath.Join(home, ".gemini", "config", "agents", native),
		filepath.Join(home, ".codex", native+".config.toml"),
		filepath.Join(home, ".codex", "config.toml"),
		filepath.Join(home, ".agents", "AGENTS.md"),
		filepath.Join(home, ".codex", "AGENTS.md"),
		filepath.Join(home, ".claude", "CLAUDE.md"),
		filepath.Join(home, ".gemini", "GEMINI.md"),
		filepath.Join(home, ".gemini", "config", "mcp_config.json"),
	}
	return slices.Contains(allowed, path)
}

func pathWithin(root, candidate string) bool {
	relative, err := filepath.Rel(root, candidate)
	return err == nil && relative != "." && relative != ".." && !strings.HasPrefix(relative, ".."+string(filepath.Separator)) && !filepath.IsAbs(relative)
}
