package codingfleet

import (
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"syscall"
)

const (
	codexBeginMarker   = "# BEGIN ANVIL CODING FLEET (managed; do not edit)"
	codexEndMarker     = "# END ANVIL CODING FLEET"
	routingBeginMarker = "<!-- BEGIN ANVIL CODING FLEET ROUTING (managed; do not edit) -->"
	routingEndMarker   = "<!-- END ANVIL CODING FLEET ROUTING -->"
)

var globalCodingRoutingBlock = []byte(routingBeginMarker + "\n" +
	"## Coding task routing\n\n" +
	"- For every top-level coding task—including implementation, code changes, debugging, code review, and code-focused testing—enter through `anvil-coding-orchestrator`, the one durable goal owner, integration owner, and overall completion authority.\n" +
	"- If already executing as `anvil-coding-orchestrator` or one of its selected workflow units or specialists, do not invoke Coding Orchestrator Agent recursively.\n" +
	"- Coding Orchestrator Agent parses explicit natural-language model routes before scheduling, including whole-goal requests such as `use Terra Max for all subagents` and lane-specific requests such as `use Gemini 3.7 Flash for execution and Opus for planning`. Explicit user routes override fleet defaults and remain attached to matching dispatches across checkpoints.\n" +
	"- Resolve provider, family, model, and effort aliases only against currently discovered and allowlisted capabilities. Fail closed on ambiguous, conflicting, or unavailable requests and report the unresolved route; never silently substitute another model, family, provider, or effort.\n" +
	"- Use native in-harness agents whenever the requested model belongs to the current provider: Agy/Antigravity uses native Gemini agents, Claude uses native Anthropic agents, and Codex uses native OpenAI agents. Use the shared supervisor launcher only when the requested provider differs from the current harness provider. Pass exact model and effort overrides, never silently substitute, and never use the shared launcher for same-provider work. Foreign runs load the exact canonical workflow or specialist definition plus a bounded brief; the parent keeps monitor, resume, message, cancel, evidence, integration, and completion authority.\n" +
	"- The parent starts or uses the authenticated loopback service with `/home/anvil/.local/bin/swarm-runplane serve` (default URL `http://127.0.0.1:8083`, state `~/.local/state/swarm-runplane`, token file `~/.local/state/swarm-runplane/auth.token`; overrides `SWARM_RUNPLANE_STATE`, `SWARM_RUNPLANE_URL`, `SWARM_RUNPLANE_TOKEN`, and `SWARM_RUNPLANE_TOKEN_FILE`). Run `health` and then `capabilities`; fail closed unless the exact canonical role and requested provider/family/model/effort capability are present.\n" +
	"- Use `/home/anvil/.local/bin/swarm-runplane start --request route.json`; put the bounded foreign role/task brief in the request file and use stdin for `send JOB_ID` and `resume JOB_ID`, never argv. Supported lifecycle commands are `health`, `capabilities`, `start --request route.json`, `list`, `status JOB_ID`, `events --after N JOB_ID`, `send JOB_ID` via stdin, `resume JOB_ID` via stdin, `cancel JOB_ID`, and `evidence JOB_ID`.\n" +
	"- Every native or foreign child returns the small `anvil.agent-handoff/v1` boundary: runId, parentRunId, canonicalRole, provider, model, effort, mode, ownedFiles, limits, changedFiles, tests, result, and disposition. Keep harness-native session/process state inside its owning harness.\n" +
	"- For implementation outcomes, use one independent verification pass plus at most one focused repair and one re-verification (two total verification passes). Stop on acceptance, cancellation, blockage, exhaustion, or no material change.\n" +
	"- Coding Orchestrator Agent orchestrates only: it binds and checkpoints the goal, maintains a dependency-ready queue, dispatches workflow units, reconciles their evidence with current state, and alone declares the terminal outcome. It does not directly research, inspect, edit, test, or implement target-project code.\n" +
	"- The peer workflow layer is exactly Research Agent, Planner Agent, Executor Agent, Code Review Agent, Debugger Agent, Coding Evaluation Agent, and Factory Agent. Dispatch only the minimum units justified by the task; they are capabilities, not a mandatory serial pipeline, and no unit owns another unit.\n" +
	"- Every workflow unit selects technical and domain specialists dynamically from the shared pools at the point evidence requires them. Workflow units do not call one another; each returns evidence and control to the orchestrator. When Research, Planner, Executor, Code Review, Debugger, or Coding Evaluation reports a missing-specialist gap, the orchestrator dispatches Factory and then resumes the original unit. Factory returns the new definition to the orchestrator; it never redispatches itself or invokes another workflow unit.\n" +
	"- Coding Orchestrator Agent may run up to 25 materially independent workflow units in parallel. Each unit may parallelize independent specialist work up to its own declared logical limit: 20 for Executor and 10 for Research, Planner, Code Review, Debugger, Coding Evaluation, and Factory. These fleet ceilings do not override lower hard harness, provider, or runtime caps; keep excess work queued and report the residual constraint. Preserve explicit ownership, prefer read-heavy or disjoint-file parallelism, and serialize overlapping mutations unless a harness-native worktree isolates them.\n" +
	"- Executor Agent is the ordinary target-project writer. Research, Planner, Code Review, Debugger, and Coding Evaluation remain read-only. Factory writes only the canonical Swarm technical/domain catalog, generated projections, and installer-owned global harness state; it never edits target-project code.\n" +
	"- Only Coding Orchestrator Agent declares the overall goal complete after integrated verification. Workflow units and specialists return concise evidence and control to it.\n" +
	"- If the harness cannot invoke the named agent in-process, load and follow its globally installed generated definition instead of silently bypassing the route.\n" +
	routingEndMarker + "\n")

// InstallMode selects a bounded installer operation.
type InstallMode string

const (
	InstallApply     InstallMode = "install"
	InstallDryRun    InstallMode = "dry-run"
	InstallCheck     InstallMode = "check"
	InstallUninstall InstallMode = "uninstall"
)

