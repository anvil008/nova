package codingfleet

import (
	"bytes"
	"encoding/json"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
	"time"
)

func TestInstallAntigravityLifecycleMCPIsManagedAndScoped(t *testing.T) {
	home, repositoryRoot := installerFixture(t)
	configPath := antigravityMCPConfigPath(home)
	if err := os.MkdirAll(filepath.Dir(configPath), 0o700); err != nil {
		t.Fatal(err)
	}
	original := []byte(`{"unowned":{"preserve":true},"mcpServers":{"personal":{"command":"personal-server","args":[]}}}`)
	if err := os.WriteFile(configPath, original, 0o640); err != nil {
		t.Fatal(err)
	}
	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallApply}); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(configPath)
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Unowned map[string]bool                       `json:"unowned"`
		Servers map[string]antigravityMCPRegistration `json:"mcpServers"`
	}
	if err := json.Unmarshal(data, &document); err != nil {
		t.Fatal(err)
	}
	if !document.Unowned["preserve"] || document.Servers["personal"].Command != "personal-server" {
		t.Fatalf("unowned Antigravity config changed: %s", data)
	}
	if got := document.Servers[supervisorMCPServerName]; got.Command != supervisorRunplaneBinary || !reflect.DeepEqual(got.Args, []string{"mcp"}) || !reflect.DeepEqual(got.EnabledTools, []string{supervisorMCPToolName}) {
		t.Fatalf("managed registration=%+v", got)
	}
	info, err := os.Stat(configPath)
	if err != nil || info.Mode().Perm() != 0o640 {
		t.Fatalf("config mode=%v error=%v", info.Mode().Perm(), err)
	}

	orchestrator, err := os.ReadFile(filepath.Join(home, ".gemini", "config", "agents", codingOrchestratorAgentName, "agent.md"))
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Contains(orchestrator, []byte("  - "+supervisorMCPToolName+"\n")) {
		t.Fatal("Antigravity orchestrator lacks lifecycle MCP tool")
	}
	leaf, err := os.ReadFile(filepath.Join(home, ".gemini", "config", "agents", "anvil-cf-technical-go", "agent.md"))
	if err != nil {
		t.Fatal(err)
	}
	if bytes.Contains(leaf, []byte(supervisorMCPToolName)) {
		t.Fatal("leaf projection received lifecycle MCP tool")
	}
	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallUninstall}); err != nil {
		t.Fatal(err)
	}
	data, err = os.ReadFile(configPath)
	if err != nil {
		t.Fatal(err)
	}
	if bytes.Contains(data, []byte(supervisorMCPServerName)) || !bytes.Contains(data, []byte("personal-server")) {
		t.Fatalf("uninstall config=%s", data)
	}
}

func TestInstallRejectsConflictingLifecycleMCPRegistration(t *testing.T) {
	home, repositoryRoot := installerFixture(t)
	configPath := antigravityMCPConfigPath(home)
	if err := os.MkdirAll(filepath.Dir(configPath), 0o700); err != nil {
		t.Fatal(err)
	}
	conflict := []byte(`{"mcpServers":{"anvil-swarm-runplane":{"command":"malicious","args":[]}}}`)
	if err := os.WriteFile(configPath, conflict, 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallApply}); err == nil || !strings.Contains(err.Error(), "refuse conflicting") {
		t.Fatalf("conflicting registration error=%v", err)
	}
	if got, err := os.ReadFile(configPath); err != nil || !bytes.Equal(got, conflict) {
		t.Fatalf("conflicting config mutated: %q, %v", got, err)
	}
}

