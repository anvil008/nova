package codingfleet

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"strings"

	"github.com/anvil008/swarm-coder/guard"
)

const (
	guardBinaryName = "anvil-guard"
	// guardRepositoryBinary is the repository-relative build output the
	// installer links. Build it with
	// `go build -trimpath -o bin/anvil-guard ./cmd/anvil-guard`.
	guardRepositoryBinary = "bin/" + guardBinaryName

	antigravityHookHandlerKey = "anvil-coding-fleet"
	codexTrustMissingPrefix   = "codex hook trust missing "

	hookEventPreToolUse   = "PreToolUse"
	hookEventPostToolUse  = "PostToolUse"
	hookEventStop         = "Stop"
	hookEventSubagentStop = "SubagentStop"
)

// Hook events per harness. Antigravity documents no SubagentStop event.
var (
	claudeHookEvents      = []string{hookEventPreToolUse, hookEventPostToolUse, hookEventStop, hookEventSubagentStop}
	codexHookEvents       = []string{hookEventPreToolUse, hookEventPostToolUse, hookEventStop, hookEventSubagentStop}
	antigravityHookEvents = []string{hookEventPreToolUse, hookEventPostToolUse, hookEventStop}
)

type hookCommand struct {
	Type    string `json:"type"`
	Command string `json:"command"`
}

type hookMatcherGroup struct {
	Matcher string        `json:"matcher,omitempty"`
	Hooks   []hookCommand `json:"hooks"`
}

func guardInstalledPath(home string) string {
	return filepath.Join(home, ".local", "bin", guardBinaryName)
}

// skillInstalledPath is where the run-plane foreign-dispatch document lives once
// installed. The orchestrator runs with the target project as its working
// directory, so a repository-relative reference is unreachable; every rendered
// prompt cites this absolute path instead.
func skillInstalledPath(home string) string {
	return filepath.Join(home, ".local", "share", "anvil-coding-fleet", supervisorRunplaneSkillFile)
}

// guardCommandPath is the location the rendered definitions cite. Generated
// projections are committed, so they have to name one fixed home; deriving it
// from the same layout function the installer uses keeps the prompt and the
// registered hook command from drifting apart.
var guardCommandPath = guardInstalledPath(canonicalHomeDirectory)

// guardHookGroup builds the single managed matcher group for one harness event.
// Every registration names its own event: Antigravity payloads never carry one,
// and a Claude or Codex payload that fails to decode carries nothing at all --
// which is exactly when the guard has to refuse in the right dialect.
func guardHookGroup(home, harness, event string) hookMatcherGroup {
	command := guardInstalledPath(home) + " hook --harness " + harness + " --event " + event
	group := hookMatcherGroup{Hooks: []hookCommand{{Type: "command", Command: command}}}
	// The matchers come from the guard itself, so the installer can only ever
	// register tool names the guard actually recognizes.
	switch event {
	case hookEventPreToolUse:
		group.Matcher = guard.EditToolMatchers[guard.Harness(harness)]
	case hookEventPostToolUse:
		group.Matcher = guard.ShellToolMatchers[guard.Harness(harness)]
	}
	return group
}

// ownsHookGroup identifies a managed entry by the guard command path, so an
// operator's own hooks are never rewritten or removed.
func ownsHookGroup(home string, raw json.RawMessage) bool {
	var group hookMatcherGroup
	if json.Unmarshal(raw, &group) != nil {
		return false
	}
	for _, hook := range group.Hooks {
		if strings.HasPrefix(hook.Command, guardInstalledPath(home)+" ") {
			return true
		}
	}
	return false
}

func claudeHookSettingsPath(home string) string {
	return filepath.Join(home, ".claude", "settings.json")
}

func codexHookConfigPath(home string) string { return filepath.Join(home, ".codex", "hooks.json") }

func antigravityHookConfigPath(home string) string {
	return filepath.Join(home, ".gemini", "config", "hooks.json")
}