// InstallOptions identifies explicit roots and the requested bounded action.
type InstallOptions struct {
	HomeDir        string
	RepositoryRoot string
	Mode           InstallMode
	// Document supplies a validated candidate catalog for an atomic Factory
	// transaction. Ordinary callers leave it nil and use the embedded catalog.
	Document *Document
	// afterMutation is a test-only failure injection seam. Production callers
	// leave it nil; it runs after each installer-owned filesystem mutation.
	afterMutation func(string) error
}

// InstallResult lists deterministic actions or checks performed.
type InstallResult struct {
	Actions         []string
	VerifiedDigests int
}

type installLock struct {
	homeDirectory *os.File
}

// acquireInstallLock uses the target harness home directory as a stable,
// write-free lock inode. Separate codingfleet processes open independent file
// descriptions and contend on the same advisory flock without making dry-run
// or check modes create lock files.
func acquireInstallLock(home string) (*installLock, error) {
	directory, err := os.Open(home)
	if err != nil {
		return nil, fmt.Errorf("open harness home for installer lock: %w", err)
	}
	if err := syscall.Flock(int(directory.Fd()), syscall.LOCK_EX|syscall.LOCK_NB); err != nil {
		_ = directory.Close()
		if errors.Is(err, syscall.EWOULDBLOCK) || errors.Is(err, syscall.EAGAIN) {
			return nil, fmt.Errorf("coding fleet install is already running for harness home %s", home)
		}
		return nil, fmt.Errorf("acquire coding fleet installer lock for harness home %s: %w", home, err)
	}
	return &installLock{homeDirectory: directory}, nil
}

func (lock *installLock) release() error {
	if lock == nil || lock.homeDirectory == nil {
		return nil
	}
	unlockErr := syscall.Flock(int(lock.homeDirectory.Fd()), syscall.LOCK_UN)
	closeErr := lock.homeDirectory.Close()
	return errors.Join(unlockErr, closeErr)
}

// Install manages the Claude anvil-coding-fleet collection plus direct role
// links, direct Antigravity role links, direct Codex role profiles, one marked
// block in Codex config.toml, and one marked routing block in each supported
// harness's global instruction file. Every canonical role is therefore
// selectable as an exact headless definition in each harness.
func Install(options InstallOptions) (InstallResult, error) {
	if options.Mode == "" {
		options.Mode = InstallApply
	}
	home, repositoryRoot, err := validateInstallOptions(options)
	if err != nil {
		return InstallResult{}, err
	}
	lock, err := acquireInstallLock(home)
	if err != nil {
		return InstallResult{}, err
	}
	defer func() {
		_ = lock.release()
	}()
	document, err := installDocument(options.Document)
	if err != nil {
		return InstallResult{}, err
	}
	rendered, err := Render(repositoryRoot, document)
	if err != nil {
		return InstallResult{}, err
	}
	if options.Mode != InstallUninstall {
		if err := SyncRendered(repositoryRoot, rendered, true); err != nil {
			return InstallResult{}, fmt.Errorf("generated projections must be current before installation: %w", err)
		}
	}

	operations := make([]linkOperation, 0, len(document.Roles)*3+1)
	operations = append(operations, linkOperation{
		path:   filepath.Join(home, ".claude", "agents", "anvil-coding-fleet"),
		target: filepath.Join(repositoryRoot, "harness-agents", "rendered", "claude"),
	})
	for _, role := range document.Roles {
		name := nativeAgentName(role)
		operations = append(operations, linkOperation{
			path:   filepath.Join(home, ".claude", "agents", name+".md"),
			target: filepath.Join(repositoryRoot, "harness-agents", "rendered", "claude", name+".md"),
			file:   true,
		}, linkOperation{
			path:   filepath.Join(home, ".gemini", "config", "agents", name),
			target: filepath.Join(repositoryRoot, "harness-agents", "rendered", "antigravity", name),
		}, linkOperation{
			path:   filepath.Join(home, ".codex", name+".config.toml"),
			target: filepath.Join(repositoryRoot, "harness-agents", "rendered", "codex", name+".toml"),
			file:   true,
		})
	}
	if err := preflightInstall(repositoryRoot, home, operations, rendered.CodexConfigBlock, options.Mode); err != nil {
		return InstallResult{}, err
	}

	result := InstallResult{}
	transaction, err := beginInstallTransaction(home, operations, options)
	if err != nil {
		return result, err
	}
	fail := func(installErr error) (InstallResult, error) {
		if transaction == nil {
			return result, installErr
		}
		if rollbackErr := transaction.rollback(); rollbackErr != nil {
			return result, fmt.Errorf("install failed: %w; rollback failed: %v", installErr, rollbackErr)
		}
		return result, fmt.Errorf("install failed and was rolled back: %w", installErr)
	}
	if options.Mode == InstallUninstall {
		if err := uninstallLinks(home, operations, options.Mode, &result, transaction); err != nil {
			return fail(err)
		}
	} else {
		if err := reconcileLinks(repositoryRoot, home, operations, options.Mode, &result, transaction); err != nil {
			return fail(err)
		}
	}
	if err := reconcileCodexConfig(home, rendered.CodexConfigBlock, options.Mode, &result, transaction); err != nil {
		return fail(err)
	}
	if err := reconcileGlobalInstructions(home, options.Mode, &result, transaction); err != nil {
		return fail(err)
	}
	if err := reconcileAntigravityMCP(home, options.Mode, &result, transaction); err != nil {
		return fail(err)
	}
	if options.Mode == InstallApply || options.Mode == InstallCheck {
		verified, err := verifyInstalledDigests(home, rendered)
		if err != nil {
			return fail(err)
		}
		result.VerifiedDigests = verified
	}
	sort.Strings(result.Actions)
	return result, nil
}

func installDocument(candidate *Document) (Document, error) {
	if candidate == nil {
		return Load()
	}
	document := *candidate
	document.AuthorityProfiles = append([]AuthorityProfile(nil), candidate.AuthorityProfiles...)
	document.Roles = append([]Role(nil), candidate.Roles...)
	if err := validateDocument(document); err != nil {
		return Document{}, fmt.Errorf("validate candidate install catalog: %w", err)
	}
	if err := validateFleetTopology(document.Roles); err != nil {
		return Document{}, fmt.Errorf("validate candidate install topology: %w", err)
	}
	normalizeDocument(&document)
	return document, nil
}