func TestInstallFirstRepeatCheckAndUnownedPreservation(t *testing.T) {
	home, repositoryRoot := installerFixture(t)
	unownedClaude := filepath.Join(home, ".claude", "agents", "personal.md")
	if err := os.MkdirAll(filepath.Dir(unownedClaude), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(unownedClaude, []byte("personal\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	configPath := filepath.Join(home, ".codex", "config.toml")
	if err := os.MkdirAll(filepath.Dir(configPath), 0o755); err != nil {
		t.Fatal(err)
	}
	unownedConfig := []byte("model = \"local-choice\"\n[mcp_servers.keep]\ncommand = \"keep\"\n")
	if err := os.WriteFile(configPath, unownedConfig, 0o640); err != nil {
		t.Fatal(err)
	}
	for _, pathname := range globalInstructionPaths(home) {
		if err := os.MkdirAll(filepath.Dir(pathname), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(pathname, []byte("unmanaged instructions stay\n"), 0o640); err != nil {
			t.Fatal(err)
		}
	}

	options := InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallApply}
	if _, err := Install(options); err != nil {
		t.Fatalf("Install(first) error = %v", err)
	}
	assertManagedLinks(t, home, repositoryRoot)
	firstConfig, err := os.ReadFile(configPath)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.HasPrefix(firstConfig, unownedConfig) {
		t.Fatalf("unowned config prefix changed:\n%s", firstConfig)
	}
	if bytes.Count(firstConfig, []byte(codexBeginMarker)) != 1 || bytes.Count(firstConfig, []byte(codexEndMarker)) != 1 {
		t.Fatalf("managed marker count is invalid:\n%s", firstConfig)
	}
	info, err := os.Stat(configPath)
	if err != nil {
		t.Fatal(err)
	}
	if info.Mode().Perm() != 0o640 {
		t.Fatalf("config mode = %v, want 0640", info.Mode().Perm())
	}

	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot}); err != nil {
		t.Fatalf("Install(repeat/default mode) error = %v", err)
	}
	secondConfig, err := os.ReadFile(configPath)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(firstConfig, secondConfig) {
		t.Fatal("repeated install changed Codex config bytes")
	}
	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallCheck}); err != nil {
		t.Fatalf("Install(check) error = %v", err)
	}
	if got, err := os.ReadFile(unownedClaude); err != nil || string(got) != "personal\n" {
		t.Fatalf("unowned Claude agent changed: %q, %v", got, err)
	}
	for _, pathname := range globalInstructionPaths(home) {
		got, err := os.ReadFile(pathname)
		if err != nil || !bytes.HasPrefix(got, []byte("unmanaged instructions stay\n")) || bytes.Count(got, []byte(routingBeginMarker)) != 1 || bytes.Count(got, []byte(routingEndMarker)) != 1 {
			t.Errorf("global instruction file %s = %q, %v; want preserved prefix plus one routing block", pathname, got, err)
		}
		for _, contract := range [][]byte{
			[]byte("enter through `anvil-coding-orchestrator`"),
			[]byte("use Terra Max for all subagents"),
			[]byte("use Gemini 3.7 Flash for execution and Opus for planning"),
			[]byte("Explicit user routes override fleet defaults"),
			[]byte("Fail closed on ambiguous, conflicting, or unavailable requests"),
			[]byte("Use native in-harness agents whenever the requested model belongs to the current provider"),
			[]byte("Use the shared supervisor launcher only when the requested provider differs"),
			[]byte("never use the shared launcher for same-provider work"),
			[]byte("anvil.agent-handoff/v1"),
			[]byte("two total verification passes"),
			[]byte("/home/anvil/.local/bin/swarm-runplane serve"),
			[]byte("http://127.0.0.1:8083"),
			[]byte("~/.local/state/swarm-runplane/auth.token"),
			[]byte("SWARM_RUNPLANE_STATE"),
			[]byte("SWARM_RUNPLANE_URL"),
			[]byte("SWARM_RUNPLANE_TOKEN"),
			[]byte("SWARM_RUNPLANE_TOKEN_FILE"),
			[]byte("exact canonical role and requested provider/family/model/effort capability"),
			[]byte("/home/anvil/.local/bin/swarm-runplane start --request route.json"),
			[]byte("events --after N JOB_ID"),
			[]byte("send JOB_ID` via stdin"),
			[]byte("resume JOB_ID` via stdin"),
			[]byte("cancel JOB_ID"),
			[]byte("evidence JOB_ID"),
			[]byte("never argv"),
			[]byte("parent keeps monitor, resume, message, cancel, evidence, integration, and completion authority"),
			[]byte("Coding Orchestrator Agent orchestrates only"),
			[]byte("The peer workflow layer is exactly Research Agent, Planner Agent, Executor Agent, Code Review Agent, Debugger Agent, Coding Evaluation Agent, and Factory Agent"),
			[]byte("Every workflow unit selects technical and domain specialists dynamically"),
			[]byte("When Research, Planner, Executor, Code Review, Debugger, or Coding Evaluation reports a missing-specialist gap"),
			[]byte("the orchestrator dispatches Factory and then resumes the original unit"),
			[]byte("Factory returns the new definition to the orchestrator; it never redispatches itself or invokes another workflow unit"),
			[]byte("may run up to 25 materially independent workflow units in parallel"),
			[]byte("20 for Executor and 10 for Research, Planner, Code Review, Debugger, Coding Evaluation, and Factory"),
			[]byte("do not override lower hard harness, provider, or runtime caps"),
			[]byte("Executor Agent is the ordinary target-project writer"),
			[]byte("Factory writes only the canonical Swarm technical/domain catalog, generated projections, and installer-owned global harness state"),
			[]byte("Only Coding Orchestrator Agent declares the overall goal complete"),
		} {
			if !bytes.Contains(got, contract) {
				t.Errorf("global instruction file %s is missing routing contract %q", pathname, contract)
			}
		}
		if info, statErr := os.Stat(pathname); statErr != nil || info.Mode().Perm() != 0o640 {
			t.Errorf("global instruction mode %s = %v, %v; want 0640", pathname, info, statErr)
		}
	}
}