func decodeJSONDocument(pathname string) (map[string]json.RawMessage, []byte, error) {
	current, err := os.ReadFile(pathname)
	if err != nil && !errors.Is(err, fs.ErrNotExist) {
		return nil, nil, fmt.Errorf("read %s: %w", pathname, err)
	}
	document := map[string]json.RawMessage{}
	if len(bytes.TrimSpace(current)) != 0 {
		if err := json.Unmarshal(current, &document); err != nil {
			return nil, nil, fmt.Errorf("decode %s: %w", pathname, err)
		}
	}
	return document, current, nil
}

func encodeJSONDocument(document map[string]json.RawMessage) ([]byte, error) {
	if len(document) == 0 {
		return nil, nil
	}
	encoded, err := json.MarshalIndent(document, "", "  ")
	if err != nil {
		return nil, err
	}
	return append(encoded, '\n'), nil
}

// updateClaudeHookSettings owns only the guard entries inside the `hooks`
// block. Every other key and every unowned matcher group keeps its value and
// position, so the merge is JSON semantic rather than textual. A file that is
// already correct is left byte identical rather than reformatted.
func updateClaudeHookSettings(home string, mode InstallMode) ([]byte, bool, error) {
	document, current, err := decodeJSONDocument(claudeHookSettingsPath(home))
	if err != nil {
		return nil, false, err
	}
	events := map[string][]json.RawMessage{}
	if raw, ok := document["hooks"]; ok {
		if err := json.Unmarshal(raw, &events); err != nil {
			return nil, false, errors.New("Claude settings hooks must be an object of event arrays")
		}
	}
	found, err := reconcileHookEvents(home, events, claudeHookEvents, "claude", mode)
	if err != nil {
		return nil, false, err
	}
	if len(events) == 0 {
		delete(document, "hooks")
	} else {
		encoded, err := json.Marshal(events)
		if err != nil {
			return nil, false, err
		}
		document["hooks"] = encoded
	}
	updated, err := encodeJSONDocument(document)
	if err != nil {
		return nil, false, err
	}
	return sameOrUpdated(current, updated), found, nil
}

// updateCodexHookConfig appends a new managed group and refreshes an existing
// one where it sits. Codex records per-hook trust under index-based
// `[hooks.state]` keys, so moving an unowned group would silently revoke an
// operator's approval of someone else's hook.
func updateCodexHookConfig(home string, mode InstallMode) ([]byte, bool, error) {
	document, current, err := decodeJSONDocument(codexHookConfigPath(home))
	if err != nil {
		return nil, false, err
	}
	events := map[string][]json.RawMessage{}
	if raw, ok := document["hooks"]; ok {
		if err := json.Unmarshal(raw, &events); err != nil {
			return nil, false, errors.New("Codex hooks.json hooks must be an object of event arrays")
		}
	}
	found, err := reconcileHookEvents(home, events, codexHookEvents, "codex", mode)
	if err != nil {
		return nil, false, err
	}
	if len(events) == 0 {
		delete(document, "hooks")
	} else {
		encoded, err := json.Marshal(events)
		if err != nil {
			return nil, false, err
		}
		document["hooks"] = encoded
	}
	updated, err := encodeJSONDocument(document)
	if err != nil {
		return nil, false, err
	}
	return sameOrUpdated(current, updated), found, nil
}

// reconcileHookEvents rewrites each managed event array. An existing managed
// group is updated where it already sits and a new one is appended, so no
// unowned group ever changes index: Codex derives its per-hook trust keys from
// those indexes, and moving a group silently revokes an operator's approval.
func reconcileHookEvents(home string, events map[string][]json.RawMessage, wanted []string, harness string, mode InstallMode) (bool, error) {
	found := false
	managed := make(map[string]struct{}, len(wanted))
	for _, event := range wanted {
		managed[event] = struct{}{}
	}
	for event, groups := range events {
		if _, ours := managed[event]; !ours {
			continue
		}
		expected, err := json.Marshal(guardHookGroup(home, harness, event))
		if err != nil {
			return false, err
		}
		kept := make([]json.RawMessage, 0, len(groups))
		placed := false
		for _, group := range groups {
			if !ownsHookGroup(home, group) {
				kept = append(kept, group)
				continue
			}
			found = true
			if mode == InstallUninstall {
				continue
			}
			// Every owned group is refreshed where it sits, duplicates
			// included. Dropping one would shift every later group, and Codex
			// derives its per-hook trust keys from those indexes, so the
			// collapse would silently revoke an operator's approval.
			placed = true
			kept = append(kept, expected)
		}
		if mode != InstallUninstall && !placed {
			kept = append(kept, expected)
		}
		if len(kept) == 0 {
			delete(events, event)
			continue
		}
		events[event] = kept
	}
	if mode == InstallUninstall {
		return found, nil
	}
	for _, event := range wanted {
		if _, present := events[event]; present {
			continue
		}
		expected, err := json.Marshal(guardHookGroup(home, harness, event))
		if err != nil {
			return false, err
		}
		events[event] = []json.RawMessage{expected}
	}
	return found, nil
}

