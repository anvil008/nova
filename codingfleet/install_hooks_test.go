package codingfleet

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func readJSONFile(t *testing.T, pathname string) map[string]json.RawMessage {
	t.Helper()
	raw, err := os.ReadFile(pathname)
	if err != nil {
		t.Fatalf("read %s: %v", pathname, err)
	}
	document := map[string]json.RawMessage{}
	if err := json.Unmarshal(raw, &document); err != nil {
		t.Fatalf("decode %s: %v", pathname, err)
	}
	return document
}

func TestInstallRegistersGuardHooksForEveryHarness(t *testing.T) {
	home, repositoryRoot := installerFixture(t)
	guard := guardInstalledPath(home)

	claudeSettings := filepath.Join(home, ".claude", "settings.json")
	if err := os.MkdirAll(filepath.Dir(claudeSettings), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(claudeSettings, []byte(`{"model":"opus","hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"personal-audit"}]}]}}`), 0o600); err != nil {
		t.Fatal(err)
	}

	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallApply}); err != nil {
		t.Fatal(err)
	}

	settings := readJSONFile(t, claudeSettings)
	if string(settings["model"]) != `"opus"` {
		t.Fatalf("unowned Claude settings changed: %s", settings["model"])
	}
	var claudeHooks map[string][]hookMatcherGroup
	if err := json.Unmarshal(settings["hooks"], &claudeHooks); err != nil {
		t.Fatal(err)
	}
	if len(claudeHooks["PreToolUse"]) != 2 || claudeHooks["PreToolUse"][0].Hooks[0].Command != "personal-audit" {
		t.Fatalf("unowned Claude hook lost: %+v", claudeHooks["PreToolUse"])
	}
	// Every registration names its own event: a hook that has to infer the
	// event from the payload cannot classify a payload it failed to decode.
	wantClaude := func(event string) string { return guard + " hook --harness claude --event " + event }
	if claudeHooks["PreToolUse"][1].Matcher != "Edit|Write|MultiEdit|NotebookEdit" || claudeHooks["PreToolUse"][1].Hooks[0].Command != wantClaude("PreToolUse") {
		t.Fatalf("Claude PreToolUse registration = %+v", claudeHooks["PreToolUse"][1])
	}
	for _, event := range []string{"PostToolUse", "Stop", "SubagentStop"} {
		if len(claudeHooks[event]) != 1 || claudeHooks[event][0].Hooks[0].Command != wantClaude(event) {
			t.Fatalf("Claude %s registration = %+v", event, claudeHooks[event])
		}
	}

	codexHooks := readJSONFile(t, filepath.Join(home, ".codex", "hooks.json"))
	var codexEvents map[string][]hookMatcherGroup
	if err := json.Unmarshal(codexHooks["hooks"], &codexEvents); err != nil {
		t.Fatal(err)
	}
	if codexEvents["PreToolUse"][0].Matcher != "apply_patch" || codexEvents["PreToolUse"][0].Hooks[0].Command != guard+" hook --harness codex --event PreToolUse" {
		t.Fatalf("Codex PreToolUse registration = %+v", codexEvents["PreToolUse"])
	}
	for _, event := range codexHookEvents {
		if len(codexEvents[event]) != 1 || codexEvents[event][0].Hooks[0].Command != guard+" hook --harness codex --event "+event {
			t.Fatalf("Codex %s registration = %+v", event, codexEvents[event])
		}
	}

	agyHooks := readJSONFile(t, filepath.Join(home, ".gemini", "config", "hooks.json"))
	var handler struct {
		Enabled     bool               `json:"enabled"`
		PreToolUse  []hookMatcherGroup `json:"PreToolUse"`
		PostToolUse []hookMatcherGroup `json:"PostToolUse"`
		Stop        []hookMatcherGroup `json:"Stop"`
	}
	if err := json.Unmarshal(agyHooks[antigravityHookHandlerKey], &handler); err != nil {
		t.Fatal(err)
	}
	if !handler.Enabled || handler.PreToolUse[0].Matcher != "write_to_file|replace_file_content|multi_replace_file_content" {
		t.Fatalf("Antigravity handler = %+v", handler)
	}
	if handler.Stop[0].Hooks[0].Command != guard+" hook --harness agy --event Stop" {
		t.Fatalf("Antigravity Stop command = %q", handler.Stop[0].Hooks[0].Command)
	}

	before := snapshotInstalledHarnessState(t, home)
	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallApply}); err != nil {
		t.Fatal(err)
	}
	if after := snapshotInstalledHarnessState(t, home); len(after) != len(before) {
		t.Fatal("second install changed the managed hook surface")
	}
	for pathname, state := range before {
		if after := snapshotInstalledHarnessState(t, home)[pathname]; after != state {
			t.Fatalf("hook registration is not idempotent at %s", pathname)
		}
	}

	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallUninstall}); err != nil {
		t.Fatal(err)
	}
	settings = readJSONFile(t, claudeSettings)
	remaining := map[string][]hookMatcherGroup{}
	if err := json.Unmarshal(settings["hooks"], &remaining); err != nil {
		t.Fatal(err)
	}
	claudeHooks = remaining
	if len(claudeHooks["PreToolUse"]) != 1 || claudeHooks["PreToolUse"][0].Hooks[0].Command != "personal-audit" {
		t.Fatalf("uninstall did not restore the unowned Claude hooks: %+v", claudeHooks)
	}
	if _, ok := claudeHooks["Stop"]; ok {
		t.Fatalf("uninstall left a managed Stop hook: %+v", claudeHooks["Stop"])
	}
	// The handler was the only key, so uninstall restores the pre-install absence.
	if _, err := os.Lstat(filepath.Join(home, ".gemini", "config", "hooks.json")); !os.IsNotExist(err) {
		t.Fatalf("uninstall left the Antigravity hook config: %v", err)
	}
}