func TestInstallCheckAcceptsRepositoryCompatibilityShim(t *testing.T) {
	home, previousRoot := installerFixture(t)
	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: previousRoot, Mode: InstallApply}); err != nil {
		t.Fatal(err)
	}

	currentRoot := previousRoot + "-coding"
	if err := os.Rename(previousRoot, currentRoot); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(previousRoot, 0o755); err != nil {
		t.Fatal(err)
	}
	compatibilityTarget, err := filepath.Rel(previousRoot, filepath.Join(currentRoot, "harness-agents"))
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(compatibilityTarget, filepath.Join(previousRoot, "harness-agents")); err != nil {
		t.Fatal(err)
	}

	result, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: currentRoot, Mode: InstallCheck})
	if err != nil {
		t.Fatalf("Install(check compatibility shim) error = %v", err)
	}
	if got, want := result.VerifiedDigests, len(mustLoad(t).Roles)*3; got != want {
		t.Fatalf("verified digests = %d, want %d", got, want)
	}

	result, err = Install(InstallOptions{HomeDir: home, RepositoryRoot: currentRoot, Mode: InstallDryRun})
	if err != nil {
		t.Fatalf("Install(dry-run direct repoint) error = %v", err)
	}
	wantsRepoint := false
	for _, action := range result.Actions {
		if strings.HasPrefix(action, "link ") {
			wantsRepoint = true
			break
		}
	}
	if !wantsRepoint {
		t.Fatal("dry-run treated compatibility links as permanent direct targets")
	}
}

func TestInstallRollsBackEveryGenerationBoundary(t *testing.T) {
	tests := []struct {
		name string
		hook func(home string) func(string) error
	}{
		{
			name: "mid role links",
			hook: func(string) func(string) error {
				mutations := 0
				return func(string) error {
					mutations++
					if mutations == 37 {
						return errors.New("injected mid-link failure")
					}
					return nil
				}
			},
		},
		{
			name: "after Codex config",
			hook: func(home string) func(string) error {
				wanted := filepath.Join(home, ".codex", "config.toml")
				return func(pathname string) error {
					if pathname == wanted {
						return errors.New("injected Codex config failure")
					}
					return nil
				}
			},
		},
		{
			name: "mid global instructions",
			hook: func(home string) func(string) error {
				wanted := globalInstructionPaths(home)[1]
				return func(pathname string) error {
					if pathname == wanted {
						return errors.New("injected global instruction failure")
					}
					return nil
				}
			},
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			home, previousRoot := installerFixture(t)
			if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: previousRoot, Mode: InstallApply}); err != nil {
				t.Fatal(err)
			}
			before := snapshotInstalledHarnessState(t, home)

			nextRoot := renderInstallerRepository(t)
			originalRoutingBlock := globalCodingRoutingBlock
			globalCodingRoutingBlock = bytes.Replace(
				originalRoutingBlock,
				[]byte("## Coding task routing"),
				[]byte("## Coding task routing generation two"),
				1,
			)
			_, err := Install(InstallOptions{
				HomeDir:        home,
				RepositoryRoot: nextRoot,
				Mode:           InstallApply,
				afterMutation:  test.hook(home),
			})
			globalCodingRoutingBlock = originalRoutingBlock
			if err == nil || !strings.Contains(err.Error(), "rolled back") || !strings.Contains(err.Error(), "injected") {
				t.Fatalf("Install(injected failure) error = %v, want injected rollback", err)
			}

			after := snapshotInstalledHarnessState(t, home)
			if !reflect.DeepEqual(after, before) {
				t.Fatalf("installer state differs after rollback\nbefore: %#v\nafter:  %#v", before, after)
			}
			result, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: previousRoot, Mode: InstallCheck})
			if err != nil {
				t.Fatalf("previous generation is not current after rollback: %v", err)
			}
			if got, want := result.VerifiedDigests, len(mustLoad(t).Roles)*3; got != want {
				t.Fatalf("verified digests = %d, want %d", got, want)
			}
		})
	}
}

