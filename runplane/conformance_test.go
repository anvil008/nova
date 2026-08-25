package runplane

import (
	"context"
	"path/filepath"
	"reflect"
	"testing"

	"github.com/anvil008/swarm-coder/codingfleet"
)

func TestConformanceFixturesHaveCrossHarnessParity(t *testing.T) {
	fixtures, err := LoadConformanceFixtures()
	if err != nil {
		t.Fatal(err)
	}
	if len(fixtures) != 9 {
		t.Fatalf("fixtures=%d, want 9", len(fixtures))
	}
	for _, fixture := range fixtures {
		var reference *NormalizedConformance
		for _, seam := range []AdapterSeam{SeamNative, SeamClaude, SeamAGY} {
			result, err := RunConformanceFixture(fixture, seam)
			if err != nil {
				t.Fatalf("%s/%s: %v", fixture.Name, seam, err)
			}
			if result.ProcessStarts != 0 || result.Mutations != 0 {
				t.Fatalf("%s/%s caused starts or mutations: %+v", fixture.Name, seam, result)
			}
			if reference == nil {
				copy := result
				reference = &copy
			} else if !reflect.DeepEqual(*reference, result) {
				t.Fatalf("%s parity: native=%+v %s=%+v", fixture.Name, *reference, seam, result)
			}
		}
	}
}

func TestOfflineConformanceReadsOnlyCurrentDefinitions(t *testing.T) {
	root := t.TempDir()
	document, err := codingfleet.Load()
	if err != nil {
		t.Fatal(err)
	}
	rendered, err := codingfleet.Render(root, document)
	if err != nil {
		t.Fatal(err)
	}
	if err := codingfleet.SyncRendered(root, rendered, false); err != nil {
		t.Fatal(err)
	}
	report, err := RunOfflineConformance(context.Background(), filepath.Join(root, "harness-agents", "rendered"))
	if err != nil {
		t.Fatal(err)
	}
	if report.Fixtures != 9 || len(report.ProjectionDigests) != document.Counts.Total*3 {
		t.Fatalf("report=%+v", report)
	}
}