func TestInstallAppendsCodexHookGroupsWithoutReordering(t *testing.T) {
	home, repositoryRoot := installerFixture(t)
	hooksPath := filepath.Join(home, ".codex", "hooks.json")
	if err := os.MkdirAll(filepath.Dir(hooksPath), 0o755); err != nil {
		t.Fatal(err)
	}
	original := `{"hooks":{"PreToolUse":[{"matcher":"first","hooks":[{"type":"command","command":"first-hook"}]},{"matcher":"second","hooks":[{"type":"command","command":"second-hook"}]}]}}`
	if err := os.WriteFile(hooksPath, []byte(original), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallApply}); err != nil {
		t.Fatal(err)
	}
	var document struct {
		Hooks map[string][]hookMatcherGroup `json:"hooks"`
	}
	raw, err := os.ReadFile(hooksPath)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(raw, &document); err != nil {
		t.Fatal(err)
	}
	groups := document.Hooks["PreToolUse"]
	if len(groups) != 3 || groups[0].Matcher != "first" || groups[1].Matcher != "second" {
		t.Fatalf("Codex trust indexes were disturbed: %+v", groups)
	}
	if groups[2].Hooks[0].Command != guardInstalledPath(home)+" hook --harness codex --event PreToolUse" {
		t.Fatalf("managed group was not appended last: %+v", groups[2])
	}
}

func TestInstallCheckReportsMissingCodexHookTrust(t *testing.T) {
	home, repositoryRoot := installerFixture(t)
	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallApply}); err != nil {
		t.Fatal(err)
	}
	result, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallCheck})
	if err != nil {
		t.Fatal(err)
	}
	missing := make([]string, 0)
	for _, action := range result.Actions {
		if strings.HasPrefix(action, codexTrustMissingPrefix) {
			missing = append(missing, action)
		}
	}
	if len(missing) != 4 {
		t.Fatalf("expected one trust report per registered Codex event, got %v", missing)
	}
	wantKey := filepath.Join(home, ".codex", "hooks.json") + ":pre_tool_use:0:0"
	if !strings.Contains(strings.Join(missing, "\n"), wantKey) {
		t.Fatalf("trust report does not name the index-based key %q: %v", wantKey, missing)
	}

	configPath := filepath.Join(home, ".codex", "config.toml")
	config, err := os.ReadFile(configPath)
	if err != nil {
		t.Fatal(err)
	}
	trusted := string(config)
	for _, event := range codexHookEvents {
		trusted += "\n[hooks.state.\"" + codexTrustKey(home, event, 0, 0) + "\"]\napproved = true\n"
	}
	if err := os.WriteFile(configPath, []byte(trusted), 0o600); err != nil {
		t.Fatal(err)
	}
	result, err = Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallCheck})
	if err != nil {
		t.Fatal(err)
	}
	for _, action := range result.Actions {
		if strings.HasPrefix(action, codexTrustMissingPrefix) {
			t.Fatalf("trust reported missing after approval: %q", action)
		}
	}
}

