package runplane

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestStateSchemaMigratesV2DisabledJobToV3(t *testing.T) {
	root := t.TempDir()
	if err := os.MkdirAll(filepath.Join(root, "jobs"), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Join(root, "events"), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "state-version.json"), []byte("{\"version\":2}\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	fixture, err := os.ReadFile("testdata/state/v2-disabled.json")
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "jobs", "11111111111111111111111111111111.json"), fixture, 0o600); err != nil {
		t.Fatal(err)
	}
	store, err := newStateStore(root, 10)
	if err != nil {
		t.Fatal(err)
	}
	versionBytes, err := os.ReadFile(filepath.Join(root, "state-version.json"))
	if err != nil {
		t.Fatal(err)
	}
	var version stateVersionRecord
	if err := json.Unmarshal(versionBytes, &version); err != nil {
		t.Fatal(err)
	}
	if version.Version != 3 {
		t.Fatalf("state version = %d, want 3", version.Version)
	}
	jobs, err := store.loadJobs()
	if err != nil {
		t.Fatal(err)
	}
	if jobs["11111111111111111111111111111111"].Visibility != nil {
		t.Fatal("disabled v2 job unexpectedly acquired visibility state")
	}
}

func TestStateSchemaV3PersistsPresentationWithoutLocator(t *testing.T) {
	var job Job
	fixture, err := os.ReadFile("testdata/state/v3-herdr.json")
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(fixture, &job); err != nil {
		t.Fatal(err)
	}
	if job.Visibility == nil || job.Visibility.Sequence != 7 || job.Visibility.Presentation.Attempt != "attempt-1" {
		t.Fatalf("visibility = %#v", job.Visibility)
	}
	encoded, err := json.Marshal(job)
	if err != nil {
		t.Fatal(err)
	}
	for _, forbidden := range []string{"workspaceId", "tabId", "paneId", "terminalId"} {
		if stringContains(encoded, forbidden) {
			t.Fatalf("serialized durable job contains volatile locator field %q: %s", forbidden, encoded)
		}
	}
}

func stringContains(data []byte, wanted string) bool {
	for index := 0; index+len(wanted) <= len(data); index++ {
		if string(data[index:index+len(wanted)]) == wanted {
			return true
		}
	}
	return false
}
