package herdrbridge

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
)

type Snapshot struct {
	Version    string      `json:"version"`
	Protocol   int         `json:"protocol"`
	Workspaces []Workspace `json:"workspaces"`
	Tabs       []Tab       `json:"tabs"`
	Panes      []Pane      `json:"panes"`
}

type Workspace struct {
	WorkspaceID string `json:"workspace_id"`
	Label       string `json:"label"`
}

type Tab struct {
	TabID       string `json:"tab_id"`
	WorkspaceID string `json:"workspace_id"`
	Label       string `json:"label"`
}

type Pane struct {
	PaneID      string            `json:"pane_id"`
	WorkspaceID string            `json:"workspace_id"`
	TabID       string            `json:"tab_id"`
	TerminalID  string            `json:"terminal_id"`
	Tokens      map[string]string `json:"tokens"`
}

func (c *Client) Snapshot(ctx context.Context) (Snapshot, error) {
	var result struct {
		Type     string   `json:"type"`
		Snapshot Snapshot `json:"snapshot"`
	}
	if err := c.call(ctx, "session.snapshot", map[string]any{}, &result); err != nil {
		return Snapshot{}, err
	}
	if result.Type != "session_snapshot" || result.Snapshot.Version != SupportedVersion || result.Snapshot.Protocol != SupportedProtocol {
		return Snapshot{}, fmt.Errorf("%w: invalid session snapshot", ErrIncompatible)
	}
	if !snapshotHasWorkspace(result.Snapshot, c.config.WorkspaceID) {
		return Snapshot{}, fmt.Errorf("configured workspace %q: %w", c.config.WorkspaceID, ErrNotFound)
	}
	return result.Snapshot, nil
}

type layoutNode struct {
	Type    string            `json:"type"`
	PaneID  string            `json:"pane_id,omitempty"`
	CWD     string            `json:"cwd,omitempty"`
	Command []string          `json:"command,omitempty"`
	Env     map[string]string `json:"env,omitempty"`
	Label   string            `json:"label,omitempty"`
}

type layoutDescription struct {
	WorkspaceID string     `json:"workspace_id"`
	TabID       string     `json:"tab_id"`
	FocusedPane string     `json:"focused_pane_id"`
	Root        layoutNode `json:"root"`
	Zoomed      bool       `json:"zoomed"`
}

// ApplyLayout creates one new non-focused tab with one root pane. All IDs are
// captured from Herdr's response, then reconciled against a fresh snapshot.
func (c *Client) ApplyLayout(ctx context.Context, spec LayoutSpec) (Locator, error) {
	if err := spec.validate(); err != nil {
		return Locator{}, err
	}
	params := map[string]any{
		"workspace_id": c.config.WorkspaceID,
		"tab_label":    spec.TabLabel,
		"focus":        false,
		"root": layoutNode{
			Type: "pane", CWD: spec.CWD, Command: append([]string(nil), spec.Command...),
			Env: cloneStrings(spec.Env), Label: spec.TabLabel,
		},
	}
	var result struct {
		Type   string            `json:"type"`
		Layout layoutDescription `json:"layout"`
	}
	if err := c.call(ctx, "layout.apply", params, &result); err != nil {
		return Locator{}, err
	}
	if result.Type != "layout_apply" || result.Layout.WorkspaceID != c.config.WorkspaceID || result.Layout.Root.Type != "pane" {
		return Locator{}, errors.New("herdr layout.apply returned an unexpected layout")
	}
	returned := Locator{WorkspaceID: result.Layout.WorkspaceID, TabID: result.Layout.TabID, PaneID: result.Layout.Root.PaneID, JobLabel: spec.TabLabel}
	snapshot, err := c.Snapshot(ctx)
	if err != nil {
		return Locator{}, fmt.Errorf("resolve applied layout: %w", err)
	}
	resolved, err := ResolveLocator(snapshot, returned, Presentation{})
	if err != nil {
		return Locator{}, fmt.Errorf("resolve applied root pane: %w", err)
	}
	if resolved.WorkspaceID != c.config.WorkspaceID || resolved.TabID != returned.TabID {
		return Locator{}, errors.New("applied root pane moved before ownership was established")
	}
	return resolved, nil
}