func TestInstallLinksTheGuardBinary(t *testing.T) {
	home, repositoryRoot := installerFixture(t)
	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallApply}); err != nil {
		t.Fatal(err)
	}
	link := guardInstalledPath(home)
	target, err := os.Readlink(link)
	if err != nil || target != filepath.Join(repositoryRoot, guardRepositoryBinary) {
		t.Fatalf("Readlink(%s) = %q, %v", link, target, err)
	}
	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallUninstall}); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Lstat(link); !os.IsNotExist(err) {
		t.Fatalf("uninstall left the guard link: %v", err)
	}
}

func TestInstallDryRunReportsHooksWithoutWriting(t *testing.T) {
	home, repositoryRoot := installerFixture(t)
	result, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallDryRun})
	if err != nil {
		t.Fatal(err)
	}
	joined := strings.Join(result.Actions, "\n")
	for _, want := range []string{
		"link " + guardInstalledPath(home),
		"update " + filepath.Join(home, ".claude", "settings.json"),
		"update " + filepath.Join(home, ".codex", "hooks.json"),
		"update " + filepath.Join(home, ".gemini", "config", "hooks.json"),
	} {
		if !strings.Contains(joined, want) {
			t.Fatalf("dry run does not report %q:\n%s", want, joined)
		}
	}
	for _, pathname := range []string{
		filepath.Join(home, ".claude", "settings.json"),
		filepath.Join(home, ".codex", "hooks.json"),
		filepath.Join(home, ".gemini", "config", "hooks.json"),
		guardInstalledPath(home),
	} {
		if _, err := os.Lstat(pathname); !os.IsNotExist(err) {
			t.Fatalf("dry run wrote %s: %v", pathname, err)
		}
	}
}

func TestInstallUpdatesAStaleHookGroupInPlace(t *testing.T) {
	home, repositoryRoot := installerFixture(t)
	hooksPath := filepath.Join(home, ".codex", "hooks.json")
	if err := os.MkdirAll(filepath.Dir(hooksPath), 0o755); err != nil {
		t.Fatal(err)
	}
	stale := `{"hooks":{"PreToolUse":[` +
		`{"matcher":"stale","hooks":[{"type":"command","command":"` + guardInstalledPath(home) + ` hook --harness codex --event Stale"}]},` +
		`{"matcher":"trusted","hooks":[{"type":"command","command":"operator-hook"}]}]}}`
	if err := os.WriteFile(hooksPath, []byte(stale), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallApply}); err != nil {
		t.Fatal(err)
	}
	var document struct {
		Hooks map[string][]hookMatcherGroup `json:"hooks"`
	}
	raw, err := os.ReadFile(hooksPath)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(raw, &document); err != nil {
		t.Fatal(err)
	}
	groups := document.Hooks["PreToolUse"]
	if len(groups) != 2 {
		t.Fatalf("stale managed group was duplicated instead of replaced: %+v", groups)
	}
	if groups[0].Matcher != "apply_patch" || groups[0].Hooks[0].Command != guardInstalledPath(home)+" hook --harness codex --event PreToolUse" {
		t.Fatalf("managed group was not refreshed in place: %+v", groups[0])
	}
	// The operator's already-trusted hook must keep its index-based trust key.
	if groups[1].Hooks[0].Command != "operator-hook" {
		t.Fatalf("unowned group changed index: %+v", groups)
	}
}

func TestUninstallLeavesAnEmptyClaudeSettingsDocument(t *testing.T) {
	home, repositoryRoot := installerFixture(t)
	settingsPath := filepath.Join(home, ".claude", "settings.json")
	if err := os.MkdirAll(filepath.Dir(settingsPath), 0o755); err != nil {
		t.Fatal(err)
	}
	// A settings file the operator created, holding nothing the installer owns.
	if err := os.WriteFile(settingsPath, []byte("{}\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallApply}); err != nil {
		t.Fatal(err)
	}
	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallUninstall}); err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(settingsPath)
	if err != nil {
		t.Fatalf("uninstall deleted a settings file the installer did not create: %v", err)
	}
	document := map[string]json.RawMessage{}
	if err := json.Unmarshal(raw, &document); err != nil {
		t.Fatalf("decode %s: %v", settingsPath, err)
	}
	if len(document) != 0 {
		t.Fatalf("uninstall left managed state behind: %s", raw)
	}
}

