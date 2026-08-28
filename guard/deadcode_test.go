package guard

import (
	"os/exec"
	"strings"
	"testing"
)

func TestNoDeadCodeInGuardOrControlplane(t *testing.T) {
	tool, err := exec.LookPath("deadcode")
	if err != nil {
		t.Skip("deadcode is not installed")
	}
	command := exec.Command(tool, "-test", "./...")
	command.Dir = ".."
	output, err := command.CombinedOutput()
	if err != nil {
		t.Fatalf("deadcode -test ./...: %v\n%s", err, output)
	}
	for _, line := range strings.Split(string(output), "\n") {
		if strings.Contains(line, "/guard/") || strings.Contains(line, "/controlplane/") {
			t.Fatalf("unreachable guard/controlplane function: %s", line)
		}
	}
}
