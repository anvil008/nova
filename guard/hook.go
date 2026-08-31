package guard

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// Harness names the supported payload and response dialects.
type Harness string

const (
	HarnessClaude      Harness = "claude"
	HarnessCodex       Harness = "codex"
	HarnessAntigravity Harness = "agy"
)

// Event names the supported hook points. Every installed registration passes
// --event: Antigravity payloads carry no event field, and a payload that fails
// to decode carries nothing the guard could classify itself.
const (
	EventPreToolUse   = "PreToolUse"
	EventPostToolUse  = "PostToolUse"
	EventStop         = "Stop"
	EventSubagentStop = "SubagentStop"
)

// EditToolMatchers and ShellToolMatchers are the per-harness tool names the
// installer registers and the guard recognizes.
var (
	EditToolMatchers = map[Harness]string{
		HarnessClaude:      "Edit|Write|MultiEdit|NotebookEdit",
		HarnessCodex:       "apply_patch",
		HarnessAntigravity: "write_to_file|replace_file_content|multi_replace_file_content",
	}
	ShellToolMatchers = map[Harness]string{
		HarnessClaude: "Bash", HarnessCodex: "Bash", HarnessAntigravity: "run_command",
	}
)

// payload is the union of the three harness stdin shapes. Each harness fills
// only its own fields; unknown fields are ignored because hook payloads grow.
type payload struct {
	HookEventName string          `json:"hook_event_name"`
	ToolName      string          `json:"tool_name"`
	ToolInput     json.RawMessage `json:"tool_input"`
	CWD           string          `json:"cwd"`

	SessionID string `json:"session_id"`
	TurnID    string `json:"turn_id"`

	ToolCall *struct {
		Name string          `json:"name"`
		Args json.RawMessage `json:"args"`
	} `json:"toolCall"`
	WorkspacePaths []string `json:"workspacePaths"`
	ConversationID string   `json:"conversationId"`

	TerminationReason string `json:"terminationReason"`
	FullyIdle         bool   `json:"fullyIdle"`
}

// maxPayloadBytes bounds a hook payload. It has to comfortably exceed a whole
// file written by an edit tool: a truncated read is indistinguishable from
// malformed JSON, and treating either as "allow" is the bypass.
const maxPayloadBytes = 64 << 20

func decodePayload(reader io.Reader) (payload, error) {
	var decoded payload
	if reader == nil {
		return decoded, nil
	}
	raw, err := io.ReadAll(io.LimitReader(reader, maxPayloadBytes+1))
	if err != nil {
		return decoded, err
	}
	if len(raw) > maxPayloadBytes {
		return decoded, fmt.Errorf("hook payload exceeds %d bytes", maxPayloadBytes)
	}
	if len(strings.TrimSpace(string(raw))) == 0 {
		return decoded, nil
	}
	if err := json.Unmarshal(raw, &decoded); err != nil {
		return decoded, fmt.Errorf("decode hook payload: %w", err)
	}
	return decoded, nil
}

func (p payload) event(override string) string {
	if override != "" {
		return override
	}
	if p.HookEventName != "" {
		return p.HookEventName
	}
	if p.TerminationReason != "" || p.FullyIdle {
		return EventStop
	}
	return EventPreToolUse
}

func (p payload) tool() string {
	if p.ToolCall != nil {
		return p.ToolCall.Name
	}
	return p.ToolName
}

// session identifies the harness conversation the touch log is keyed on.
// Claude and Antigravity name it directly; Codex documents only a per-turn
// identifier, which still scopes the log more tightly than nothing.
func (p payload) session() string {
	for _, candidate := range []string{p.SessionID, p.ConversationID, p.TurnID} {
		if trimmed := strings.TrimSpace(candidate); trimmed != "" {
			return trimmed
		}
	}
	return ""
}

func (p payload) workingDirectory(fallback string) string {
	if p.CWD != "" {
		return p.CWD
	}
	if len(p.WorkspacePaths) > 0 && p.WorkspacePaths[0] != "" {
		return p.WorkspacePaths[0]
	}
	return fallback
}

// pathKeys are the argument names the three harnesses use for an edit target.
var pathKeys = []string{"file_path", "filePath", "path", "notebook_path", "TargetFile", "target_file", "AbsolutePath", "absolute_path"}