func TestInstallRefreshesEveryOwnedCodexGroupWithoutShiftingIndexes(t *testing.T) {
	home, repositoryRoot := installerFixture(t)
	hooksPath := filepath.Join(home, ".codex", "hooks.json")
	if err := os.MkdirAll(filepath.Dir(hooksPath), 0o755); err != nil {
		t.Fatal(err)
	}
	guard := guardInstalledPath(home)
	// Two owned groups in one event array. Dropping the second shifts the
	// trusted operator group that follows it, revoking its Codex trust key.
	seeded := `{"hooks":{"PreToolUse":[` +
		`{"matcher":"operator-first","hooks":[{"type":"command","command":"operator-first-hook"}]},` +
		`{"matcher":"stale-one","hooks":[{"type":"command","command":"` + guard + ` hook --harness codex --event One"}]},` +
		`{"matcher":"stale-two","hooks":[{"type":"command","command":"` + guard + ` hook --harness codex --event Two"}]},` +
		`{"matcher":"operator-last","hooks":[{"type":"command","command":"operator-last-hook"}]}]}}`
	if err := os.WriteFile(hooksPath, []byte(seeded), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallApply}); err != nil {
		t.Fatal(err)
	}
	var document struct {
		Hooks map[string][]hookMatcherGroup `json:"hooks"`
	}
	raw, err := os.ReadFile(hooksPath)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(raw, &document); err != nil {
		t.Fatal(err)
	}
	groups := document.Hooks["PreToolUse"]
	if len(groups) != 4 {
		t.Fatalf("owned duplicate was dropped, shifting later trust indexes: %+v", groups)
	}
	if groups[0].Hooks[0].Command != "operator-first-hook" || groups[3].Hooks[0].Command != "operator-last-hook" {
		t.Fatalf("unowned groups moved: %+v", groups)
	}
	want := guard + " hook --harness codex --event PreToolUse"
	for _, index := range []int{1, 2} {
		if groups[index].Matcher != "apply_patch" || groups[index].Hooks[0].Command != want {
			t.Fatalf("owned group %d was not refreshed in place: %+v", index, groups[index])
		}
	}
}

func TestInstallRejectsAMalformedHookConfig(t *testing.T) {
	for _, relative := range []string{
		filepath.Join(".claude", "settings.json"),
		filepath.Join(".codex", "hooks.json"),
		filepath.Join(".gemini", "config", "hooks.json"),
	} {
		t.Run(relative, func(t *testing.T) {
			home, repositoryRoot := installerFixture(t)
			pathname := filepath.Join(home, relative)
			if err := os.MkdirAll(filepath.Dir(pathname), 0o755); err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(pathname, []byte("{not json"), 0o600); err != nil {
				t.Fatal(err)
			}
			for _, mode := range []InstallMode{InstallDryRun, InstallCheck, InstallApply, InstallUninstall} {
				if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: mode}); err == nil {
					t.Fatalf("%s accepted a malformed %s", mode, pathname)
				}
			}
			raw, err := os.ReadFile(pathname)
			if err != nil || string(raw) != "{not json" {
				t.Fatalf("a rejected install rewrote %s: %q %v", pathname, raw, err)
			}
		})
	}
}

func TestInstallRefusesANonRegularHookConfig(t *testing.T) {
	home, repositoryRoot := installerFixture(t)
	settingsPath := filepath.Join(home, ".claude", "settings.json")
	if err := os.MkdirAll(filepath.Dir(settingsPath), 0o755); err != nil {
		t.Fatal(err)
	}
	elsewhere := filepath.Join(t.TempDir(), "settings.json")
	if err := os.WriteFile(elsewhere, []byte("{}\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(elsewhere, settingsPath); err != nil {
		t.Fatal(err)
	}
	for _, mode := range []InstallMode{InstallDryRun, InstallCheck, InstallApply} {
		_, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: mode})
		if err == nil || !strings.Contains(err.Error(), "non-regular") {
			t.Fatalf("%s accepted a symlinked settings file: %v", mode, err)
		}
	}
}