func preflightInstall(repositoryRoot, home string, operations []linkOperation, block []byte, mode InstallMode) error {
	if mode != InstallUninstall {
		for _, operation := range operations {
			if err := requireManagedSource(repositoryRoot, operation); err != nil {
				return fmt.Errorf("link source %s: %w", operation.target, err)
			}
			if _, err := linkMatches(operation.path, operation.target); err != nil {
				return err
			}
		}
	}
	managedPaths, err := managedLinkPaths(home, operations)
	if err != nil {
		return err
	}
	for _, pathname := range managedPaths {
		info, err := os.Lstat(pathname)
		if errors.Is(err, fs.ErrNotExist) {
			continue
		}
		if err != nil {
			return fmt.Errorf("inspect managed target %s: %w", pathname, err)
		}
		if info.Mode()&os.ModeSymlink == 0 {
			return fmt.Errorf("refuse to replace or remove non-symlink managed target %s", pathname)
		}
	}
	configPath := filepath.Join(home, ".codex", "config.toml")
	current, err := os.ReadFile(configPath)
	if err != nil && !errors.Is(err, fs.ErrNotExist) {
		return fmt.Errorf("read Codex config: %w", err)
	}
	if _, _, err := updateManagedBlock(current, block, mode == InstallUninstall); err != nil {
		return fmt.Errorf("Codex config markers: %w", err)
	}
	for _, pathname := range globalInstructionPaths(home) {
		if err := rejectSymlinkComponents(home, filepath.Dir(pathname)); err != nil {
			return fmt.Errorf("validate global instruction path %s: %w", pathname, err)
		}
		info, statErr := os.Lstat(pathname)
		if statErr == nil && info.Mode()&os.ModeSymlink != 0 {
			return fmt.Errorf("refuse symlinked global instruction file %s", pathname)
		}
		if statErr != nil && !errors.Is(statErr, fs.ErrNotExist) {
			return fmt.Errorf("inspect global instruction file %s: %w", pathname, statErr)
		}
		instruction, readErr := os.ReadFile(pathname)
		if readErr != nil && !errors.Is(readErr, fs.ErrNotExist) {
			return fmt.Errorf("read global instruction file %s: %w", pathname, readErr)
		}
		if _, _, markerErr := updateDelimitedBlock(instruction, globalCodingRoutingBlock, mode == InstallUninstall, routingBeginMarker, routingEndMarker); markerErr != nil {
			return fmt.Errorf("global instruction markers in %s: %w", pathname, markerErr)
		}
	}
	mcpPath := antigravityMCPConfigPath(home)
	if err := rejectSymlinkComponents(home, filepath.Dir(mcpPath)); err != nil {
		return fmt.Errorf("validate Antigravity MCP config path: %w", err)
	}
	if info, statErr := os.Lstat(mcpPath); statErr == nil {
		if info.Mode()&os.ModeSymlink != 0 || !info.Mode().IsRegular() {
			return fmt.Errorf("refuse non-regular Antigravity MCP config %s", mcpPath)
		}
	} else if !errors.Is(statErr, fs.ErrNotExist) {
		return fmt.Errorf("inspect Antigravity MCP config: %w", statErr)
	}
	if _, _, err := updateAntigravityMCPConfig(home, mode); err != nil {
		return err
	}
	return nil
}

func managedLinkPaths(home string, operations []linkOperation) ([]string, error) {
	managedPaths := make([]string, 0, len(operations))
	for _, operation := range operations {
		managedPaths = append(managedPaths, operation.path)
	}
	claudeRoot := filepath.Join(home, ".claude", "agents")
	entries, err := os.ReadDir(claudeRoot)
	if err == nil {
		for _, entry := range entries {
			if isManagedClaudeAgentFile(entry.Name()) {
				managedPaths = append(managedPaths, filepath.Join(claudeRoot, entry.Name()))
			}
		}
	} else if !errors.Is(err, fs.ErrNotExist) {
		return nil, fmt.Errorf("list Claude agents: %w", err)
	}
	agentsRoot := filepath.Join(home, ".gemini", "config", "agents")
	entries, err = os.ReadDir(agentsRoot)
	if err == nil {
		for _, entry := range entries {
			if isManagedAgentName(entry.Name()) {
				managedPaths = append(managedPaths, filepath.Join(agentsRoot, entry.Name()))
			}
		}
	} else if !errors.Is(err, fs.ErrNotExist) {
		return nil, fmt.Errorf("list Antigravity agents: %w", err)
	}
	codexRoot := filepath.Join(home, ".codex")
	entries, err = os.ReadDir(codexRoot)
	if err == nil {
		for _, entry := range entries {
			if isManagedCodexProfileFile(entry.Name()) {
				managedPaths = append(managedPaths, filepath.Join(codexRoot, entry.Name()))
			}
		}
	} else if !errors.Is(err, fs.ErrNotExist) {
		return nil, fmt.Errorf("list Codex profiles: %w", err)
	}
	sort.Strings(managedPaths)
	return compactStrings(managedPaths), nil
}

func validateInstallOptions(options InstallOptions) (string, string, error) {
	switch options.Mode {
	case InstallApply, InstallDryRun, InstallCheck, InstallUninstall:
	default:
		return "", "", fmt.Errorf("unsupported install mode %q", options.Mode)
	}
	if !filepath.IsAbs(options.HomeDir) || !filepath.IsAbs(options.RepositoryRoot) {
		return "", "", fmt.Errorf("home and repository roots must be absolute")
	}
	home := filepath.Clean(options.HomeDir)
	repositoryRoot := filepath.Clean(options.RepositoryRoot)
	if home == string(filepath.Separator) || repositoryRoot == string(filepath.Separator) {
		return "", "", fmt.Errorf("home and repository roots may not be filesystem root")
	}
	if home == repositoryRoot {
		return "", "", fmt.Errorf("home and repository roots must differ")
	}
	return home, repositoryRoot, nil
}