// ResolveLocator first follows a currently valid opaque pane identity. If that
// identity was invalidated by a move or restart, it uses the safe taskRef and
// attempt tokens as the only deterministic recovery key.
func ResolveLocator(snapshot Snapshot, previous Locator, presentation Presentation) (Locator, error) {
	if previous.PaneID != "" {
		for _, pane := range snapshot.Panes {
			if pane.PaneID == previous.PaneID {
				return locatorFromPane(snapshot, pane, previous.JobLabel), nil
			}
		}
	}
	if previous.TerminalID != "" {
		matches := matchingLocators(snapshot, previous, presentation, func(pane Pane, _ Tab) bool { return pane.TerminalID == previous.TerminalID })
		if len(matches) == 1 {
			return matches[0], nil
		}
		if len(matches) > 1 {
			return Locator{}, ErrAmbiguous
		}
	}
	if previous.JobLabel == "" || presentation.TaskRef == "" || presentation.Attempt == "" {
		return Locator{}, ErrNotFound
	}
	matches := matchingLocators(snapshot, previous, presentation, func(_ Pane, tab Tab) bool { return tab.Label == previous.JobLabel })
	if len(matches) == 0 {
		return Locator{}, ErrNotFound
	}
	if len(matches) != 1 {
		return Locator{}, ErrAmbiguous
	}
	return matches[0], nil
}

func matchingLocators(snapshot Snapshot, previous Locator, presentation Presentation, predicate func(Pane, Tab) bool) []Locator {
	tabs := make(map[string]Tab, len(snapshot.Tabs))
	for _, tab := range snapshot.Tabs {
		tabs[tab.TabID] = tab
	}
	var matches []Locator
	for _, pane := range snapshot.Panes {
		if previous.WorkspaceID != "" && pane.WorkspaceID != previous.WorkspaceID {
			continue
		}
		if presentation.TaskRef != "" && (pane.Tokens["taskRef"] != presentation.TaskRef || pane.Tokens["attempt"] != presentation.Attempt) {
			continue
		}
		tab := tabs[pane.TabID]
		if predicate(pane, tab) {
			matches = append(matches, locatorFromPane(snapshot, pane, tab.Label))
		}
	}
	return matches
}

func locatorFromPane(snapshot Snapshot, pane Pane, fallbackLabel string) Locator {
	label := fallbackLabel
	for _, tab := range snapshot.Tabs {
		if tab.TabID == pane.TabID && tab.Label != "" {
			label = tab.Label
			break
		}
	}
	return Locator{WorkspaceID: pane.WorkspaceID, TabID: pane.TabID, PaneID: pane.PaneID, TerminalID: pane.TerminalID, JobLabel: label}
}

type moveResponse struct {
	Type       string `json:"type"`
	MoveResult struct {
		Changed             bool   `json:"changed"`
		PreviousPaneID      string `json:"previous_pane_id"`
		PreviousWorkspaceID string `json:"previous_workspace_id"`
		PreviousTabID       string `json:"previous_tab_id"`
		Pane                Pane   `json:"pane"`
	} `json:"move_result"`
}

// ResolveMove replaces the entire pre-move locator with Herdr's returned
// canonical pane identity. It never parses or constructs a successor ID.
func ResolveMove(previous Locator, response []byte) (Locator, error) {
	if err := previous.validate(); err != nil {
		return Locator{}, err
	}
	var decoded moveResponse
	if err := json.Unmarshal(response, &decoded); err != nil {
		return Locator{}, fmt.Errorf("decode pane move result: %w", err)
	}
	if decoded.Type != "pane_move" || decoded.MoveResult.PreviousPaneID != previous.PaneID ||
		decoded.MoveResult.PreviousWorkspaceID != previous.WorkspaceID || decoded.MoveResult.PreviousTabID != previous.TabID {
		return Locator{}, errors.New("pane move lineage does not match the owned locator")
	}
	current := Locator{WorkspaceID: decoded.MoveResult.Pane.WorkspaceID, TabID: decoded.MoveResult.Pane.TabID, PaneID: decoded.MoveResult.Pane.PaneID, TerminalID: decoded.MoveResult.Pane.TerminalID, JobLabel: previous.JobLabel}
	if err := current.validate(); err != nil {
		return Locator{}, fmt.Errorf("pane move omitted canonical identity: %w", err)
	}
	return current, nil
}

func snapshotHasWorkspace(snapshot Snapshot, workspaceID string) bool {
	for _, workspace := range snapshot.Workspaces {
		if workspace.WorkspaceID == workspaceID {
			return true
		}
	}
	return false
}

func cloneStrings(input map[string]string) map[string]string {
	if len(input) == 0 {
		return nil
	}
	result := make(map[string]string, len(input))
	for key, value := range input {
		result[key] = value
	}
	return result
}