func TestUninstallPreservesUnownedCodexGroups(t *testing.T) {
	home, repositoryRoot := installerFixture(t)
	hooksPath := filepath.Join(home, ".codex", "hooks.json")
	if err := os.MkdirAll(filepath.Dir(hooksPath), 0o755); err != nil {
		t.Fatal(err)
	}
	seeded := `{"hooks":{"PreToolUse":[{"matcher":"operator","hooks":[{"type":"command","command":"operator-hook"}]}],` +
		`"PreCompact":[{"matcher":"operator","hooks":[{"type":"command","command":"unmanaged-event-hook"}]}]}}`
	if err := os.WriteFile(hooksPath, []byte(seeded), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallApply}); err != nil {
		t.Fatal(err)
	}
	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallUninstall}); err != nil {
		t.Fatal(err)
	}
	var document struct {
		Hooks map[string][]hookMatcherGroup `json:"hooks"`
	}
	raw, err := os.ReadFile(hooksPath)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(raw, &document); err != nil {
		t.Fatal(err)
	}
	if len(document.Hooks["PreToolUse"]) != 1 || document.Hooks["PreToolUse"][0].Hooks[0].Command != "operator-hook" {
		t.Fatalf("uninstall disturbed the operator's Codex hooks: %+v", document.Hooks["PreToolUse"])
	}
	if len(document.Hooks["PreCompact"]) != 1 {
		t.Fatalf("uninstall touched an unmanaged event: %+v", document.Hooks["PreCompact"])
	}
	for event, groups := range document.Hooks {
		for _, group := range groups {
			for _, hook := range group.Hooks {
				if strings.HasPrefix(hook.Command, guardInstalledPath(home)+" ") {
					t.Fatalf("uninstall left a managed %s registration: %+v", event, group)
				}
			}
		}
	}
}

func TestInstallManagesTheRunplaneSkillDocument(t *testing.T) {
	home, repositoryRoot := installerFixture(t)
	installed := skillInstalledPath(home)
	source := filepath.Join(repositoryRoot, filepath.FromSlash(supervisorRunplaneSkillSource))

	dryRun, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallDryRun})
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(strings.Join(dryRun.Actions, "\n"), "link "+installed) {
		t.Fatalf("dry run does not report the skill artifact:\n%s", strings.Join(dryRun.Actions, "\n"))
	}
	if _, err := os.Lstat(installed); !os.IsNotExist(err) {
		t.Fatalf("dry run wrote %s: %v", installed, err)
	}

	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallApply}); err != nil {
		t.Fatal(err)
	}
	target, err := os.Readlink(installed)
	if err != nil || target != source {
		t.Fatalf("Readlink(%s) = %q, %v; want %q", installed, target, err, source)
	}
	content, err := os.ReadFile(installed)
	if err != nil || !strings.Contains(string(content), "swarm-runplane") {
		t.Fatalf("installed skill is not readable: %v", err)
	}
	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallCheck}); err != nil {
		t.Fatalf("check rejected a freshly installed skill: %v", err)
	}
	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallApply}); err != nil {
		t.Fatalf("second install was not idempotent: %v", err)
	}

	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallUninstall}); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Lstat(installed); !os.IsNotExist(err) {
		t.Fatalf("uninstall left the skill artifact: %v", err)
	}
}

// `bin/` is gitignored, so a `git clean` or a repository move can leave the
// installed hook command dangling. Every mode must fail loudly and name the
// rebuild rather than proceeding.
func TestInstallFailsLoudlyWhenTheGuardBinaryIsMissing(t *testing.T) {
	home, repositoryRoot := installerFixture(t)
	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallApply}); err != nil {
		t.Fatal(err)
	}
	if err := os.Remove(filepath.Join(repositoryRoot, filepath.FromSlash(guardRepositoryBinary))); err != nil {
		t.Fatal(err)
	}
	for _, mode := range []InstallMode{InstallCheck, InstallDryRun, InstallApply} {
		_, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: mode})
		if err == nil {
			t.Fatalf("%s accepted a dangling guard link", mode)
		}
		if !strings.Contains(err.Error(), "go build -trimpath -o "+guardRepositoryBinary+" ./cmd/anvil-guard") {
			t.Fatalf("%s error does not name the rebuild: %v", mode, err)
		}
	}
	// Uninstall must still be able to remove the managed link.
	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallUninstall}); err != nil {
		t.Fatalf("uninstall could not clean up a dangling link: %v", err)
	}
	if _, err := os.Lstat(guardInstalledPath(home)); !os.IsNotExist(err) {
		t.Fatalf("uninstall left the dangling guard link: %v", err)
	}
}
