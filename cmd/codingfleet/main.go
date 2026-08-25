package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/anvil008/swarm-coder/codingfleet"
)

func main() {
	if err := run(os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, "codingfleet:", err)
		os.Exit(1)
	}
}

func run(arguments []string) error {
	if len(arguments) == 0 {
		return fmt.Errorf("usage: codingfleet <render|install> [options]")
	}
	switch arguments[0] {
	case "render":
		return runRender(arguments[1:])
	case "install":
		return runInstall(arguments[1:])
	default:
		return fmt.Errorf("unknown command %q; want render or install", arguments[0])
	}
}

func runRender(arguments []string) error {
	flags := flag.NewFlagSet("render", flag.ContinueOnError)
	rootFlag := flags.String("root", "", "absolute Swarm Coder repository root (default: discover from current directory)")
	check := flags.Bool("check", false, "report generated-output drift without writing")
	if err := flags.Parse(arguments); err != nil {
		return err
	}
	if flags.NArg() != 0 {
		return fmt.Errorf("render accepts no positional arguments")
	}
	root, err := resolveRepositoryRoot(*rootFlag)
	if err != nil {
		return err
	}
	document, err := codingfleet.Load()
	if err != nil {
		return err
	}
	rendered, err := codingfleet.Render(root, document)
	if err != nil {
		return err
	}
	if err := codingfleet.SyncRendered(root, rendered, *check); err != nil {
		return err
	}
	if *check {
		fmt.Printf("coding fleet projections are current (%d roles, %d files)\n", document.Counts.Total, len(rendered.Files))
	} else {
		fmt.Printf("rendered %d roles to %d native files\n", document.Counts.Total, len(rendered.Files))
	}
	return nil
}

func runInstall(arguments []string) error {
	flags := flag.NewFlagSet("install", flag.ContinueOnError)
	rootFlag := flags.String("root", "", "absolute Swarm Coder repository root (default: discover from current directory)")
	homeFlag := flags.String("home", "", "absolute harness home (default: current user home)")
	dryRun := flags.Bool("dry-run", false, "show changes without writing")
	check := flags.Bool("check", false, "verify installed targets without writing")
	uninstall := flags.Bool("uninstall", false, "remove only Anvil Coding Fleet managed state")
	if err := flags.Parse(arguments); err != nil {
		return err
	}
	if flags.NArg() != 0 {
		return fmt.Errorf("install accepts no positional arguments")
	}
	selected := 0
	for _, enabled := range []bool{*dryRun, *check, *uninstall} {
		if enabled {
			selected++
		}
	}
	if selected > 1 {
		return fmt.Errorf("--dry-run, --check, and --uninstall are mutually exclusive")
	}
	root, err := resolveRepositoryRoot(*rootFlag)
	if err != nil {
		return err
	}
	home := *homeFlag
	if home == "" {
		home, err = os.UserHomeDir()
		if err != nil {
			return fmt.Errorf("resolve user home: %w", err)
		}
	}
	if !filepath.IsAbs(home) {
		return fmt.Errorf("home %q must be absolute", home)
	}
	mode := codingfleet.InstallApply
	switch {
	case *dryRun:
		mode = codingfleet.InstallDryRun
	case *check:
		mode = codingfleet.InstallCheck
	case *uninstall:
		mode = codingfleet.InstallUninstall
	}
	result, err := codingfleet.Install(codingfleet.InstallOptions{
		HomeDir:        home,
		RepositoryRoot: root,
		Mode:           mode,
	})
	if err != nil {
		return err
	}
	for _, action := range result.Actions {
		fmt.Println(action)
	}
	if result.VerifiedDigests > 0 {
		fmt.Printf("verified %d installed role digests\n", result.VerifiedDigests)
	}
	return nil
}

func resolveRepositoryRoot(explicit string) (string, error) {
	if explicit != "" {
		if !filepath.IsAbs(explicit) {
			return "", fmt.Errorf("repository root %q must be absolute", explicit)
		}
		return filepath.Clean(explicit), nil
	}
	current, err := os.Getwd()
	if err != nil {
		return "", fmt.Errorf("resolve current directory: %w", err)
	}
	for {
		module, err := os.ReadFile(filepath.Join(current, "go.mod"))
		if err == nil && strings.Contains(string(module), "module github.com/anvil008/swarm-coder") {
			return current, nil
		}
		parent := filepath.Dir(current)
		if parent == current {
			return "", fmt.Errorf("could not discover Swarm Coder repository root")
		}
		current = parent
	}
}