// editTargets extracts every path an edit tool call would write.
func (p payload) editTargets() []string {
	arguments := p.ToolInput
	if p.ToolCall != nil {
		arguments = p.ToolCall.Args
	}
	if len(arguments) == 0 {
		return nil
	}
	var object map[string]json.RawMessage
	if json.Unmarshal(arguments, &object) != nil {
		return nil
	}
	targets := make(map[string]struct{})
	for _, key := range pathKeys {
		var value string
		if raw, ok := object[key]; ok && json.Unmarshal(raw, &value) == nil && value != "" {
			targets[value] = struct{}{}
		}
	}
	// Codex apply_patch carries the whole envelope as one string; its file
	// headers are the only place the touched paths appear.
	for _, key := range []string{"input", "patch"} {
		var envelope string
		if raw, ok := object[key]; ok && json.Unmarshal(raw, &envelope) == nil {
			for _, target := range patchEnvelopePaths(envelope) {
				targets[target] = struct{}{}
			}
		}
	}
	var changes map[string]json.RawMessage
	if raw, ok := object["changes"]; ok && json.Unmarshal(raw, &changes) == nil {
		for target := range changes {
			targets[target] = struct{}{}
		}
	}
	ordered := make([]string, 0, len(targets))
	for target := range targets {
		ordered = append(ordered, target)
	}
	sort.Strings(ordered)
	return ordered
}

func patchEnvelopePaths(envelope string) []string {
	prefixes := []string{"*** Add File: ", "*** Update File: ", "*** Delete File: ", "*** Move to: "}
	paths := make([]string, 0)
	for _, line := range strings.Split(envelope, "\n") {
		for _, prefix := range prefixes {
			if strings.HasPrefix(line, prefix) {
				paths = append(paths, strings.TrimSpace(strings.TrimPrefix(line, prefix)))
			}
		}
	}
	return paths
}

// response is the harness-neutral decision the dialect writers project.
type response struct {
	deny   bool
	notify bool
	reason string
}

func isKnownHookEvent(event string) bool {
	switch event {
	case EventPreToolUse, EventPostToolUse, EventStop, EventSubagentStop:
		return true
	default:
		return false
	}
}

func hasActiveSeal(decoded payload, fallbackDir string) bool {
	workingDirectory := decoded.workingDirectory(fallbackDir)
	cache := newLookups()
	if repository, ok := cache.repositoryForPath(workingDirectory, "."); ok {
		if loaded := cache.load(repository); loaded != nil && loaded.seal != nil {
			return true
		}
	}
	if repository, err := repositoryRoot(workingDirectory); err == nil {
		if loaded := cache.load(repository); loaded != nil && loaded.seal != nil {
			return true
		}
	}
	for _, target := range decoded.editTargets() {
		if repository, ok := cache.repositoryForPath(workingDirectory, target); ok {
			if loaded := cache.load(repository); loaded != nil && loaded.seal != nil {
				return true
			}
		}
	}
	for _, repository := range touchedRepositories(decoded.session()) {
		if loaded := cache.load(repository); loaded != nil && loaded.seal != nil {
			return true
		}
	}
	return false
}

// hook is the single entry point every harness registration calls. It stays
// silent for any repository with no seal so non-fleet sessions are untouched.
func hook(options Options, harnessName Harness, eventOverride string) int {
	decoded, decodeErr := decodePayload(options.Stdin)
	if decodeErr != nil {
		// json.Unmarshal can populate fields before it fails, so nothing that
		// came out of an unreadable payload is trusted -- including the cwd
		// that used to decide, on its own, whether any seal was in force.
		decoded = payload{}
	}
	if !isKnownHookEvent(eventOverride) {
		var configErr string
		if eventOverride == "" {
			configErr = "tdd-guard hook misconfigured: --event is required (must be PreToolUse, PostToolUse, Stop, or SubagentStop)"
		} else {
			configErr = fmt.Sprintf("tdd-guard hook misconfigured: --event %q is not a known event (must be PreToolUse, PostToolUse, Stop, or SubagentStop)", eventOverride)
		}
		sealed := false
		if decodeErr != nil {
			s, err := anySealExists()
			sealed = err == nil && s
		} else {
			sealed = hasActiveSeal(decoded, options.Dir)
		}
		if !sealed {
			fmt.Fprintln(options.Stderr, configErr)
			return 0
		}
		event := decoded.event(eventOverride)
		return emit(options, harnessName, event, response{
			deny:   true,
			reason: configErr,
		})
	}
	event := decoded.event(eventOverride)
	if decodeErr != nil {
		// A seal is in force somewhere and the guard cannot tell what the tool
		// would write, so the only safe answer is refusal.
		sealed, err := anySealExists()
		if err != nil || !sealed {
			return 0
		}
		return emit(options, harnessName, event, response{
			deny:   true,
			reason: "tdd-guard: refusing an unreadable hook payload while a test seal is in force: " + decodeErr.Error(),
		})
	}
	workingDirectory := decoded.workingDirectory(options.Dir)
	var decision response
	switch event {
	case EventPreToolUse:
		decision = preToolUse(harnessName, decoded, workingDirectory)
	case EventPostToolUse:
		decision = postToolUse(harnessName, decoded, workingDirectory)
	case EventStop, EventSubagentStop:
		decision = stopGate(decoded, workingDirectory)
	}
	return emit(options, harnessName, event, decision)
}