// updateAntigravityHookConfig owns exactly one named handler key.
func updateAntigravityHookConfig(home string, mode InstallMode) ([]byte, bool, error) {
	document, current, err := decodeJSONDocument(antigravityHookConfigPath(home))
	if err != nil {
		return nil, false, err
	}
	_, found := document[antigravityHookHandlerKey]
	if mode == InstallUninstall {
		delete(document, antigravityHookHandlerKey)
	} else {
		handler := map[string]any{"enabled": true}
		for _, event := range antigravityHookEvents {
			handler[event] = []hookMatcherGroup{guardHookGroup(home, "agy", event)}
		}
		encoded, err := json.Marshal(handler)
		if err != nil {
			return nil, false, err
		}
		document[antigravityHookHandlerKey] = encoded
	}
	updated, err := encodeJSONDocument(document)
	if err != nil {
		return nil, false, err
	}
	return sameOrUpdated(current, updated), found, nil
}

// sameOrUpdated keeps an unchanged file byte identical rather than reformatting
// it, so a no-op install never rewrites an operator's configuration.
func sameOrUpdated(current, updated []byte) []byte {
	var currentValue, updatedValue any
	if len(bytes.TrimSpace(current)) != 0 && len(bytes.TrimSpace(updated)) != 0 &&
		json.Unmarshal(current, &currentValue) == nil && json.Unmarshal(updated, &updatedValue) == nil &&
		jsonSemanticEqual(currentValue, updatedValue) {
		return append([]byte(nil), current...)
	}
	return updated
}

type hookRegistration struct {
	path   string
	update func(string, InstallMode) ([]byte, bool, error)
	label  string
	// keepWhenEmpty marks a file the installer edits but never owns. Claude's
	// settings.json carries the operator's whole configuration, so an uninstall
	// that empties it leaves `{}` rather than deleting a file the installer may
	// not have created. The two dedicated hook documents hold nothing else.
	keepWhenEmpty bool
}

func hookRegistrations(home string) []hookRegistration {
	return []hookRegistration{
		{path: claudeHookSettingsPath(home), update: updateClaudeHookSettings, label: "Claude", keepWhenEmpty: true},
		{path: codexHookConfigPath(home), update: updateCodexHookConfig, label: "Codex"},
		{path: antigravityHookConfigPath(home), update: updateAntigravityHookConfig, label: "Antigravity"},
	}
}