func TestInstallVerifiesEveryProjectionDigest(t *testing.T) {
	home, repositoryRoot := installerFixture(t)
	result, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallApply})
	if err != nil {
		t.Fatal(err)
	}
	want := len(mustLoad(t).Roles) * 3
	if result.VerifiedDigests != want {
		t.Fatalf("verified digests = %d, want %d", result.VerifiedDigests, want)
	}

	rendered, err := Render(repositoryRoot, mustLoad(t))
	if err != nil {
		t.Fatal(err)
	}
	rendered.Files[0].Content = append(rendered.Files[0].Content, []byte("tampered expected digest")...)
	if _, err := verifyInstalledDigests(home, rendered); err == nil || !strings.Contains(err.Error(), "digest mismatch") {
		t.Fatalf("verifyInstalledDigests() error = %v, want digest mismatch", err)
	}
}

func TestInstallRollsBackDigestVerificationFailure(t *testing.T) {
	home, previousRoot := installerFixture(t)
	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: previousRoot, Mode: InstallApply}); err != nil {
		t.Fatal(err)
	}
	before := snapshotInstalledHarnessState(t, home)
	nextRoot := renderInstallerRepository(t)

	originalRoutingBlock := globalCodingRoutingBlock
	globalCodingRoutingBlock = bytes.Replace(
		originalRoutingBlock,
		[]byte("## Coding task routing"),
		[]byte("## Coding task routing generation two"),
		1,
	)
	lastGlobalPath := globalInstructionPaths(home)[len(globalInstructionPaths(home))-1]
	tamperedProfile := filepath.Join(home, ".codex", "anvil-wf-research.config.toml")
	_, err := Install(InstallOptions{
		HomeDir:        home,
		RepositoryRoot: nextRoot,
		Mode:           InstallApply,
		afterMutation: func(pathname string) error {
			if pathname != lastGlobalPath {
				return nil
			}
			if err := os.Remove(tamperedProfile); err != nil {
				return err
			}
			return os.Symlink(filepath.Join(home, ".agents", "AGENTS.md"), tamperedProfile)
		},
	})
	globalCodingRoutingBlock = originalRoutingBlock
	if err == nil || !strings.Contains(err.Error(), "rolled back") || !strings.Contains(err.Error(), "digest mismatch") {
		t.Fatalf("Install(digest mismatch) error = %v, want digest rollback", err)
	}

	after := snapshotInstalledHarnessState(t, home)
	if !reflect.DeepEqual(after, before) {
		t.Fatalf("installer state differs after digest rollback\nbefore: %#v\nafter:  %#v", before, after)
	}
	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: previousRoot, Mode: InstallCheck}); err != nil {
		t.Fatalf("previous generation is not current after digest rollback: %v", err)
	}
}