type linkOperation struct {
	path   string
	target string
	file   bool
}

type installPathSnapshot struct {
	path       string
	exists     bool
	linkTarget string
	content    []byte
	mode       fs.FileMode
}

type installTransaction struct {
	snapshots     []installPathSnapshot
	afterMutation func(string) error
}

func beginInstallTransaction(home string, operations []linkOperation, options InstallOptions) (*installTransaction, error) {
	if options.Mode != InstallApply && options.Mode != InstallUninstall {
		return nil, nil
	}
	paths, err := managedLinkPaths(home, operations)
	if err != nil {
		return nil, fmt.Errorf("enumerate installer-owned links for rollback: %w", err)
	}
	paths = append(paths, filepath.Join(home, ".codex", "config.toml"))
	paths = append(paths, globalInstructionPaths(home)...)
	paths = append(paths, antigravityMCPConfigPath(home))
	sort.Strings(paths)
	paths = compactStrings(paths)

	transaction := &installTransaction{
		snapshots:     make([]installPathSnapshot, 0, len(paths)),
		afterMutation: options.afterMutation,
	}
	for _, pathname := range paths {
		snapshot, err := captureInstallPath(pathname)
		if err != nil {
			return nil, fmt.Errorf("capture rollback state for %s: %w", pathname, err)
		}
		transaction.snapshots = append(transaction.snapshots, snapshot)
	}
	return transaction, nil
}

func captureInstallPath(pathname string) (installPathSnapshot, error) {
	snapshot := installPathSnapshot{path: pathname}
	info, err := os.Lstat(pathname)
	if errors.Is(err, fs.ErrNotExist) {
		return snapshot, nil
	}
	if err != nil {
		return installPathSnapshot{}, err
	}
	snapshot.exists = true
	snapshot.mode = info.Mode().Perm()
	if info.Mode()&os.ModeSymlink != 0 {
		snapshot.linkTarget, err = os.Readlink(pathname)
		return snapshot, err
	}
	if !info.Mode().IsRegular() {
		return installPathSnapshot{}, fmt.Errorf("installer-owned path is neither a symlink nor regular file")
	}
	snapshot.content, err = os.ReadFile(pathname)
	return snapshot, err
}

func (transaction *installTransaction) mutated(pathname string) error {
	if transaction == nil || transaction.afterMutation == nil {
		return nil
	}
	return transaction.afterMutation(pathname)
}

func (transaction *installTransaction) rollback() error {
	if transaction == nil {
		return nil
	}
	var rollbackErrors []error
	for index := len(transaction.snapshots) - 1; index >= 0; index-- {
		if err := restoreInstallPath(transaction.snapshots[index]); err != nil {
			rollbackErrors = append(rollbackErrors, err)
		}
	}
	return errors.Join(rollbackErrors...)
}

func restoreInstallPath(snapshot installPathSnapshot) error {
	info, err := os.Lstat(snapshot.path)
	if err == nil {
		if info.Mode()&os.ModeSymlink == 0 && !info.Mode().IsRegular() {
			return fmt.Errorf("refuse to replace unexpected rollback target %s", snapshot.path)
		}
		if err := os.Remove(snapshot.path); err != nil {
			return fmt.Errorf("remove current rollback target %s: %w", snapshot.path, err)
		}
	} else if !errors.Is(err, fs.ErrNotExist) {
		return fmt.Errorf("inspect rollback target %s: %w", snapshot.path, err)
	}
	if !snapshot.exists {
		return nil
	}
	if err := os.MkdirAll(filepath.Dir(snapshot.path), 0o755); err != nil {
		return fmt.Errorf("create rollback parent for %s: %w", snapshot.path, err)
	}
	if snapshot.linkTarget != "" {
		if err := os.Symlink(snapshot.linkTarget, snapshot.path); err != nil {
			return fmt.Errorf("restore rollback link %s: %w", snapshot.path, err)
		}
		return nil
	}
	if err := writeFileAtomic(snapshot.path, snapshot.content, snapshot.mode); err != nil {
		return fmt.Errorf("restore rollback file %s: %w", snapshot.path, err)
	}
	return nil
}

func reconcileLinks(repositoryRoot, home string, operations []linkOperation, mode InstallMode, result *InstallResult, transaction *installTransaction) error {
	for _, operation := range operations {
		if err := requireManagedSource(repositoryRoot, operation); err != nil {
			return fmt.Errorf("link source %s: %w", operation.target, err)
		}
		matches, err := linkMatches(operation.path, operation.target)
		if err != nil {
			return err
		}
		if matches {
			result.Actions = append(result.Actions, "current "+operation.path)
			continue
		}
		if mode == InstallCheck {
			compatible, err := linkResolvesTo(operation.path, operation.target)
			if err != nil {
				return err
			}
			if compatible {
				result.Actions = append(result.Actions, "current via compatibility link "+operation.path)
				continue
			}
			return fmt.Errorf("managed link is missing or stale: %s", operation.path)
		}
		result.Actions = append(result.Actions, "link "+operation.path+" -> "+operation.target)
		if mode == InstallDryRun {
			continue
		}
		if err := replaceSymlink(operation.path, operation.target); err != nil {
			return err
		}
		if err := transaction.mutated(operation.path); err != nil {
			return err
		}
	}
	if err := cleanupStaleAntigravity(home, operations, mode, result, transaction); err != nil {
		return err
	}
	if err := cleanupStaleClaudeAgents(home, operations, mode, result, transaction); err != nil {
		return err
	}
	return cleanupStaleCodexProfiles(home, operations, mode, result, transaction)
}

func linkMatches(pathname, target string) (bool, error) {
	info, err := os.Lstat(pathname)
	if errors.Is(err, fs.ErrNotExist) {
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf("inspect managed link %s: %w", pathname, err)
	}
	if info.Mode()&os.ModeSymlink == 0 {
		return false, fmt.Errorf("refuse to replace non-symlink managed target %s", pathname)
	}
	current, err := os.Readlink(pathname)
	if err != nil {
		return false, fmt.Errorf("read managed link %s: %w", pathname, err)
	}
	return current == target, nil
}