func reconcileHookConfigs(home string, mode InstallMode, result *InstallResult, transaction *installTransaction) error {
	for _, registration := range hookRegistrations(home) {
		current, readErr := os.ReadFile(registration.path)
		if readErr != nil && !errors.Is(readErr, fs.ErrNotExist) {
			return readErr
		}
		updated, found, err := registration.update(home, mode)
		if err != nil {
			return err
		}
		if len(updated) == 0 && registration.keepWhenEmpty && len(bytes.TrimSpace(current)) != 0 {
			updated = []byte("{}\n")
		}
		if bytes.Equal(current, updated) {
			result.Actions = append(result.Actions, "current "+registration.path)
			continue
		}
		if mode == InstallCheck {
			if !found {
				return fmt.Errorf("%s guard hook registration is missing from %s", registration.label, registration.path)
			}
			return fmt.Errorf("%s guard hook registration is stale in %s", registration.label, registration.path)
		}
		action := "update " + registration.path
		if mode == InstallUninstall {
			action = "remove managed hook registration from " + registration.path
		}
		result.Actions = append(result.Actions, action)
		if mode == InstallDryRun {
			continue
		}
		fileMode := fs.FileMode(0o600)
		if info, statErr := os.Stat(registration.path); statErr == nil {
			fileMode = info.Mode().Perm()
		}
		if len(updated) == 0 {
			if err := os.Remove(registration.path); err != nil && !errors.Is(err, fs.ErrNotExist) {
				return err
			}
		} else if err := writeFileAtomic(registration.path, updated, fileMode); err != nil {
			return fmt.Errorf("write %s atomically: %w", registration.path, err)
		}
		if err := transaction.mutated(registration.path); err != nil {
			return err
		}
	}
	if mode == InstallCheck {
		return reportCodexHookTrust(home, result)
	}
	return nil
}

// codexTrustKey mirrors the index-based key Codex records in
// `[hooks.state]` once an operator approves a hook through `/hooks`.
func codexTrustKey(home, event string, group, index int) string {
	return fmt.Sprintf("%s:%s:%d:%d", codexHookConfigPath(home), snakeCaseEvent(event), group, index)
}

func snakeCaseEvent(event string) string {
	var builder strings.Builder
	for position, character := range event {
		if character >= 'A' && character <= 'Z' {
			if position > 0 {
				builder.WriteByte('_')
			}
			character += 'a' - 'A'
		}
		builder.WriteRune(character)
	}
	return builder.String()
}

// reportCodexHookTrust names every managed Codex entry the operator has not yet
// approved. The trust hash is not reproducible, so this is a report rather than
// a failure: the fix is a one-time `/hooks` approval inside Codex.
func reportCodexHookTrust(home string, result *InstallResult) error {
	document, _, err := decodeJSONDocument(codexHookConfigPath(home))
	if err != nil {
		return err
	}
	events := map[string][]json.RawMessage{}
	if raw, ok := document["hooks"]; ok && json.Unmarshal(raw, &events) != nil {
		return errors.New("Codex hooks.json hooks must be an object of event arrays")
	}
	config, err := os.ReadFile(filepath.Join(home, ".codex", "config.toml"))
	if err != nil && !errors.Is(err, fs.ErrNotExist) {
		return err
	}
	for _, event := range codexHookEvents {
		for group, raw := range events[event] {
			if !ownsHookGroup(home, raw) {
				continue
			}
			var decoded hookMatcherGroup
			if json.Unmarshal(raw, &decoded) != nil {
				continue
			}
			for index := range decoded.Hooks {
				key := codexTrustKey(home, event, group, index)
				if bytes.Contains(config, []byte("[hooks.state.\""+key+"\"]")) {
					continue
				}
				result.Actions = append(result.Actions, codexTrustMissingPrefix+key+"; approve it once with /hooks in Codex")
			}
		}
	}
	return nil
}

// preflightHookConfigs fails closed on anything the installer cannot safely
// rewrite in place. A symlinked hook config is refused rather than followed,
// including under --check and --dry-run: writing through it would mutate a file
// outside the harness home, and a dotfiles layout that symlinks
// `~/.claude/settings.json` therefore has to register the guard hooks itself.
func preflightHookConfigs(home string, mode InstallMode) error {
	for _, registration := range hookRegistrations(home) {
		if err := rejectSymlinkComponents(home, filepath.Dir(registration.path)); err != nil {
			return fmt.Errorf("validate %s hook path: %w", registration.label, err)
		}
		if info, statErr := os.Lstat(registration.path); statErr == nil {
			if info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
				return fmt.Errorf("refuse non-regular %s hook config %s", registration.label, registration.path)
			}
		} else if !errors.Is(statErr, fs.ErrNotExist) {
			return fmt.Errorf("inspect %s hook config: %w", registration.label, statErr)
		}
		if _, _, err := registration.update(home, mode); err != nil {
			return err
		}
	}
	return nil
}