func TestInstallDryRunDoesNotMutate(t *testing.T) {
	home, repositoryRoot := installerFixture(t)
	result, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallDryRun})
	if err != nil {
		t.Fatalf("Install(dry-run) error = %v", err)
	}
	if len(result.Actions) == 0 {
		t.Fatal("dry-run returned no planned actions")
	}
	for _, path := range []string{filepath.Join(home, ".agents"), filepath.Join(home, ".claude"), filepath.Join(home, ".gemini"), filepath.Join(home, ".codex")} {
		if _, err := os.Lstat(path); !os.IsNotExist(err) {
			t.Fatalf("dry-run mutated %s, stat error = %v", path, err)
		}
	}
}

func TestInstallRejectsConcurrentInstaller(t *testing.T) {
	home, repositoryRoot := installerFixture(t)
	lockHeld := make(chan struct{})
	releaseFirst := make(chan struct{})
	firstDone := make(chan error, 1)
	go func() {
		blocked := false
		_, err := Install(InstallOptions{
			HomeDir:        home,
			RepositoryRoot: repositoryRoot,
			Mode:           InstallApply,
			afterMutation: func(string) error {
				if blocked {
					return nil
				}
				blocked = true
				close(lockHeld)
				<-releaseFirst
				return nil
			},
		})
		firstDone <- err
	}()

	select {
	case <-lockHeld:
	case <-time.After(5 * time.Second):
		close(releaseFirst)
		t.Fatal("first installer did not reach a locked mutation")
	}
	_, contentionErr := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallCheck})
	close(releaseFirst)
	if contentionErr == nil || !strings.Contains(contentionErr.Error(), "already running") || !strings.Contains(contentionErr.Error(), home) {
		t.Fatalf("second Install() error = %v, want clear harness-home contention", contentionErr)
	}

	select {
	case err := <-firstDone:
		if err != nil {
			t.Fatalf("first installer failed after contention: %v", err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("first installer did not complete after releasing contention test")
	}
	result, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallCheck})
	if err != nil {
		t.Fatalf("installed generation is invalid after contention: %v", err)
	}
	if got, want := result.VerifiedDigests, len(mustLoad(t).Roles)*3; got != want {
		t.Fatalf("verified digests = %d, want %d", got, want)
	}
}

func TestInstallCleansOnlyStaleOwnedSymlinks(t *testing.T) {
	home, repositoryRoot := installerFixture(t)
	agentsRoot := filepath.Join(home, ".gemini", "config", "agents")
	if err := os.MkdirAll(agentsRoot, 0o755); err != nil {
		t.Fatal(err)
	}
	stale := filepath.Join(agentsRoot, "anvil-cf-stale")
	unowned := filepath.Join(agentsRoot, "personal-agent")
	if err := os.Symlink(filepath.Join(repositoryRoot, "stale"), stale); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(filepath.Join(repositoryRoot, "personal"), unowned); err != nil {
		t.Fatal(err)
	}
	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallApply}); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Lstat(stale); !os.IsNotExist(err) {
		t.Fatalf("stale owned link remains, stat error = %v", err)
	}
	if _, err := os.Lstat(unowned); err != nil {
		t.Fatalf("unowned link was removed: %v", err)
	}
}

func TestInstallCleansOnlyStaleOwnedClaudeAgents(t *testing.T) {
	home, repositoryRoot := installerFixture(t)
	agentsRoot := filepath.Join(home, ".claude", "agents")
	if err := os.MkdirAll(agentsRoot, 0o755); err != nil {
		t.Fatal(err)
	}
	stale := filepath.Join(agentsRoot, "anvil-cf-stale.md")
	unowned := filepath.Join(agentsRoot, "personal.md")
	if err := os.Symlink(filepath.Join(repositoryRoot, "stale"), stale); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(filepath.Join(repositoryRoot, "personal"), unowned); err != nil {
		t.Fatal(err)
	}
	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallApply}); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Lstat(stale); !os.IsNotExist(err) {
		t.Fatalf("stale owned Claude agent remains, stat error = %v", err)
	}
	if _, err := os.Lstat(unowned); err != nil {
		t.Fatalf("unowned Claude agent was removed: %v", err)
	}
}