// linkResolvesTo accepts an old installer-owned link only when the complete
// filesystem resolution is the same as the current repository target. This is
// deliberately check-only: an apply still rewrites links to the direct current
// target, allowing a temporary repository compatibility shim to be retired.
func linkResolvesTo(pathname, target string) (bool, error) {
	current, err := filepath.EvalSymlinks(pathname)
	if errors.Is(err, fs.ErrNotExist) {
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf("resolve managed link %s: %w", pathname, err)
	}
	expected, err := filepath.EvalSymlinks(target)
	if errors.Is(err, fs.ErrNotExist) {
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf("resolve managed target %s: %w", target, err)
	}
	return filepath.Clean(current) == filepath.Clean(expected), nil
}

func replaceSymlink(pathname, target string) error {
	if err := os.MkdirAll(filepath.Dir(pathname), 0o755); err != nil {
		return err
	}
	info, err := os.Lstat(pathname)
	if err == nil {
		if info.Mode()&os.ModeSymlink == 0 {
			return fmt.Errorf("refuse to replace non-symlink managed target %s", pathname)
		}
		if err := os.Remove(pathname); err != nil {
			return err
		}
	} else if !errors.Is(err, fs.ErrNotExist) {
		return err
	}
	if err := os.Symlink(target, pathname); err != nil {
		return fmt.Errorf("create managed link %s: %w", pathname, err)
	}
	return nil
}

func cleanupStaleAntigravity(home string, operations []linkOperation, mode InstallMode, result *InstallResult, transaction *installTransaction) error {
	agentsRoot := filepath.Join(home, ".gemini", "config", "agents")
	expected := make(map[string]struct{}, len(operations))
	for _, operation := range operations {
		if filepath.Dir(operation.path) == agentsRoot {
			expected[filepath.Base(operation.path)] = struct{}{}
		}
	}
	entries, err := os.ReadDir(agentsRoot)
	if errors.Is(err, fs.ErrNotExist) {
		return nil
	}
	if err != nil {
		return fmt.Errorf("list Antigravity agents: %w", err)
	}
	for _, entry := range entries {
		if !isManagedAgentName(entry.Name()) {
			continue
		}
		if _, ok := expected[entry.Name()]; ok {
			continue
		}
		pathName := filepath.Join(agentsRoot, entry.Name())
		info, err := os.Lstat(pathName)
		if err != nil {
			return err
		}
		if info.Mode()&os.ModeSymlink == 0 {
			return fmt.Errorf("refuse to remove non-symlink stale Antigravity target %s", pathName)
		}
		if mode == InstallCheck {
			return fmt.Errorf("stale managed Antigravity link: %s", pathName)
		}
		result.Actions = append(result.Actions, "remove stale "+pathName)
		if mode == InstallDryRun {
			continue
		}
		if err := os.Remove(pathName); err != nil {
			return err
		}
		if err := transaction.mutated(pathName); err != nil {
			return err
		}
	}
	return nil
}

func cleanupStaleClaudeAgents(home string, operations []linkOperation, mode InstallMode, result *InstallResult, transaction *installTransaction) error {
	agentsRoot := filepath.Join(home, ".claude", "agents")
	expected := make(map[string]struct{}, len(operations))
	for _, operation := range operations {
		if filepath.Dir(operation.path) == agentsRoot && isManagedClaudeAgentFile(filepath.Base(operation.path)) {
			expected[filepath.Base(operation.path)] = struct{}{}
		}
	}
	entries, err := os.ReadDir(agentsRoot)
	if errors.Is(err, fs.ErrNotExist) {
		return nil
	}
	if err != nil {
		return fmt.Errorf("list Claude agents: %w", err)
	}
	for _, entry := range entries {
		if !isManagedClaudeAgentFile(entry.Name()) {
			continue
		}
		if _, ok := expected[entry.Name()]; ok {
			continue
		}
		pathname := filepath.Join(agentsRoot, entry.Name())
		info, err := os.Lstat(pathname)
		if err != nil {
			return err
		}
		if info.Mode()&os.ModeSymlink == 0 {
			return fmt.Errorf("refuse to remove non-symlink stale Claude agent %s", pathname)
		}
		if mode == InstallCheck {
			return fmt.Errorf("stale managed Claude agent: %s", pathname)
		}
		result.Actions = append(result.Actions, "remove stale "+pathname)
		if mode == InstallDryRun {
			continue
		}
		if err := os.Remove(pathname); err != nil {
			return err
		}
		if err := transaction.mutated(pathname); err != nil {
			return err
		}
	}
	return nil
}

func cleanupStaleCodexProfiles(home string, operations []linkOperation, mode InstallMode, result *InstallResult, transaction *installTransaction) error {
	codexRoot := filepath.Join(home, ".codex")
	expected := make(map[string]struct{}, len(operations))
	for _, operation := range operations {
		if filepath.Dir(operation.path) == codexRoot && isManagedCodexProfileFile(filepath.Base(operation.path)) {
			expected[filepath.Base(operation.path)] = struct{}{}
		}
	}
	entries, err := os.ReadDir(codexRoot)
	if errors.Is(err, fs.ErrNotExist) {
		return nil
	}
	if err != nil {
		return fmt.Errorf("list Codex profiles: %w", err)
	}
	for _, entry := range entries {
		if !isManagedCodexProfileFile(entry.Name()) {
			continue
		}
		if _, ok := expected[entry.Name()]; ok {
			continue
		}
		pathname := filepath.Join(codexRoot, entry.Name())
		info, err := os.Lstat(pathname)
		if err != nil {
			return err
		}
		if info.Mode()&os.ModeSymlink == 0 {
			return fmt.Errorf("refuse to remove non-symlink stale Codex profile %s", pathname)
		}
		if mode == InstallCheck {
			return fmt.Errorf("stale managed Codex profile: %s", pathname)
		}
		result.Actions = append(result.Actions, "remove stale "+pathname)
		if mode == InstallDryRun {
			continue
		}
		if err := os.Remove(pathname); err != nil {
			return err
		}
		if err := transaction.mutated(pathname); err != nil {
			return err
		}
	}
	return nil
}

