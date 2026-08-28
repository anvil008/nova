package guard

import (
	"os"
	"os/exec"
	"reflect"
	"testing"
)

func TestRecordTouchedRepositoryProcess(t *testing.T) {
	if os.Getenv("ANVIL_TOUCH_HELPER") != "1" {
		return
	}
	if err := recordTouchedRepositories(os.Getenv("ANVIL_TOUCH_SESSION"), []string{os.Getenv("ANVIL_TOUCH_REPOSITORY")}); err != nil {
		t.Fatal(err)
	}
}

func TestConcurrentTouchLogWritesAreMerged(t *testing.T) {
	state := t.TempDir()
	const session = "concurrent-session"
	commands := make([]*exec.Cmd, 0, 2)
	for _, repository := range []string{"/repository/alpha", "/repository/bravo"} {
		command := exec.Command(os.Args[0], "-test.run=^TestRecordTouchedRepositoryProcess$")
		command.Env = append(os.Environ(), "ANVIL_GUARD_STATE="+state, "ANVIL_TOUCH_HELPER=1", "ANVIL_TOUCH_SESSION="+session, "ANVIL_TOUCH_REPOSITORY="+repository)
		if err := command.Start(); err != nil {
			t.Fatal(err)
		}
		commands = append(commands, command)
	}
	for _, command := range commands {
		if err := command.Wait(); err != nil {
			t.Fatalf("touch helper: %v", err)
		}
	}
	t.Setenv("ANVIL_GUARD_STATE", state)
	if got, want := touchedRepositories(session), []string{"/repository/alpha", "/repository/bravo"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("touched repositories = %v, want %v", got, want)
	}
}