func TestInstallRejectsConflictingNonSymlinkTargets(t *testing.T) {
	tests := []struct {
		name string
		path func(home string) string
	}{
		{name: "Claude collection", path: func(home string) string {
			return filepath.Join(home, ".claude", "agents", "anvil-coding-fleet")
		}},
		{name: "Claude direct role", path: func(home string) string {
			return filepath.Join(home, ".claude", "agents", "anvil-wf-executor.md")
		}},
		{name: "Codex direct role", path: func(home string) string {
			return filepath.Join(home, ".codex", "anvil-wf-executor.config.toml")
		}},
		{name: "Antigravity role", path: func(home string) string {
			return filepath.Join(home, ".gemini", "config", "agents", "anvil-cf-domain-finance-plaid")
		}},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			home, repositoryRoot := installerFixture(t)
			conflict := test.path(home)
			if err := os.MkdirAll(conflict, 0o755); err != nil {
				t.Fatal(err)
			}
			_, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallApply})
			if err == nil || !strings.Contains(err.Error(), "non-symlink") {
				t.Fatalf("Install() error = %v, want non-symlink refusal", err)
			}
		})
	}
}

func TestInstallRejectsSymlinkedGeneratedSourceBeforeHomeMutation(t *testing.T) {
	home, repositoryRoot := installerFixture(t)
	providerRoot := filepath.Join(repositoryRoot, "harness-agents", "rendered", "claude")
	if err := os.RemoveAll(providerRoot); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(t.TempDir(), providerRoot); err != nil {
		t.Fatal(err)
	}
	_, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallApply})
	if err == nil || !strings.Contains(err.Error(), "symlink") {
		t.Fatalf("Install() error = %v, want symlink refusal", err)
	}
	for _, pathname := range []string{filepath.Join(home, ".claude"), filepath.Join(home, ".gemini"), filepath.Join(home, ".codex")} {
		if _, statErr := os.Lstat(pathname); !os.IsNotExist(statErr) {
			t.Fatalf("failed install mutated %s, stat error = %v", pathname, statErr)
		}
	}
}

func TestInstallRejectsMalformedCodexMarkers(t *testing.T) {
	tests := []struct {
		name    string
		content string
	}{
		{name: "begin only", content: codexBeginMarker + "\n"},
		{name: "end only", content: codexEndMarker + "\n"},
		{name: "duplicate", content: codexBeginMarker + "\n" + codexBeginMarker + "\n" + codexEndMarker + "\n"},
		{name: "reversed", content: codexEndMarker + "\n" + codexBeginMarker + "\n"},
		{name: "inline begin", content: "prefix " + codexBeginMarker + "\n" + codexEndMarker + "\n"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			home, repositoryRoot := installerFixture(t)
			configPath := filepath.Join(home, ".codex", "config.toml")
			if err := os.MkdirAll(filepath.Dir(configPath), 0o755); err != nil {
				t.Fatal(err)
			}
			if err := os.WriteFile(configPath, []byte(test.content), 0o600); err != nil {
				t.Fatal(err)
			}
			_, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallApply})
			if err == nil || !strings.Contains(err.Error(), "marker") {
				t.Fatalf("Install() error = %v, want marker refusal", err)
			}
		})
	}
}