// preToolUse judges every path the call would write against the seal of the
// repository that owns that path. The session's own directory decides nothing:
// an absolute path, a traversal, or a symlink reaches a sealed tree from
// anywhere on the filesystem.
func preToolUse(harnessName Harness, decoded payload, workingDirectory string) response {
	if !matchesTool(EditToolMatchers[harnessName], decoded.tool()) {
		return response{}
	}
	cache := newLookups()
	blocked, touched := make([]string, 0), make([]string, 0)
	for _, target := range decoded.editTargets() {
		repository, inRepository := cache.repositoryForPath(workingDirectory, target)
		if !inRepository {
			continue
		}
		loaded := cache.load(repository)
		if loaded == nil || loaded.seal == nil {
			continue
		}
		if !containsString(touched, repository) {
			touched = append(touched, repository)
		}
		if isSealedTestPath(loaded, workingDirectory, target) {
			blocked = append(blocked, filepath.ToSlash(target))
		}
	}
	// The write is about to happen, so the log has to exist before the tool
	// runs; a later shell check or Stop gate is the only thing that reads it.
	_ = recordTouchedRepositories(decoded.session(), touched)
	if len(blocked) == 0 {
		return response{}
	}
	return response{deny: true, reason: "tdd-guard: sealed test paths may not be edited during implementation: " + strings.Join(blocked, ", ") + "; amend them with `tdd-guard reseal --reason <text>` instead"}
}

func postToolUse(harnessName Harness, decoded payload, workingDirectory string) response {
	if !matchesTool(ShellToolMatchers[harnessName], decoded.tool()) {
		return response{}
	}
	resolved := sessionScope(decoded, workingDirectory)
	messages := make([]string, 0, len(resolved.states))
	for _, loaded := range resolved.states {
		changed, err := loaded.changedTests()
		if err != nil || len(changed) == 0 {
			continue
		}
		messages = append(messages, resolved.qualify(loaded, strings.Join(changed, ", ")))
	}
	if len(messages) == 0 {
		return response{}
	}
	return response{notify: true, reason: "tdd-guard: sealed tests changed during implementation: " + strings.Join(messages, "; ") + "; restore them or record `tdd-guard reseal --reason <text>`"}
}

func stopGate(decoded payload, workingDirectory string) response {
	resolved := sessionScope(decoded, workingDirectory)
	blockers := make([]string, 0, 3)
	for _, loaded := range resolved.states {
		found, err := stopGateBlockers(loaded)
		if err != nil {
			continue
		}
		for _, blocker := range found {
			blockers = append(blockers, resolved.qualify(loaded, blocker))
		}
	}
	if len(blockers) > 0 {
		return response{deny: true, reason: "tdd-guard: " + strings.Join(blockers, "; ")}
	}
	if resolved.repository != "" {
		cache := newLookups()
		loaded := cache.load(resolved.repository)
		if loaded == nil || loaded.seal == nil {
			if loaded != nil {
				if _, err := os.Stat(loaded.directory); err == nil {
					if found, err := stopGateBlockers(loaded); err == nil && len(found) > 0 {
						return response{
							deny:   true,
							reason: "tdd-guard: " + strings.Join(found, "; "),
						}
					}
				}
			}
			sourcePaths, err := unsealedSourceChanges(resolved.repository)
			if err == nil && len(sourcePaths) > 0 {
				return response{
					notify: true,
					reason: "tdd-guard: source changed without a TDD seal: " + strings.Join(sourcePaths, ", ") + " — RED->seal->GREEN was skipped",
				}
			}
		}
	}
	return response{}
}

