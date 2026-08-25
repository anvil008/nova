package runplane

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

type CommandRunner interface {
	Output(context.Context, string, ...string) ([]byte, error)
}

type OSCommandRunner struct{}

func (OSCommandRunner) Output(ctx context.Context, name string, args ...string) ([]byte, error) {
	command := exec.CommandContext(ctx, name, args...)
	command.Stdin = nil
	return command.CombinedOutput()
}

type Discoverer struct {
	Runner  CommandRunner
	Roots   DefinitionRoots
	Timeout time.Duration
	static  map[Harness]Capability
}

func NewDiscoverer() Discoverer {
	return Discoverer{Runner: OSCommandRunner{}, Roots: DefaultDefinitionRoots(), Timeout: 8 * time.Second}
}

func (d Discoverer) All(ctx context.Context) []Capability {
	return []Capability{d.One(ctx, HarnessCodex), d.One(ctx, HarnessClaude), d.One(ctx, HarnessAGY)}
}

func (d Discoverer) One(ctx context.Context, harness Harness) Capability {
	if capability, ok := d.static[harness]; ok {
		return capability
	}
	capability := Capability{Harness: harness, ObservedAt: time.Now().UTC()}
	if d.Runner == nil {
		capability.Error = "capability command runner is not configured"
		return capability
	}
	timeout := d.Timeout
	if timeout <= 0 {
		timeout = 8 * time.Second
	}
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	var err error
	switch harness {
	case HarnessCodex:
		err = d.discoverCodex(ctx, &capability)
	case HarnessClaude:
		err = d.discoverClaude(ctx, &capability)
	case HarnessAGY:
		err = d.discoverAGY(ctx, &capability)
	default:
		err = fmt.Errorf("unsupported harness %q", harness)
	}
	if err != nil {
		capability.Error = err.Error()
		return capability
	}
	capability.Available = hasExactModelEffort(capability.ModelEfforts) && len(capability.Roles) > 0
	if !capability.Available {
		if len(capability.ModelEfforts) > 0 && !hasExactModelEffort(capability.ModelEfforts) {
			capability.Error = "only model aliases were observed; no authoritative exact concrete model/effort pair is launchable"
		} else {
			capability.Error = "no launchable exact model/role/effort intersection was discovered"
		}
	}
	return capability
}

func (d Discoverer) discoverCodex(ctx context.Context, out *Capability) error {
	version, err := d.Runner.Output(ctx, "codex", "--version")
	if err != nil {
		return commandDiscoveryError("codex --version", version, err)
	}
	help, err := d.Runner.Output(ctx, "codex", "exec", "--help")
	if err != nil {
		return commandDiscoveryError("codex exec --help", help, err)
	}
	resume, err := d.Runner.Output(ctx, "codex", "exec", "resume", "--help")
	if err != nil {
		return commandDiscoveryError("codex exec resume --help", resume, err)
	}
	if !bytesContainAll(help, "--profile", "--model", "--json", "read from stdin") || !bytesContainAll(resume, "SESSION_ID", "read from stdin") {
		return errors.New("installed codex help does not expose the required headless stdin/resume contract")
	}
	out.Version = strings.TrimSpace(string(version))
	_, _, roles := d.installedRoleMetadata(HarnessCodex, nil)
	out.Roles = roles
	if err := d.loadCodexModelEfforts(out); err != nil {
		return err
	}
	out.SupportsResume = true
	out.SupportsSend = false
	return nil
}

func (d Discoverer) discoverClaude(ctx context.Context, out *Capability) error {
	version, err := d.Runner.Output(ctx, "claude", "--version")
	if err != nil {
		return commandDiscoveryError("claude --version", version, err)
	}
	help, err := d.Runner.Output(ctx, "claude", "--help")
	if err != nil {
		return commandDiscoveryError("claude --help", help, err)
	}
	if !bytesContainAll(help, "--agent", "--agents", "--setting-sources", "--model", "--effort", "--input-format", "stream-json", "--output-format", "--resume") {
		return errors.New("installed claude help does not expose the required agent/model/stream/resume contract")
	}
	out.Version = strings.TrimSpace(string(version))
	advertisedEfforts := stringSet(parseChoiceList(string(help), "--effort <level>"))
	document, err := codingFleetBindings()
	if err != nil {
		return err
	}
	modelSet, effortSet, roleSet, pairSet := map[string]struct{}{}, map[string]struct{}{}, map[string]struct{}{}, map[string]struct{}{}
	for _, binding := range document {
		path, pathErr := d.Roots.definitionPath(HarnessClaude, binding.NativeName)
		if pathErr != nil {
			continue
		}
		data, readErr := os.ReadFile(path)
		if readErr != nil {
			continue
		}
		if _, verifyErr := d.Roots.verifyExactDefinition(HarnessClaude, binding); verifyErr != nil {
			continue
		}
		agent, parseErr := parseCanonicalClaudeAgent(data, binding.NativeName)
		if parseErr != nil {
			continue
		}
		if _, ok := advertisedEfforts[agent.Effort]; !ok {
			continue
		}
		pairKey := agent.Model + "\x00" + agent.Effort
		if _, duplicate := pairSet[pairKey]; !duplicate {
			out.ModelEfforts = append(out.ModelEfforts, ModelEffort{Provider: "anthropic", Family: "claude", Model: agent.Model, Effort: agent.Effort, Reference: "alias"})
			pairSet[pairKey] = struct{}{}
		}
		modelSet[agent.Model], effortSet[agent.Effort], roleSet[binding.NativeName] = struct{}{}, struct{}{}, struct{}{}
	}
	out.Models, out.Efforts, out.Roles = sortedKeys(modelSet), sortedKeys(effortSet), sortedKeys(roleSet)
	sort.Slice(out.ModelEfforts, func(i, j int) bool {
		if out.ModelEfforts[i].Model == out.ModelEfforts[j].Model {
			return out.ModelEfforts[i].Effort < out.ModelEfforts[j].Effort
		}
		return out.ModelEfforts[i].Model < out.ModelEfforts[j].Model
	})
	out.SupportsResume = true
	out.SupportsSend = true
	return nil
}