func isManagedCodexProfileFile(name string) bool {
	if !strings.HasSuffix(name, ".config.toml") {
		return false
	}
	base := strings.TrimSuffix(name, ".config.toml")
	return isManagedAgentName(base)
}

func isManagedClaudeAgentFile(name string) bool {
	if !strings.HasSuffix(name, ".md") {
		return false
	}
	return isManagedAgentName(strings.TrimSuffix(name, ".md"))
}

func uninstallLinks(home string, operations []linkOperation, mode InstallMode, result *InstallResult, transaction *installTransaction) error {
	paths := make([]string, 0, len(operations))
	for _, operation := range operations {
		paths = append(paths, operation.path)
	}
	claudeRoot := filepath.Join(home, ".claude", "agents")
	entries, err := os.ReadDir(claudeRoot)
	if err == nil {
		for _, entry := range entries {
			if isManagedClaudeAgentFile(entry.Name()) {
				paths = append(paths, filepath.Join(claudeRoot, entry.Name()))
			}
		}
	} else if !errors.Is(err, fs.ErrNotExist) {
		return err
	}
	agentsRoot := filepath.Join(home, ".gemini", "config", "agents")
	entries, err = os.ReadDir(agentsRoot)
	if err == nil {
		for _, entry := range entries {
			if isManagedAgentName(entry.Name()) {
				paths = append(paths, filepath.Join(agentsRoot, entry.Name()))
			}
		}
	} else if !errors.Is(err, fs.ErrNotExist) {
		return err
	}
	codexRoot := filepath.Join(home, ".codex")
	entries, err = os.ReadDir(codexRoot)
	if err == nil {
		for _, entry := range entries {
			if isManagedCodexProfileFile(entry.Name()) {
				paths = append(paths, filepath.Join(codexRoot, entry.Name()))
			}
		}
	} else if !errors.Is(err, fs.ErrNotExist) {
		return err
	}
	sort.Strings(paths)
	paths = compactStrings(paths)
	for _, pathname := range paths {
		info, err := os.Lstat(pathname)
		if errors.Is(err, fs.ErrNotExist) {
			continue
		}
		if err != nil {
			return err
		}
		if info.Mode()&os.ModeSymlink == 0 {
			return fmt.Errorf("refuse to uninstall non-symlink target %s", pathname)
		}
		result.Actions = append(result.Actions, "unlink "+pathname)
		if mode != InstallDryRun {
			if err := os.Remove(pathname); err != nil {
				return err
			}
			if err := transaction.mutated(pathname); err != nil {
				return err
			}
		}
	}
	return nil
}

func compactStrings(values []string) []string {
	if len(values) == 0 {
		return values
	}
	result := values[:1]
	for _, value := range values[1:] {
		if value != result[len(result)-1] {
			result = append(result, value)
		}
	}
	return result
}

func requireManagedSource(repositoryRoot string, operation linkOperation) error {
	pathname := operation.target
	generatedRoot := filepath.Join(repositoryRoot, "harness-agents", "rendered")
	relative, err := filepath.Rel(generatedRoot, filepath.Clean(pathname))
	if err != nil || relative == "." || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) || filepath.IsAbs(relative) {
		return fmt.Errorf("path is outside generated coding-fleet tree")
	}
	if operation.file {
		if err := rejectSymlinkComponents(repositoryRoot, filepath.Dir(pathname)); err != nil {
			return err
		}
		if err := rejectSymlinkFile(pathname); err != nil {
			return err
		}
	} else if err := rejectSymlinkComponents(repositoryRoot, pathname); err != nil {
		return err
	}
	info, err := os.Lstat(pathname)
	if err != nil {
		return err
	}
	if info.Mode()&os.ModeSymlink != 0 {
		return fmt.Errorf("managed source is a symlink")
	}
	if operation.file && !info.Mode().IsRegular() {
		return fmt.Errorf("not a regular file")
	}
	if !operation.file && !info.IsDir() {
		return fmt.Errorf("not a directory")
	}
	return nil
}

func reconcileCodexConfig(home string, block []byte, mode InstallMode, result *InstallResult, transaction *installTransaction) error {
	configPath := filepath.Join(home, ".codex", "config.toml")
	current, err := os.ReadFile(configPath)
	if err != nil && !errors.Is(err, fs.ErrNotExist) {
		return fmt.Errorf("read Codex config: %w", err)
	}
	updated, found, err := updateManagedBlock(current, block, mode == InstallUninstall)
	if err != nil {
		return fmt.Errorf("Codex config markers: %w", err)
	}
	if bytes.Equal(current, updated) {
		result.Actions = append(result.Actions, "current "+configPath)
		return nil
	}
	if mode == InstallCheck {
		if !found {
			return fmt.Errorf("Codex managed block is missing from %s", configPath)
		}
		compatible, err := codexManagedBlockResolves(current, block)
		if err != nil {
			return fmt.Errorf("resolve Codex managed block paths: %w", err)
		}
		if compatible {
			result.Actions = append(result.Actions, "current via compatibility paths "+configPath)
			return nil
		}
		return fmt.Errorf("Codex managed block is stale in %s", configPath)
	}
	action := "update " + configPath
	if mode == InstallUninstall {
		action = "remove managed block from " + configPath
	}
	result.Actions = append(result.Actions, action)
	if mode == InstallDryRun {
		return nil
	}
	fileMode := fs.FileMode(0o600)
	if info, statErr := os.Stat(configPath); statErr == nil {
		fileMode = info.Mode().Perm()
	}
	if err := writeFileAtomic(configPath, updated, fileMode); err != nil {
		return fmt.Errorf("write Codex config atomically: %w", err)
	}
	return transaction.mutated(configPath)
}

