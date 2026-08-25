package herdrbridge

import (
	"context"
	"encoding/json"
	"errors"
	"reflect"
	"testing"
)

func TestLayoutApplyCreatesOneNonFocusedRootPane(t *testing.T) {
	client := scriptedClient(t, []func(wireRequest) any{
		func(request wireRequest) any {
			if request.Method != "layout.apply" {
				t.Fatalf("method = %q", request.Method)
			}
			params := request.Params.(map[string]any)
			if params["workspace_id"] != "opaque-workspace" || params["focus"] != false {
				t.Fatalf("layout params = %#v", params)
			}
			root := params["root"].(map[string]any)
			if root["type"] != "pane" || root["pane_id"] != nil {
				t.Fatalf("root pane was not a single server-identified pane: %#v", root)
			}
			return map[string]any{
				"type": "layout_apply",
				"layout": map[string]any{
					"workspace_id": "opaque-workspace", "tab_id": "opaque-tab", "focused_pane_id": "previous-focus", "zoomed": false,
					"root": map[string]any{"type": "pane", "pane_id": "opaque-pane"},
				},
			}
		},
		func(request wireRequest) any {
			if request.Method != "session.snapshot" {
				t.Fatalf("method = %q", request.Method)
			}
			return snapshotResult([]Pane{{PaneID: "opaque-pane", WorkspaceID: "opaque-workspace", TabID: "opaque-tab", TerminalID: "opaque-terminal"}})
		},
	})
	locator, err := client.ApplyLayout(context.Background(), LayoutSpec{
		TabLabel: "SWM-503 · execution", CWD: "/repo", Command: []string{"/usr/bin/swarm-runplane-child"}, Env: map[string]string{"SAFE": "1"},
	})
	if err != nil {
		t.Fatal(err)
	}
	want := Locator{WorkspaceID: "opaque-workspace", TabID: "opaque-tab", PaneID: "opaque-pane", TerminalID: "opaque-terminal", JobLabel: "job"}
	if !reflect.DeepEqual(locator, want) {
		t.Fatalf("locator = %#v, want %#v", locator, want)
	}
}

func TestResolveLocatorAfterRestartUsesSafeTokens(t *testing.T) {
	snapshot := Snapshot{Tabs: []Tab{{TabID: "new-tab", WorkspaceID: "opaque-workspace", Label: "job-SWM-503-attempt-2"}}, Panes: []Pane{
		{PaneID: "new-pane", WorkspaceID: "opaque-workspace", TabID: "new-tab", Tokens: map[string]string{"taskRef": "SWM-503", "attempt": "2"}},
	}}
	resolved, err := ResolveLocator(snapshot,
		Locator{WorkspaceID: "opaque-workspace", TabID: "old-tab", PaneID: "old-pane", JobLabel: "job-SWM-503-attempt-2"},
		Presentation{TaskRef: "SWM-503", Task: "Show job activity", Phase: "execution", Model: "gpt-5.6-sol", Attempt: "2"},
	)
	if err != nil {
		t.Fatal(err)
	}
	if resolved.PaneID != "new-pane" || resolved.TabID != "new-tab" {
		t.Fatalf("resolved = %#v", resolved)
	}
}

func TestResolveLocatorRejectsAmbiguousRecovery(t *testing.T) {
	snapshot := Snapshot{Tabs: []Tab{{TabID: "t1", WorkspaceID: "opaque-workspace", Label: "job"}, {TabID: "t2", WorkspaceID: "opaque-workspace", Label: "job"}}, Panes: []Pane{
		{PaneID: "p1", WorkspaceID: "opaque-workspace", TabID: "t1", Tokens: map[string]string{"taskRef": "SWM-503", "attempt": "1"}},
		{PaneID: "p2", WorkspaceID: "opaque-workspace", TabID: "t2", Tokens: map[string]string{"taskRef": "SWM-503", "attempt": "1"}},
	}}
	_, err := ResolveLocator(snapshot, Locator{WorkspaceID: "opaque-workspace", JobLabel: "job"}, Presentation{TaskRef: "SWM-503", Task: "Show job activity", Phase: "execution", Model: "gpt-5.6-sol", Attempt: "1"})
	if !errors.Is(err, ErrAmbiguous) {
		t.Fatalf("error = %v, want ambiguous", err)
	}
}

func TestMoveResolutionReplacesOpaquePaneIdentity(t *testing.T) {
	previous := Locator{WorkspaceID: "w-old", TabID: "t-old", PaneID: "p-old"}
	payload, _ := json.Marshal(map[string]any{
		"type": "pane_move",
		"move_result": map[string]any{
			"changed": true, "previous_workspace_id": "w-old", "previous_tab_id": "t-old", "previous_pane_id": "p-old",
			"pane": map[string]any{"workspace_id": "w-new", "tab_id": "t-new", "pane_id": "p-new"},
		},
	})
	current, err := ResolveMove(previous, payload)
	if err != nil {
		t.Fatal(err)
	}
	want := Locator{WorkspaceID: "w-new", TabID: "t-new", PaneID: "p-new"}
	if !reflect.DeepEqual(current, want) {
		t.Fatalf("current = %#v, want %#v", current, want)
	}
}

func TestMoveResolutionRejectsStaleLineage(t *testing.T) {
	previous := Locator{WorkspaceID: "w-old", TabID: "t-old", PaneID: "p-old"}
	payload := []byte(`{"type":"pane_move","move_result":{"previous_workspace_id":"w-old","previous_tab_id":"t-old","previous_pane_id":"someone-else","pane":{"workspace_id":"w-new","tab_id":"t-new","pane_id":"p-new"}}}`)
	if _, err := ResolveMove(previous, payload); err == nil {
		t.Fatal("stale move lineage was accepted")
	}
}

func snapshotResult(panes []Pane) map[string]any {
	return map[string]any{
		"type": "session_snapshot",
		"snapshot": Snapshot{
			Version: SupportedVersion, Protocol: SupportedProtocol,
			Workspaces: []Workspace{{WorkspaceID: "opaque-workspace", Label: "swarm"}},
			Tabs:       []Tab{{TabID: "opaque-tab", WorkspaceID: "opaque-workspace", Label: "job"}}, Panes: panes,
		},
	}
}
