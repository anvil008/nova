package guard

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

const usageCommands = `<command> [options]

  seal --tests <globs|paths> --red-command <argv...>
  verify --green-command <argv...> [--coverage-command <argv...>] [--min-coverage <float>]
  reseal --reason <text>
  diff-review record --findings <file>
  arch-check --assertions <file>
  hook --harness claude|codex|agy --event PreToolUse|PostToolUse|Stop|SubagentStop
  status [--json]`

func usage() string {
	return "usage: " + filepath.Base(os.Args[0]) + " " + usageCommands
}

// Options carries the process boundary so every command is directly testable.
type Options struct {
	Dir    string
	Stdin  io.Reader
	Stdout io.Writer
	Stderr io.Writer
}

// Run executes one subcommand and returns the process exit code. Code 2 is the
// harness message and refusal channel; 1 is an operational failure.
func Run(options Options, args []string) int {
	if options.Stdout == nil {
		options.Stdout = io.Discard
	}
	if options.Stderr == nil {
		options.Stderr = io.Discard
	}
	if options.Dir == "" {
		options.Dir, _ = os.Getwd()
	}
	if len(args) == 0 {
		fmt.Fprintln(options.Stderr, usage())
		return 1
	}
	if len(args) == 1 && (args[0] == "--help" || args[0] == "-h") {
		fmt.Fprintln(options.Stdout, usage())
		return 0
	}
	code, err := dispatch(options, args)
	if err != nil {
		fmt.Fprintln(options.Stderr, "anvil-guard:", err)
		return 1
	}
	return code
}

func dispatch(options Options, args []string) (int, error) {
	command, rest := args[0], args[1:]
	if command == "hook" {
		flags, err := parseFlags(rest, map[string]bool{"--harness": true, "--event": true})
		if err != nil {
			return 1, err
		}
		harnessName := Harness(flags.values["--harness"])
		switch harnessName {
		case HarnessClaude, HarnessCodex, HarnessAntigravity:
		default:
			return 1, fmt.Errorf("hook requires --harness claude|codex|agy")
		}
		return hook(options, harnessName, flags.values["--event"]), nil
	}

	if command == "seal" {
		flags, err := parseFlags(rest, map[string]bool{"--tests": true, "--red-command": false})
		if err != nil {
			return 1, err
		}
		loaded, err := loadState(options.Dir)
		if err != nil {
			return 1, err
		}
		return 0, seal(loaded, flags.lists["--tests"], flags.argv["--red-command"])
	}

	loaded, err := loadState(options.Dir)
	if err != nil {
		return 1, err
	}
	switch command {
	case "verify":
		flags, err := parseFlags(rest, map[string]bool{"--green-command": false, "--coverage-command": false, "--min-coverage": true})
		if err != nil {
			return 1, err
		}
		minCoverage := 0.0
		if raw, ok := flags.values["--min-coverage"]; ok {
			minCoverage, err = strconv.ParseFloat(raw, 64)
			if err != nil {
				return 1, fmt.Errorf("--min-coverage %q is not a number: %w", raw, err)
			}
		}
		return 0, verify(loaded, flags.argv["--green-command"], flags.argv["--coverage-command"], minCoverage, options.Stderr)
	case "reseal":
		flags, err := parseFlags(rest, map[string]bool{"--reason": true})
		if err != nil {
			return 1, err
		}
		return 0, reseal(loaded, flags.values["--reason"])
	case "diff-review":
		if len(rest) == 0 || rest[0] != "record" {
			return 1, fmt.Errorf("usage: anvil-guard diff-review record --findings <file>")
		}
		flags, err := parseFlags(rest[1:], map[string]bool{"--findings": true})
		if err != nil {
			return 1, err
		}
		return 0, recordDiffReview(loaded, flags.values["--findings"])
	case "arch-check":
		flags, err := parseFlags(rest, map[string]bool{"--assertions": true})
		if err != nil {
			return 1, err
		}
		return archCheck(loaded, flags.values["--assertions"], options.Stderr)
	case "status":
		// Output is machine-readable either way; --json is accepted so callers
		// can name the contract they depend on.
		if len(rest) > 1 || (len(rest) == 1 && rest[0] != "--json") {
			return 1, fmt.Errorf("status takes no arguments beyond --json, got %q", strings.Join(rest, " "))
		}
		report, err := status(loaded)
		if err != nil {
			return 1, err
		}
		encoded, err := json.Marshal(report)
		if err != nil {
			return 1, err
		}
		fmt.Fprintln(options.Stdout, string(encoded))
		return 0, nil
	default:
		fmt.Fprintln(options.Stderr, usage())
		return 1, fmt.Errorf("unknown command %q", command)
	}
}

// parsedFlags separates single-value flags, repeatable whitespace-separated
// lists, and trailing argv arrays. Trailing argv is never re-split or passed
// through a shell.
type parsedFlags struct {
	values map[string]string
	lists  map[string][]string
	argv   map[string][]string
}

// parseFlags reads `--flag value` pairs; a flag declared as non-scalar consumes
// the arguments up to the next known flag as one argv array. Stopping at the
// next known flag rather than at the end is what lets two argv arrays coexist,
// e.g. `verify --green-command <argv...> --coverage-command <argv...>`.
func parseFlags(args []string, scalar map[string]bool) (parsedFlags, error) {
	parsed := parsedFlags{values: map[string]string{}, lists: map[string][]string{}, argv: map[string][]string{}}
	for index := 0; index < len(args); index++ {
		name := args[index]
		isScalar, known := scalar[name]
		if !known {
			return parsed, fmt.Errorf("unexpected argument %q", name)
		}
		if !isScalar {
			end := index + 1
			for end < len(args) {
				if _, isFlag := scalar[args[end]]; isFlag {
					break
				}
				end++
			}
			if end == index+1 {
				return parsed, fmt.Errorf("%s requires an argv array", name)
			}
			parsed.argv[name] = args[index+1 : end]
			index = end - 1
			continue
		}
		if index+1 >= len(args) {
			return parsed, fmt.Errorf("%s requires a value", name)
		}
		value := args[index+1]
		parsed.values[name] = value
		parsed.lists[name] = append(parsed.lists[name], strings.Fields(value)...)
		index++
	}
	return parsed, nil
}

func isAfter(later, earlier string) bool {
	left, leftErr := time.Parse(time.RFC3339Nano, later)
	right, rightErr := time.Parse(time.RFC3339Nano, earlier)
	if leftErr != nil || rightErr != nil {
		return false
	}
	return !left.Before(right)
}