func (d Discoverer) discoverAGY(ctx context.Context, out *Capability) error {
	version, err := d.Runner.Output(ctx, "agy", "--version")
	if err != nil {
		return commandDiscoveryError("agy --version", version, err)
	}
	help, err := d.Runner.Output(ctx, "agy", "--help")
	if err != nil {
		return commandDiscoveryError("agy --help", help, err)
	}
	if !bytesContainAll(help, "--agent", "--model", "--effort", "--input-format", "stream-json", "--output-format", "--conversation", "--sandbox") {
		return errors.New("installed agy help does not expose the required agent/model/stream/resume/sandbox contract")
	}
	modelsOutput, err := d.Runner.Output(ctx, "agy", "models")
	if err != nil {
		return commandDiscoveryError("agy models", modelsOutput, err)
	}
	agentsOutput, err := d.Runner.Output(ctx, "agy", "agents")
	if err != nil {
		return commandDiscoveryError("agy agents", agentsOutput, err)
	}
	out.Version = strings.TrimSpace(string(version))
	out.Models = firstFields(modelsOutput)
	out.Efforts = parseChoiceList(string(help), "--effort")
	for _, model := range out.Models {
		for _, effort := range out.Efforts {
			if strings.HasSuffix(model, "-"+effort) {
				out.ModelEfforts = append(out.ModelEfforts, ModelEffort{Provider: "google", Family: "gemini", Model: model, Effort: effort, Reference: "exact"})
			}
		}
	}
	advertised := stringSet(firstFields(agentsOutput))
	_, _, installed := d.installedRoleMetadata(HarnessAGY, nil)
	for _, role := range installed {
		if _, ok := advertised[role]; ok {
			out.Roles = append(out.Roles, role)
		}
	}
	sort.Strings(out.Roles)
	out.SupportsResume = true
	out.SupportsSend = true
	return nil
}

func (d Discoverer) loadCodexModelEfforts(out *Capability) error {
	data, err := os.ReadFile(filepath.Join(d.Roots.CodexHome, "models_cache.json"))
	if err != nil {
		return fmt.Errorf("read current codex model cache: %w", err)
	}
	var cache struct {
		ClientVersion string `json:"client_version"`
		Models        []struct {
			Slug       string `json:"slug"`
			Visibility string `json:"visibility"`
			Supported  []struct {
				Effort string `json:"effort"`
			} `json:"supported_reasoning_levels"`
		} `json:"models"`
	}
	if err := json.Unmarshal(data, &cache); err != nil {
		return fmt.Errorf("decode current codex model cache: %w", err)
	}
	if cache.ClientVersion == "" || !strings.Contains(out.Version, cache.ClientVersion) {
		return fmt.Errorf("codex model cache version %q does not match installed %q", cache.ClientVersion, out.Version)
	}
	modelSet, effortSet := map[string]struct{}{}, map[string]struct{}{}
	for _, model := range cache.Models {
		if model.Slug == "" || model.Visibility != "list" {
			continue
		}
		for _, level := range model.Supported {
			if level.Effort == "" {
				continue
			}
			out.ModelEfforts = append(out.ModelEfforts, ModelEffort{Provider: "openai", Family: "gpt", Model: model.Slug, Effort: level.Effort, Reference: "exact"})
			modelSet[model.Slug] = struct{}{}
			effortSet[level.Effort] = struct{}{}
		}
	}
	out.Models, out.Efforts = sortedKeys(modelSet), sortedKeys(effortSet)
	sort.Slice(out.ModelEfforts, func(i, j int) bool {
		if out.ModelEfforts[i].Model == out.ModelEfforts[j].Model {
			return out.ModelEfforts[i].Effort < out.ModelEfforts[j].Effort
		}
		return out.ModelEfforts[i].Model < out.ModelEfforts[j].Model
	})
	return nil
}