func TestInstallRejectsMalformedGlobalRoutingMarkers(t *testing.T) {
	home, repositoryRoot := installerFixture(t)
	pathname := filepath.Join(home, ".agents", "AGENTS.md")
	if err := os.MkdirAll(filepath.Dir(pathname), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(pathname, []byte(routingBeginMarker+"\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	_, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallApply})
	if err == nil || !strings.Contains(err.Error(), "global instruction markers") {
		t.Fatalf("Install() error = %v, want global instruction marker refusal", err)
	}
	for _, managed := range []string{filepath.Join(home, ".claude", "agents", "anvil-coding-fleet"), filepath.Join(home, ".codex", "config.toml")} {
		if _, statErr := os.Lstat(managed); !os.IsNotExist(statErr) {
			t.Fatalf("failed preflight mutated %s, stat error = %v", managed, statErr)
		}
	}
}

func TestManagedBlockPreservesExactPrefixAndSuffix(t *testing.T) {
	prefix := []byte("model = \"keep\"\n# prefix stays byte exact\n")
	suffix := []byte("[mcp_servers.keep]\ncommand = \"keep\"\n")
	oldBlock := []byte(codexBeginMarker + "\nold = true\n" + codexEndMarker + "\n")
	newBlock := []byte(codexBeginMarker + "\nnew = true\n" + codexEndMarker + "\n")
	current := append(append(append([]byte(nil), prefix...), oldBlock...), suffix...)

	updated, found, err := updateManagedBlock(current, newBlock, false)
	if err != nil || !found {
		t.Fatalf("updateManagedBlock(replace) = found %t, error %v", found, err)
	}
	want := append(append(append([]byte(nil), prefix...), newBlock...), suffix...)
	if !bytes.Equal(updated, want) {
		t.Fatalf("replace did not byte-preserve prefix/suffix:\n%s", updated)
	}

	uninstalled, found, err := updateManagedBlock(updated, newBlock, true)
	if err != nil || !found {
		t.Fatalf("updateManagedBlock(uninstall) = found %t, error %v", found, err)
	}
	wantUninstalled := append(append([]byte(nil), prefix...), suffix...)
	if !bytes.Equal(uninstalled, wantUninstalled) {
		t.Fatalf("uninstall did not byte-preserve prefix/suffix:\n%s", uninstalled)
	}
}

func TestInstallUninstallRemovesOnlyOwnedState(t *testing.T) {
	home, repositoryRoot := installerFixture(t)
	configPath := filepath.Join(home, ".codex", "config.toml")
	if err := os.MkdirAll(filepath.Dir(configPath), 0o755); err != nil {
		t.Fatal(err)
	}
	unowned := []byte("model = \"keep\"\n")
	if err := os.WriteFile(configPath, unowned, 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallApply}); err != nil {
		t.Fatal(err)
	}
	for _, pathname := range globalInstructionPaths(home) {
		current, err := os.ReadFile(pathname)
		if err != nil {
			t.Fatal(err)
		}
		if !bytes.Contains(current, []byte(routingBeginMarker)) {
			t.Fatalf("global routing block missing from %s", pathname)
		}
	}
	unownedAgent := filepath.Join(home, ".gemini", "config", "agents", "personal")
	if err := os.Symlink(filepath.Join(repositoryRoot, "personal"), unownedAgent); err != nil {
		t.Fatal(err)
	}
	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallUninstall}); err != nil {
		t.Fatalf("Install(uninstall) error = %v", err)
	}
	if _, err := os.Lstat(filepath.Join(home, ".claude", "agents", "anvil-coding-fleet")); !os.IsNotExist(err) {
		t.Fatalf("Claude managed link remains, stat error = %v", err)
	}
	if _, err := os.Lstat(unownedAgent); err != nil {
		t.Fatalf("unowned Antigravity agent removed: %v", err)
	}
	config, err := os.ReadFile(configPath)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(config, unowned) {
		t.Fatalf("uninstall changed unowned config bytes: %q", config)
	}
	for _, pathname := range globalInstructionPaths(home) {
		current, err := os.ReadFile(pathname)
		if err != nil {
			t.Fatal(err)
		}
		if bytes.Contains(current, []byte(routingBeginMarker)) || bytes.Contains(current, []byte(routingEndMarker)) {
			t.Errorf("uninstall left global routing block in %s: %q", pathname, current)
		}
	}
}

func installerFixture(t *testing.T) (string, string) {
	t.Helper()
	fixtureRoot := t.TempDir()
	home := filepath.Join(fixtureRoot, "home")
	repositoryRoot := filepath.Join(fixtureRoot, "repo")
	if err := os.MkdirAll(home, 0o755); err != nil {
		t.Fatal(err)
	}
	document := mustLoad(t)
	rendered, err := Render(repositoryRoot, document)
	if err != nil {
		t.Fatal(err)
	}
	if err := SyncRendered(repositoryRoot, rendered, false); err != nil {
		t.Fatal(err)
	}
	return home, repositoryRoot
}

func renderInstallerRepository(t *testing.T) string {
	t.Helper()
	repositoryRoot := filepath.Join(t.TempDir(), "repo")
	rendered, err := Render(repositoryRoot, mustLoad(t))
	if err != nil {
		t.Fatal(err)
	}
	if err := SyncRendered(repositoryRoot, rendered, false); err != nil {
		t.Fatal(err)
	}
	return repositoryRoot
}

type installedHarnessPathState struct {
	Mode       fs.FileMode
	LinkTarget string
	Content    string
}