func unsealedSourceChanges(repository string) ([]string, error) {
	changed, err := changedWorkingPaths(repository)
	if err != nil {
		return nil, err
	}
	testPatterns, err := configuredPatterns(repository)
	if err != nil {
		testPatterns = DefaultTestPatterns
	}
	seen := make(map[string]struct{})
	sourcePaths := make([]string, 0)
	for _, relPath := range changed {
		if isSourcePath(relPath, testPatterns) {
			if _, exists := seen[relPath]; !exists {
				seen[relPath] = struct{}{}
				sourcePaths = append(sourcePaths, relPath)
			}
		}
	}
	sort.Strings(sourcePaths)
	return sourcePaths, nil
}

func isSourcePath(relPath string, testPatterns []string) bool {
	relPath = filepath.ToSlash(strings.TrimSpace(relPath))
	if relPath == "" {
		return false
	}
	lower := strings.ToLower(relPath)
	if lower == "docs" || strings.HasPrefix(lower, "docs/") {
		return false
	}
	ext := strings.ToLower(filepath.Ext(relPath))
	switch ext {
	case ".md", ".json", ".toml", ".yaml", ".yml":
		return false
	}
	for _, pattern := range testPatterns {
		if matchTestPattern(pattern, relPath) {
			return false
		}
	}
	return true
}

func containsString(values []string, candidate string) bool {
	for _, value := range values {
		if value == candidate {
			return true
		}
	}
	return false
}

func matchesTool(matcher, tool string) bool {
	if tool == "" {
		return false
	}
	for _, candidate := range strings.Split(matcher, "|") {
		if candidate == tool {
			return true
		}
	}
	return false
}

// emit projects one decision into the harness's documented dialect.
//
// PostToolUse cannot block anywhere, so its message goes to stderr. Claude and
// Codex document exit 2 as that channel; Antigravity does not, so its message
// exits 0 rather than claiming a blocking semantic. A `permissionDecision` on
// PostToolUse or Stop is read by nobody, which is why the event has to be known
// from the registration rather than inferred from a payload that may not have
// decoded at all.
func emit(options Options, harnessName Harness, event string, decision response) int {
	if !decision.deny && !decision.notify {
		return 0
	}
	if decision.notify {
		// notify is visible-but-non-blocking. At PostToolUse exit 2 shows the
		// message without blocking (the tool already ran); at Stop exit 2 would
		// BLOCK, so surface it through a non-blocking channel instead.
		if event == EventPostToolUse {
			fmt.Fprintln(options.Stderr, decision.reason)
			if harnessName == HarnessAntigravity {
				return 0
			}
			return 2
		}
		if harnessName == HarnessAntigravity {
			fmt.Fprintln(options.Stderr, decision.reason)
			return 0
		} else {
			writeJSONLine(options, map[string]any{"systemMessage": decision.reason})
		}
		return 0
	}
	if decision.deny && event == EventPostToolUse && harnessName != HarnessAntigravity {
		fmt.Fprintln(options.Stderr, decision.reason)
		return 2
	}
	switch {
	case harnessName == HarnessClaude && (event == EventStop || event == EventSubagentStop):
		fmt.Fprintln(options.Stderr, decision.reason)
		return 2
	case harnessName == HarnessClaude:
		writeJSONLine(options, map[string]any{"hookSpecificOutput": map[string]any{
			"hookEventName": event, "permissionDecision": "deny", "permissionDecisionReason": decision.reason,
		}})
	case harnessName == HarnessCodex && (event == EventStop || event == EventSubagentStop):
		writeJSONLine(options, map[string]any{"continue": false, "reason": decision.reason})
	case harnessName == HarnessCodex:
		writeJSONLine(options, map[string]any{"decision": "block", "reason": decision.reason})
	case event == EventStop || event == EventSubagentStop:
		writeJSONLine(options, map[string]any{"decision": "continue", "reason": decision.reason})
	default:
		writeJSONLine(options, map[string]any{"decision": "deny", "reason": decision.reason})
	}
	return 0
}

func writeJSONLine(options Options, value any) {
	encoded, err := json.Marshal(value)
	if err != nil {
		return
	}
	fmt.Fprintln(options.Stdout, string(encoded))
}
