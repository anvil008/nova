package runplane

import (
	"bytes"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/anvil008/swarm-coder/codingfleet"
)

type roleBinding struct {
	CanonicalID   string
	NativeName    string
	Instructions  string
	Digest        string
	CatalogDigest string
	Authority     codingfleet.AuthorityProfile
	Class         codingfleet.RoleClass
	Mode          CapabilityMode
}

func loadRoleBinding(roleID string) (roleBinding, error) {
	document, err := codingfleet.Load()
	if err != nil {
		return roleBinding{}, fmt.Errorf("load canonical coding fleet: %w", err)
	}
	for _, role := range document.Roles {
		if role.ID != roleID {
			continue
		}
		if role.ID == "workflow-coding-orchestrator" {
			return roleBinding{}, fmt.Errorf("canonical role %q is the orchestrator and cannot be launched by the run plane", roleID)
		}
		mode := CapabilityMode(role.CapabilityMode)
		if mode != ModeReadOnly && mode != ModeWorkspaceWrite {
			return roleBinding{}, fmt.Errorf("canonical role %q has unsupported capability mode %q", roleID, role.CapabilityMode)
		}
		native := "anvil-cf-" + role.ID
		if strings.HasPrefix(role.ID, "workflow-") {
			native = "anvil-wf-" + strings.TrimPrefix(role.ID, "workflow-")
		}
		roleDigest, err := codingfleet.RoleDigest(document, role.ID)
		if err != nil {
			return roleBinding{}, err
		}
		catalogDigest, err := codingfleet.CatalogDigest(document)
		if err != nil {
			return roleBinding{}, err
		}
		authority, err := codingfleet.AuthorityForRole(document, role.ID)
		if err != nil {
			return roleBinding{}, err
		}
		return roleBinding{CanonicalID: role.ID, NativeName: native, Instructions: role.Instructions, Digest: roleDigest, CatalogDigest: catalogDigest, Authority: authority, Class: role.Class, Mode: mode}, nil
	}
	return roleBinding{}, fmt.Errorf("canonical role %q does not exist", roleID)
}

type DefinitionRoots struct {
	HomeDir   string
	CodexHome string
}

func DefaultDefinitionRoots() DefinitionRoots {
	home, _ := os.UserHomeDir()
	codexHome := os.Getenv("CODEX_HOME")
	if codexHome == "" {
		codexHome = filepath.Join(home, ".codex")
	}
	return DefinitionRoots{HomeDir: home, CodexHome: codexHome}
}

func (r DefinitionRoots) definitionPath(harness Harness, native string) (string, error) {
	switch harness {
	case HarnessCodex:
		return filepath.Join(r.CodexHome, native+".config.toml"), nil
	case HarnessClaude:
		return filepath.Join(r.HomeDir, ".claude", "agents", "anvil-coding-fleet", native+".md"), nil
	case HarnessAGY:
		return filepath.Join(r.HomeDir, ".gemini", "config", "agents", native, "agent.md"), nil
	default:
		return "", fmt.Errorf("unsupported harness %q", harness)
	}
}

func (r DefinitionRoots) verifyExactDefinition(harness Harness, binding roleBinding) (string, error) {
	path, err := r.definitionPath(harness, binding.NativeName)
	if err != nil {
		return "", err
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return "", fmt.Errorf("read installed %s role %q: %w", harness, binding.NativeName, err)
	}
	expected, err := expectedDefinition(harness, binding.NativeName)
	if err != nil {
		return "", err
	}
	if !bytes.Equal(data, expected) {
		return "", fmt.Errorf("installed %s role %q differs byte-for-byte from its canonical generated definition", harness, binding.NativeName)
	}
	return path, nil
}

func expectedDefinition(harness Harness, native string) ([]byte, error) {
	document, err := codingfleet.Load()
	if err != nil {
		return nil, err
	}
	rendered, err := codingfleet.Render("/swarm", document)
	if err != nil {
		return nil, err
	}
	prefix, suffix := "", ""
	switch harness {
	case HarnessCodex:
		prefix, suffix = "codex/", ".toml"
	case HarnessClaude:
		prefix, suffix = "claude/", ".md"
	case HarnessAGY:
		prefix, suffix = "antigravity/", "/agent.md"
	default:
		return nil, fmt.Errorf("unsupported harness %q", harness)
	}
	wanted := prefix + native + suffix
	for _, file := range rendered.Files {
		if filepath.ToSlash(file.Path) == wanted {
			return append([]byte(nil), file.Content...), nil
		}
	}
	return nil, fmt.Errorf("canonical generated definition %q not found", wanted)
}