func hasExactModelEffort(values []ModelEffort) bool {
	for _, value := range values {
		if value.Reference == "" || value.Reference == "exact" {
			return true
		}
	}
	return false
}

func (d Discoverer) installedRoleMetadata(harness Harness, extra func(roleBinding, string, []byte) bool) (models, efforts, roles []string) {
	document, err := codingFleetBindings()
	if err != nil {
		return nil, nil, nil
	}
	modelSet, effortSet, roleSet := map[string]struct{}{}, map[string]struct{}{}, map[string]struct{}{}
	for _, binding := range document {
		path, err := d.Roots.definitionPath(harness, binding.NativeName)
		if err != nil {
			continue
		}
		data, err := os.ReadFile(path)
		if err != nil {
			continue
		}
		if _, err := d.Roots.verifyExactDefinition(harness, binding); err != nil {
			continue
		}
		if extra != nil && !extra(binding, path, data) {
			continue
		}
		roleSet[binding.NativeName] = struct{}{}
		if model := metadataValue(data, "model"); model != "" {
			modelSet[model] = struct{}{}
		}
		if effort := metadataValue(data, "model_reasoning_effort"); effort != "" {
			effortSet[effort] = struct{}{}
		}
	}
	return sortedKeys(modelSet), sortedKeys(effortSet), sortedKeys(roleSet)
}

func codingFleetBindings() ([]roleBinding, error) {
	// Loading by ID keeps this package on the public, validated catalog API and
	// avoids depending on Factory's renderer internals.
	ids, err := canonicalRoleIDs()
	if err != nil {
		return nil, err
	}
	bindings := make([]roleBinding, 0, len(ids))
	for _, id := range ids {
		binding, err := loadRoleBinding(id)
		if err == nil { // orchestrator and non-runnable modes are intentionally skipped.
			bindings = append(bindings, binding)
		}
	}
	return bindings, nil
}

func canonicalRoleIDs() ([]string, error) {
	document, err := loadCatalogDocument()
	if err != nil {
		return nil, err
	}
	ids := make([]string, 0, len(document))
	for _, id := range document {
		ids = append(ids, id)
	}
	return ids, nil
}

func metadataValue(data []byte, key string) string {
	scanner := bufio.NewScanner(strings.NewReader(string(data)))
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if !strings.HasPrefix(line, key) {
			continue
		}
		line = strings.TrimSpace(strings.TrimPrefix(line, key))
		line = strings.TrimSpace(strings.TrimPrefix(line, ":"))
		line = strings.TrimSpace(strings.TrimPrefix(line, "="))
		return strings.Trim(strings.TrimSpace(line), "\"")
	}
	return ""
}

func firstFields(data []byte) []string {
	set := map[string]struct{}{}
	scanner := bufio.NewScanner(strings.NewReader(string(data)))
	for scanner.Scan() {
		fields := strings.Fields(scanner.Text())
		if len(fields) > 0 && !strings.HasPrefix(fields[0], "Fetching") {
			set[fields[0]] = struct{}{}
		}
	}
	return sortedKeys(set)
}

func parseChoiceList(help, marker string) []string {
	position := strings.Index(help, marker)
	if position < 0 {
		return nil
	}
	window := help[position:]
	if len(window) > 512 {
		window = window[:512]
	}
	start := strings.Index(window, "(")
	end := strings.Index(window, ")")
	if start >= 0 && end > start {
		parts := strings.FieldsFunc(window[start+1:end], func(r rune) bool { return r == '|' || r == ',' || r == ' ' })
		return sortedUnique(parts)
	}
	return nil
}

func commandDiscoveryError(command string, output []byte, err error) error {
	message := strings.TrimSpace(string(output))
	if len(message) > 256 {
		message = message[:256]
	}
	if message == "" {
		return fmt.Errorf("%s: %w", command, err)
	}
	if redacted, ok := redactValue(message).(string); ok {
		message = redacted
	}
	return fmt.Errorf("%s: %w: %s", command, err, message)
}

func bytesContainAll(data []byte, values ...string) bool {
	text := string(data)
	for _, value := range values {
		if !strings.Contains(text, value) {
			return false
		}
	}
	return true
}

func sortedUnique(values []string) []string { return sortedKeys(stringSet(values)) }
func stringSet(values []string) map[string]struct{} {
	set := make(map[string]struct{}, len(values))
	for _, value := range values {
		if value = strings.TrimSpace(value); value != "" {
			set[value] = struct{}{}
		}
	}
	return set
}
func sortedKeys(set map[string]struct{}) []string {
	values := make([]string, 0, len(set))
	for value := range set {
		values = append(values, value)
	}
	sort.Strings(values)
	return values
}