func snapshotInstalledHarnessState(t *testing.T, home string) map[string]installedHarnessPathState {
	t.Helper()
	state := make(map[string]installedHarnessPathState)
	for _, root := range []string{
		filepath.Join(home, ".agents"),
		filepath.Join(home, ".claude"),
		filepath.Join(home, ".codex"),
		filepath.Join(home, ".gemini"),
	} {
		err := filepath.WalkDir(root, func(pathname string, entry fs.DirEntry, walkErr error) error {
			if walkErr != nil {
				return walkErr
			}
			if entry.IsDir() {
				return nil
			}
			relative, err := filepath.Rel(home, pathname)
			if err != nil {
				return err
			}
			info, err := os.Lstat(pathname)
			if err != nil {
				return err
			}
			pathState := installedHarnessPathState{Mode: info.Mode()}
			if info.Mode()&os.ModeSymlink != 0 {
				pathState.LinkTarget, err = os.Readlink(pathname)
			} else {
				var content []byte
				content, err = os.ReadFile(pathname)
				pathState.Content = string(content)
			}
			if err != nil {
				return err
			}
			state[relative] = pathState
			return nil
		})
		if err != nil && !errors.Is(err, fs.ErrNotExist) {
			t.Fatalf("snapshot installed harness state: %v", err)
		}
	}
	return state
}

func assertManagedLinks(t *testing.T, home, repositoryRoot string) {
	t.Helper()
	checks := map[string]string{
		filepath.Join(home, ".claude", "agents", "anvil-coding-fleet"): filepath.Join(repositoryRoot, "harness-agents", "rendered", "claude"),
	}
	document := mustLoad(t)
	for _, role := range document.Roles {
		name := nativeAgentName(role)
		checks[filepath.Join(home, ".claude", "agents", name+".md")] = filepath.Join(repositoryRoot, "harness-agents", "rendered", "claude", name+".md")
		checks[filepath.Join(home, ".codex", name+".config.toml")] = filepath.Join(repositoryRoot, "harness-agents", "rendered", "codex", name+".toml")
		checks[filepath.Join(home, ".gemini", "config", "agents", name)] = filepath.Join(repositoryRoot, "harness-agents", "rendered", "antigravity", name)
	}
	for pathname, want := range checks {
		got, err := os.Readlink(pathname)
		if err != nil || got != want {
			t.Errorf("Readlink(%s) = %q, %v; want %q", pathname, got, err, want)
		}
	}
}

func TestInstallCleansOnlyStaleOwnedCodexProfiles(t *testing.T) {
	home, repositoryRoot := installerFixture(t)
	codexRoot := filepath.Join(home, ".codex")
	if err := os.MkdirAll(codexRoot, 0o755); err != nil {
		t.Fatal(err)
	}
	staleCurrentRole := filepath.Join(codexRoot, "anvil-wf-executor.config.toml")
	staleUnknownWorkflow := filepath.Join(codexRoot, "anvil-wf-stale.config.toml")
	unowned := filepath.Join(codexRoot, "personal.config.toml")
	for _, stale := range []string{staleCurrentRole, staleUnknownWorkflow} {
		if err := os.Symlink(filepath.Join(repositoryRoot, "stale"), stale); err != nil {
			t.Fatal(err)
		}
	}
	if err := os.Symlink(filepath.Join(repositoryRoot, "personal"), unowned); err != nil {
		t.Fatal(err)
	}
	if _, err := Install(InstallOptions{HomeDir: home, RepositoryRoot: repositoryRoot, Mode: InstallApply}); err != nil {
		t.Fatal(err)
	}
	if got, err := os.Readlink(staleCurrentRole); err != nil || got != filepath.Join(repositoryRoot, "harness-agents", "rendered", "codex", "anvil-wf-executor.toml") {
		t.Errorf("current Codex role link = %q, %v", got, err)
	}
	if _, err := os.Lstat(staleUnknownWorkflow); !os.IsNotExist(err) {
		t.Errorf("stale unknown Codex profile remains, stat error = %v", err)
	}
	if _, err := os.Lstat(unowned); err != nil {
		t.Fatalf("unowned Codex profile was removed: %v", err)
	}
}