func codexManagedBlockResolves(current, expected []byte) (bool, error) {
	currentBlock := delimitedBlock(current, codexBeginMarker, codexEndMarker)
	if currentBlock == nil {
		return false, nil
	}
	currentResolved, currentOK, err := resolveCodexConfigPaths(currentBlock)
	if err != nil || !currentOK {
		return false, err
	}
	expectedResolved, expectedOK, err := resolveCodexConfigPaths(expected)
	if err != nil || !expectedOK {
		return false, err
	}
	return bytes.Equal(currentResolved, expectedResolved), nil
}

func resolveCodexConfigPaths(block []byte) ([]byte, bool, error) {
	lines := strings.Split(string(block), "\n")
	for index, line := range lines {
		const prefix = "config_file = "
		if !strings.HasPrefix(line, prefix) {
			continue
		}
		pathname, err := strconv.Unquote(strings.TrimPrefix(line, prefix))
		if err != nil || !filepath.IsAbs(pathname) {
			return nil, false, nil
		}
		resolved, err := filepath.EvalSymlinks(pathname)
		if errors.Is(err, fs.ErrNotExist) {
			return nil, false, nil
		}
		if err != nil {
			return nil, false, err
		}
		lines[index] = prefix + strconv.Quote(filepath.Clean(resolved))
	}
	return []byte(strings.Join(lines, "\n")), true, nil
}

func delimitedBlock(content []byte, beginMarker, endMarker string) []byte {
	beginIndex := bytes.Index(content, []byte(beginMarker))
	if beginIndex < 0 {
		return nil
	}
	relativeEnd := bytes.Index(content[beginIndex:], []byte(endMarker))
	if relativeEnd < 0 {
		return nil
	}
	endIndex := beginIndex + relativeEnd + len(endMarker)
	if endIndex < len(content) && content[endIndex] == '\n' {
		endIndex++
	}
	return content[beginIndex:endIndex]
}

func globalInstructionPaths(home string) []string {
	return []string{
		filepath.Join(home, ".agents", "AGENTS.md"),
		filepath.Join(home, ".codex", "AGENTS.md"),
		filepath.Join(home, ".claude", "CLAUDE.md"),
		filepath.Join(home, ".gemini", "GEMINI.md"),
	}
}

func reconcileGlobalInstructions(home string, mode InstallMode, result *InstallResult, transaction *installTransaction) error {
	for _, pathname := range globalInstructionPaths(home) {
		current, err := os.ReadFile(pathname)
		if err != nil && !errors.Is(err, fs.ErrNotExist) {
			return fmt.Errorf("read global instruction file %s: %w", pathname, err)
		}
		updated, found, err := updateDelimitedBlock(current, globalCodingRoutingBlock, mode == InstallUninstall, routingBeginMarker, routingEndMarker)
		if err != nil {
			return fmt.Errorf("global instruction markers in %s: %w", pathname, err)
		}
		if bytes.Equal(current, updated) {
			result.Actions = append(result.Actions, "current "+pathname)
			continue
		}
		if mode == InstallCheck {
			if !found {
				return fmt.Errorf("global coding-routing block is missing from %s", pathname)
			}
			return fmt.Errorf("global coding-routing block is stale in %s", pathname)
		}
		action := "update " + pathname
		if mode == InstallUninstall {
			action = "remove managed block from " + pathname
		}
		result.Actions = append(result.Actions, action)
		if mode == InstallDryRun {
			continue
		}
		fileMode := fs.FileMode(0o600)
		if info, statErr := os.Stat(pathname); statErr == nil {
			fileMode = info.Mode().Perm()
		}
		if err := writeFileAtomic(pathname, updated, fileMode); err != nil {
			return fmt.Errorf("write global instruction file %s atomically: %w", pathname, err)
		}
		if err := transaction.mutated(pathname); err != nil {
			return err
		}
	}
	return nil
}

func antigravityMCPConfigPath(home string) string {
	return filepath.Join(home, ".gemini", "config", "mcp_config.json")
}

type antigravityMCPRegistration struct {
	Command      string   `json:"command"`
	Args         []string `json:"args"`
	EnabledTools []string `json:"enabledTools"`
}

func canonicalAntigravityMCPRegistration() antigravityMCPRegistration {
	return antigravityMCPRegistration{
		Command: supervisorRunplaneBinary, Args: []string{"mcp"}, EnabledTools: []string{supervisorMCPToolName},
	}
}

// updateAntigravityMCPConfig preserves all unknown top-level keys and server
// values while owning exactly one named stdio registration. A conflicting
// value at that reserved name rejects rather than being silently replaced.
func updateAntigravityMCPConfig(home string, mode InstallMode) ([]byte, bool, error) {
	pathname := antigravityMCPConfigPath(home)
	current, err := os.ReadFile(pathname)
	if err != nil && !errors.Is(err, fs.ErrNotExist) {
		return nil, false, fmt.Errorf("read Antigravity MCP config: %w", err)
	}
	document := map[string]json.RawMessage{}
	if len(bytes.TrimSpace(current)) != 0 {
		if err := json.Unmarshal(current, &document); err != nil {
			return nil, false, fmt.Errorf("decode Antigravity MCP config: %w", err)
		}
	}
	servers := map[string]json.RawMessage{}
	if raw, ok := document["mcpServers"]; ok {
		if err := json.Unmarshal(raw, &servers); err != nil {
			return nil, false, errors.New("Antigravity mcpServers must be an object")
		}
	}
	expected, err := json.Marshal(canonicalAntigravityMCPRegistration())
	if err != nil {
		return nil, false, err
	}
	existing, found := servers[supervisorMCPServerName]
	if found {
		var left, right any
		if json.Unmarshal(existing, &left) != nil || json.Unmarshal(expected, &right) != nil || !jsonSemanticEqual(left, right) {
			return nil, false, fmt.Errorf("refuse conflicting Antigravity MCP registration %q", supervisorMCPServerName)
		}
	}
	if mode == InstallUninstall {
		if !found {
			return append([]byte(nil), current...), false, nil
		}
		delete(servers, supervisorMCPServerName)
	} else {
		if found {
			return append([]byte(nil), current...), true, nil
		}
		servers[supervisorMCPServerName] = expected
	}
	if len(servers) == 0 {
		delete(document, "mcpServers")
	} else {
		encodedServers, err := json.Marshal(servers)
		if err != nil {
			return nil, false, err
		}
		document["mcpServers"] = encodedServers
	}
	if len(document) == 0 && mode == InstallUninstall {
		return []byte{}, true, nil
	}
	updated, err := json.MarshalIndent(document, "", "  ")
	if err != nil {
		return nil, false, err
	}
	return append(updated, '\n'), found, nil
}

