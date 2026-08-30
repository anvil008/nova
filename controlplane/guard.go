package controlplane

import (
	"fmt"
	"slices"
	"strings"
)

// GuardSnapshotAPIVersion identifies the `anvil-guard status --json` contract.
const GuardSnapshotAPIVersion = "anvil.guard-snapshot/v1"

// The kinds of run anvil-guard performs and records itself.
const (
	GuardRecordSealRed      = "seal-red"
	GuardRecordSealBaseline = "seal-baseline"
	GuardRecordGreen        = "green"
	GuardRecordDiffReview   = "diff-review"
	GuardRecordArchReview   = "arch-review"
)

// GuardRecord is one command anvil-guard ran and wrote to its state directory.
// It is the only kind of commandId a handoff, seal, or diff review may cite:
// everything else in a result is text the reporting agent authored, so a
// self-consistent fabrication costs nothing to produce.
type GuardRecord struct {
	Kind      string          `json:"kind"`
	CommandID string          `json:"commandId"`
	Evidence  CommandEvidence `json:"evidence"`
}

// GuardSnapshot is the record set for one repository, as printed by
// `anvil-guard status --json` and as read directly off disk by the run-plane
// supervisor after a foreign child exits.
//
// This is resolution, not a trust boundary. Anything running as the same OS
// user can write the state directory, so a deliberate forgery of these records
// is out of scope by design; that residual is what the LXC 135 holdout
// measures. What this removes is the single-author problem for honest agents:
// the handoff and the workflow result are parsed from the same text, so only a
// record produced by a different process can corroborate either.
type GuardSnapshot struct {
	APIVersion string        `json:"apiVersion"`
	Repository string        `json:"repository"`
	Records    []GuardRecord `json:"records"`
}

// Record returns the guard record naming commandID.
func (snapshot *GuardSnapshot) Record(commandID string) (GuardRecord, bool) {
	if snapshot == nil {
		return GuardRecord{}, false
	}
	for _, record := range snapshot.Records {
		if record.CommandID == commandID {
			return record, true
		}
	}
	return GuardRecord{}, false
}

// RequireGuardRecord rejects a commandId anvil-guard never produced, one whose
// recorded kind is not the kind of run the claim is about, or one whose
// recorded exit code contradicts the pass/fail claim.
//
// The kind is not decoration. `diff-review` and `green` both exit 0, so on exit
// code alone the `git diff HEAD` run stands in as proof that the test suite
// passed. Callers therefore name the kinds the claim admits; naming none is
// itself rejected, so the check cannot degrade into an allow-anything.
//
// A nil snapshot means the repository has no guard state and there is nothing
// to resolve against, so the older contracts stand on their own.
func RequireGuardRecord(snapshot *GuardSnapshot, label, commandID string, passed bool, allowedKinds ...string) error {
	if len(allowedKinds) == 0 {
		return fmt.Errorf("%w: %s resolves a guard record without naming the kind of run it claims", ErrInvalidContract, label)
	}
	_, err := resolveGuardRecord(snapshot, label, commandID, passed, allowedKinds)
	return err
}

// RequireGuardEvidence binds an agent-authored CommandEvidence to the guard
// record that shares its commandId. Without it a single honest run backs any
// number of invented named checks: the cited id resolves, and the argv the
// agent claims to have run is never compared with the argv the guard recorded.
// The returned record is authoritative -- callers judge pass/fail from its exit
// code, never from the agent's copy.
func RequireGuardEvidence(snapshot *GuardSnapshot, label string, claimed CommandEvidence, passed bool, allowedKinds ...string) (GuardRecord, error) {
	if len(allowedKinds) == 0 {
		return GuardRecord{}, fmt.Errorf("%w: %s resolves a guard record without naming the kind of run it claims", ErrInvalidContract, label)
	}
	record, err := resolveGuardRecord(snapshot, label, claimed.CommandID, passed, allowedKinds)
	if err != nil || snapshot == nil {
		return record, err
	}
	for _, field := range []struct {
		name           string
		claimed, guard string
	}{
		{"argvDigest", claimed.ArgvDigest, record.Evidence.ArgvDigest},
		{"stdoutDigest", claimed.StdoutDigest, record.Evidence.StdoutDigest},
	} {
		if field.guard != "" && field.claimed != field.guard {
			return GuardRecord{}, fmt.Errorf("%w: %s reports %s %q for command %q but anvil-guard recorded %q",
				ErrInvalidContract, label, field.name, field.claimed, claimed.CommandID, field.guard)
		}
	}
	if claimed.ExitCode != record.Evidence.ExitCode {
		return GuardRecord{}, fmt.Errorf("%w: %s reports exit %d for command %q but anvil-guard recorded exit %d",
			ErrInvalidContract, label, claimed.ExitCode, claimed.CommandID, record.Evidence.ExitCode)
	}
	return record, nil
}

func resolveGuardRecord(snapshot *GuardSnapshot, label, commandID string, passed bool, allowedKinds []string) (GuardRecord, error) {
	if snapshot == nil {
		return GuardRecord{}, nil
	}
	record, known := snapshot.Record(commandID)
	if !known {
		return GuardRecord{}, fmt.Errorf("%w: %s cites command %q that anvil-guard did not produce", ErrInvalidContract, label, commandID)
	}
	if !slices.Contains(allowedKinds, record.Kind) {
		return GuardRecord{}, fmt.Errorf("%w: %s cites command %q, which anvil-guard recorded as a %q run, not %s",
			ErrInvalidContract, label, commandID, record.Kind, strings.Join(allowedKinds, " or "))
	}
	if passed != (record.Evidence.ExitCode == 0) {
		return GuardRecord{}, fmt.Errorf("%w: %s claims passed=%v but the guard record for %q exited %d", ErrInvalidContract, label, passed, commandID, record.Evidence.ExitCode)
	}
	return record, nil
}