func jsonSemanticEqual(left, right any) bool {
	leftJSON, leftErr := json.Marshal(left)
	rightJSON, rightErr := json.Marshal(right)
	return leftErr == nil && rightErr == nil && bytes.Equal(leftJSON, rightJSON)
}

func reconcileAntigravityMCP(home string, mode InstallMode, result *InstallResult, transaction *installTransaction) error {
	pathname := antigravityMCPConfigPath(home)
	current, readErr := os.ReadFile(pathname)
	if readErr != nil && !errors.Is(readErr, fs.ErrNotExist) {
		return readErr
	}
	updated, found, err := updateAntigravityMCPConfig(home, mode)
	if err != nil {
		return err
	}
	if bytes.Equal(current, updated) {
		result.Actions = append(result.Actions, "current "+pathname)
		return nil
	}
	if mode == InstallCheck {
		if !found {
			return fmt.Errorf("Antigravity MCP registration %q is missing", supervisorMCPServerName)
		}
		return fmt.Errorf("Antigravity MCP registration %q is stale", supervisorMCPServerName)
	}
	action := "update " + pathname
	if mode == InstallUninstall {
		action = "remove managed MCP registration from " + pathname
	}
	result.Actions = append(result.Actions, action)
	if mode == InstallDryRun {
		return nil
	}
	fileMode := fs.FileMode(0o600)
	if info, statErr := os.Stat(pathname); statErr == nil {
		fileMode = info.Mode().Perm()
	}
	if len(updated) == 0 {
		if err := os.Remove(pathname); err != nil && !errors.Is(err, fs.ErrNotExist) {
			return err
		}
	} else if err := writeFileAtomic(pathname, updated, fileMode); err != nil {
		return fmt.Errorf("write Antigravity MCP config atomically: %w", err)
	}
	return transaction.mutated(pathname)
}

func verifyInstalledDigests(home string, rendered RenderResult) (int, error) {
	verified := 0
	for _, file := range rendered.Files {
		installedPath, err := installedProjectionPath(home, file.Path)
		if err != nil {
			return verified, err
		}
		content, err := os.ReadFile(installedPath)
		if err != nil {
			return verified, fmt.Errorf("read installed projection %s: %w", installedPath, err)
		}
		wantDigest := sha256.Sum256(file.Content)
		gotDigest := sha256.Sum256(content)
		if gotDigest != wantDigest {
			return verified, fmt.Errorf("installed projection digest mismatch: %s", installedPath)
		}
		verified++
	}
	return verified, nil
}

func installedProjectionPath(home, renderedPath string) (string, error) {
	parts := strings.Split(filepath.ToSlash(renderedPath), "/")
	switch {
	case len(parts) == 2 && parts[0] == "claude" && strings.HasSuffix(parts[1], ".md"):
		return filepath.Join(home, ".claude", "agents", parts[1]), nil
	case len(parts) == 2 && parts[0] == "codex" && strings.HasSuffix(parts[1], ".toml"):
		name := strings.TrimSuffix(parts[1], ".toml")
		return filepath.Join(home, ".codex", name+".config.toml"), nil
	case len(parts) == 3 && parts[0] == "antigravity" && parts[2] == "agent.md":
		return filepath.Join(home, ".gemini", "config", "agents", parts[1], "agent.md"), nil
	default:
		return "", fmt.Errorf("unsupported installed projection path %q", renderedPath)
	}
}

func updateManagedBlock(current, block []byte, uninstall bool) ([]byte, bool, error) {
	return updateDelimitedBlock(current, block, uninstall, codexBeginMarker, codexEndMarker)
}

func updateDelimitedBlock(current, block []byte, uninstall bool, beginMarker, endMarker string) ([]byte, bool, error) {
	begin := []byte(beginMarker)
	end := []byte(endMarker)
	if bytes.Count(current, begin) > 1 || bytes.Count(current, end) > 1 {
		return nil, false, fmt.Errorf("duplicate managed markers")
	}
	beginIndex := bytes.Index(current, begin)
	endIndex := bytes.Index(current, end)
	if (beginIndex < 0) != (endIndex < 0) {
		return nil, false, fmt.Errorf("begin and end markers must both be present")
	}
	if beginIndex >= 0 && endIndex < beginIndex+len(begin) {
		return nil, false, fmt.Errorf("managed markers are out of order")
	}
	if beginIndex >= 0 && (!isFullLine(current, beginIndex, len(begin)) || !isFullLine(current, endIndex, len(end))) {
		return nil, false, fmt.Errorf("managed markers must occupy complete lines")
	}
	if beginIndex < 0 {
		if uninstall {
			return append([]byte(nil), current...), false, nil
		}
		updated := append([]byte(nil), current...)
		if len(updated) > 0 && updated[len(updated)-1] != '\n' {
			updated = append(updated, '\n')
		}
		updated = append(updated, block...)
		return updated, false, nil
	}
	managedEnd := endIndex + len(end)
	if managedEnd < len(current) && current[managedEnd] == '\n' {
		managedEnd++
	}
	replacement := block
	if uninstall {
		replacement = nil
	}
	updated := make([]byte, 0, len(current)-managedEnd+beginIndex+len(replacement))
	updated = append(updated, current[:beginIndex]...)
	updated = append(updated, replacement...)
	updated = append(updated, current[managedEnd:]...)
	return updated, true, nil
}

func isFullLine(content []byte, start, length int) bool {
	lineStart := start == 0 || content[start-1] == '\n'
	end := start + length
	lineEnd := end == len(content) || content[end] == '\n'
	return lineStart && lineEnd
}
