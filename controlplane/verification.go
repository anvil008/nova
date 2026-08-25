package controlplane

import (
	"fmt"
	"time"
)

const VerificationAPIVersion = "anvil.verification/v1"

type VerificationPhase string

const (
	VerificationAwaitingReview VerificationPhase = "awaiting-verification"
	VerificationAwaitingRepair VerificationPhase = "awaiting-repair"
	VerificationTerminal       VerificationPhase = "terminal"
)

type VerificationOutcome string

const (
	VerificationPending    VerificationOutcome = "pending"
	VerificationAccepted   VerificationOutcome = "accepted"
	VerificationExhausted  VerificationOutcome = "exhausted"
	VerificationCancelled  VerificationOutcome = "cancelled"
	VerificationBlocked    VerificationOutcome = "blocked"
	VerificationNoProgress VerificationOutcome = "no-progress"
)

type VerificationDecision string

const (
	VerificationAccept VerificationDecision = "accept"
	VerificationReject VerificationDecision = "reject"
	VerificationCancel VerificationDecision = "cancel"
	VerificationBlock  VerificationDecision = "block"
)

type VerificationPolicy struct {
	MaxPasses  int `json:"maxPasses"`
	MaxRepairs int `json:"maxRepairs"`
}

func DefaultVerificationPolicy() VerificationPolicy {
	return VerificationPolicy{MaxPasses: 2, MaxRepairs: 1}
}

type VerificationUsage struct {
	Tokens          int64 `json:"tokens"`
	DurationSeconds int64 `json:"durationSeconds"`
}

type VerificationBudget struct {
	Maximum  VerificationUsage `json:"maximum"`
	Consumed VerificationUsage `json:"consumed"`
}

type VerificationEvent struct {
	Sequence         int                  `json:"sequence"`
	Kind             string               `json:"kind"`
	ActorRoleID      string               `json:"actorRoleId"`
	Decision         VerificationDecision `json:"decision"`
	RepositoryDigest string               `json:"repositoryDigest"`
	EvidenceDigest   string               `json:"evidenceDigest"`
	ResultDigest     string               `json:"resultDigest"`
	Reason           string               `json:"reason"`
	Repairable       bool                 `json:"repairable"`
	Usage            VerificationUsage    `json:"usage"`
	At               string               `json:"at"`
}

// TestSealTest pins one sealed test file to the content that failed in RED.
type TestSealTest struct {
	Path   string `json:"path"`
	Digest string `json:"digest"`
}

// TestSealAmendment is the explicit, recorded permission to move a sealed
// test. It is the evidence the assurance pass must inspect.
type TestSealAmendment struct {
	At     string         `json:"at"`
	Reason string         `json:"reason"`
	Before []TestSealTest `json:"before"`
	After  []TestSealTest `json:"after"`
}

// TestSeal is the RED baseline a writer committed to before implementing.
type TestSeal struct {
	SealedAt     string              `json:"sealedAt"`
	Tests        []TestSealTest      `json:"tests"`
	RedCommandID string              `json:"redCommandId"`
	Amendments   []TestSealAmendment `json:"amendments"`
}

// CurrentTests returns the digests in force: the original seal, or the most
// recent amendment when the writer explicitly resealed.
func (seal TestSeal) CurrentTests() []TestSealTest {
	if count := len(seal.Amendments); count > 0 {
		return seal.Amendments[count-1].After
	}
	return seal.Tests
}

// TestObservation is what an independent verifier actually saw: the sealed test
// digests on disk plus the green check and the command that produced it.
type TestObservation struct {
	Tests   []TestSealTest
	Green   CheckEvidence
	Command CommandEvidence
	// Guard is the record set anvil-guard produced. When present, the green
	// command must be one of those records rather than an id the verifier
	// simply wrote down.
	Guard *GuardSnapshot
}

type VerificationState struct {
	APIVersion          string              `json:"apiVersion"`
	VerificationID      string              `json:"verificationId"`
	GoalID              string              `json:"goalId"`
	GenerationID        string              `json:"generationId"`
	AssignmentID        string              `json:"assignmentId"`
	WriterRoleID        string              `json:"writerRoleId"`
	InitialResultDigest string              `json:"initialResultDigest"`
	RepositoryDigest    string              `json:"repositoryDigest"`
	EvidenceDigest      string              `json:"evidenceDigest"`
	Policy              VerificationPolicy  `json:"policy"`
	Budget              VerificationBudget  `json:"budget"`
	Passes              int                 `json:"passes"`
	Repairs             int                 `json:"repairs"`
	Phase               VerificationPhase   `json:"phase"`
	Outcome             VerificationOutcome `json:"outcome"`
	Events              []VerificationEvent `json:"events"`
	StartedAt           string              `json:"startedAt"`
	FinishedAt          string              `json:"finishedAt"`
	TestSeal            *TestSeal           `json:"testSeal,omitempty"`
	Digest              string              `json:"digest"`
}

type VerificationObservation struct {
	VerifierRoleID   string
	Decision         VerificationDecision
	RepositoryDigest string
	EvidenceDigest   string
	ResultDigest     string
	Reason           string
	Repairable       bool
	Usage            VerificationUsage
	At               string
	// Tests is required once a TestSeal is attached: the verifier must report
	// the sealed-test digests it observed and the green run it saw.
	Tests *TestObservation
}

type RepairObservation struct {
	WriterRoleID     string
	RepositoryDigest string
	EvidenceDigest   string
	ResultDigest     string
	Reason           string
	Usage            VerificationUsage
	At               string
}

func NewVerificationState(verificationID, goalID, generationID, assignmentID, writerRoleID, resultDigest, repositoryDigest, evidenceDigest, startedAt string, budget VerificationUsage) (VerificationState, error) {
	state := VerificationState{
		APIVersion: VerificationAPIVersion, VerificationID: verificationID, GoalID: goalID,
		GenerationID: generationID, AssignmentID: assignmentID, WriterRoleID: writerRoleID,
		InitialResultDigest: resultDigest, RepositoryDigest: repositoryDigest, EvidenceDigest: evidenceDigest,
		Policy: DefaultVerificationPolicy(), Budget: VerificationBudget{Maximum: budget},
		Phase: VerificationAwaitingReview, Outcome: VerificationPending, Events: []VerificationEvent{}, StartedAt: startedAt,
	}
	if err := SealVerification(&state); err != nil {
		return VerificationState{}, err
	}
	return state, nil
}

// ApplyVerification consumes one independent verification pass. It never
// invokes a model itself; callers may therefore keep both passes internal to a
// one-attempt benchmark adapter.
func ApplyVerification(state VerificationState, observation VerificationObservation) (VerificationState, error) {
	if err := ValidateVerification(state); err != nil {
		return VerificationState{}, err
	}
	if state.Phase != VerificationAwaitingReview || state.Outcome != VerificationPending {
		return VerificationState{}, fmt.Errorf("%w: verification is not awaiting review", ErrInvalidContract)
	}
	if observation.VerifierRoleID == state.WriterRoleID {
		return VerificationState{}, fmt.Errorf("%w: writer cannot self-certify verification", ErrInvalidContract)
	}
	if err := ValidateIdentifier(observation.VerifierRoleID); err != nil {
		return VerificationState{}, err
	}
	if observation.RepositoryDigest != state.RepositoryDigest || observation.EvidenceDigest == "" {
		return VerificationState{}, fmt.Errorf("%w: verifier observed stale repository or omitted evidence", ErrInvalidContract)
	}
	for _, digest := range []string{observation.RepositoryDigest, observation.EvidenceDigest, observation.ResultDigest} {
		if err := ValidateDigest(digest); err != nil {
			return VerificationState{}, err
		}
	}
	if observation.Reason == "" {
		return VerificationState{}, fmt.Errorf("%w: verification decision lacks reason", ErrInvalidContract)
	}
	if err := reconcileTestSeal(state.TestSeal, observation.Tests, observation.Decision); err != nil {
		return VerificationState{}, err
	}
	if err := addVerificationUsage(&state.Budget, observation.Usage); err != nil {
		return VerificationState{}, err
	}
	state.Passes++
	if state.Passes > state.Policy.MaxPasses {
		return VerificationState{}, fmt.Errorf("%w: verification pass budget exhausted", ErrInvalidContract)
	}
	state.EvidenceDigest = observation.EvidenceDigest
	state.Events = append(state.Events, VerificationEvent{
		Sequence: len(state.Events) + 1, Kind: "verification", ActorRoleID: observation.VerifierRoleID,
		Decision: observation.Decision, RepositoryDigest: observation.RepositoryDigest,
		EvidenceDigest: observation.EvidenceDigest, ResultDigest: observation.ResultDigest,
		Reason: observation.Reason, Repairable: observation.Repairable, Usage: observation.Usage, At: observation.At,
	})
	switch observation.Decision {
	case VerificationAccept:
		state.Phase, state.Outcome, state.FinishedAt = VerificationTerminal, VerificationAccepted, observation.At
	case VerificationReject:
		if observation.Repairable && state.Passes < state.Policy.MaxPasses && state.Repairs < state.Policy.MaxRepairs {
			state.Phase = VerificationAwaitingRepair
		} else {
			state.Phase, state.Outcome, state.FinishedAt = VerificationTerminal, VerificationExhausted, observation.At
		}
	case VerificationCancel:
		state.Phase, state.Outcome, state.FinishedAt = VerificationTerminal, VerificationCancelled, observation.At
	case VerificationBlock:
		state.Phase, state.Outcome, state.FinishedAt = VerificationTerminal, VerificationBlocked, observation.At
	default:
		return VerificationState{}, fmt.Errorf("%w: invalid verification decision %q", ErrInvalidContract, observation.Decision)
	}
	if err := SealVerification(&state); err != nil {
		return VerificationState{}, err
	}
	return state, nil
}

// ApplyRepair records the sole optional repair. If neither repository nor
// evidence changes, the loop terminates as no-progress before another review.
func ApplyRepair(state VerificationState, observation RepairObservation) (VerificationState, error) {
	if err := ValidateVerification(state); err != nil {
		return VerificationState{}, err
	}
	if state.Phase != VerificationAwaitingRepair || state.Outcome != VerificationPending {
		return VerificationState{}, fmt.Errorf("%w: verification is not awaiting repair", ErrInvalidContract)
	}
	if observation.WriterRoleID != state.WriterRoleID {
		return VerificationState{}, fmt.Errorf("%w: repair is not owned by the original writer", ErrInvalidContract)
	}
	for _, digest := range []string{observation.RepositoryDigest, observation.EvidenceDigest, observation.ResultDigest} {
		if err := ValidateDigest(digest); err != nil {
			return VerificationState{}, err
		}
	}
	if observation.Reason == "" {
		return VerificationState{}, fmt.Errorf("%w: repair lacks reason", ErrInvalidContract)
	}
	if err := addVerificationUsage(&state.Budget, observation.Usage); err != nil {
		return VerificationState{}, err
	}
	state.Repairs++
	if state.Repairs > state.Policy.MaxRepairs {
		return VerificationState{}, fmt.Errorf("%w: repair budget exhausted", ErrInvalidContract)
	}
	state.Events = append(state.Events, VerificationEvent{
		Sequence: len(state.Events) + 1, Kind: "repair", ActorRoleID: observation.WriterRoleID,
		RepositoryDigest: observation.RepositoryDigest, EvidenceDigest: observation.EvidenceDigest,
		ResultDigest: observation.ResultDigest, Reason: observation.Reason, Usage: observation.Usage, At: observation.At,
	})
	if observation.RepositoryDigest == state.RepositoryDigest && observation.EvidenceDigest == state.EvidenceDigest {
		state.Phase, state.Outcome, state.FinishedAt = VerificationTerminal, VerificationNoProgress, observation.At
	} else {
		state.RepositoryDigest = observation.RepositoryDigest
		state.EvidenceDigest = observation.EvidenceDigest
		state.Phase = VerificationAwaitingReview
	}
	if err := SealVerification(&state); err != nil {
		return VerificationState{}, err
	}
	return state, nil
}

// AttachTestSeal records the RED baseline the writer sealed before
// implementing. Every later verification pass is reconciled against it.
func AttachTestSeal(state VerificationState, seal TestSeal, guard *GuardSnapshot) (VerificationState, error) {
	if err := ValidateVerification(state); err != nil {
		return VerificationState{}, err
	}
	if err := validateTestSeal(seal); err != nil {
		return VerificationState{}, err
	}
	// The red run failed by construction, so the seal is only real if the guard
	// recorded a non-zero exit under that exact id.
	if err := RequireGuardRecord(guard, "test seal red run", seal.RedCommandID, false, GuardRecordSealRed); err != nil {
		return VerificationState{}, err
	}
	state.TestSeal = &seal
	if err := SealVerification(&state); err != nil {
		return VerificationState{}, err
	}
	return state, nil
}

func validateTestSeal(seal TestSeal) error {
	if err := ValidateTimestamp(seal.SealedAt); err != nil {
		return err
	}
	if err := ValidateIdentifier(seal.RedCommandID); err != nil {
		return err
	}
	if len(seal.Tests) == 0 || seal.Amendments == nil {
		return fmt.Errorf("%w: test seal requires sealed tests and an explicit amendment list", ErrInvalidContract)
	}
	groups := [][]TestSealTest{seal.Tests}
	for _, amendment := range seal.Amendments {
		if err := ValidateTimestamp(amendment.At); err != nil {
			return err
		}
		if amendment.Reason == "" {
			return fmt.Errorf("%w: sealed-test amendment lacks a reason", ErrInvalidContract)
		}
		groups = append(groups, amendment.Before, amendment.After)
	}
	for _, group := range groups {
		// A repeated path would collapse in the reconciliation map and let a
		// second, unchecked digest ride along under the same name.
		seen := make(map[string]struct{}, len(group))
		for _, test := range group {
			if !validRelativeScope(test.Path) || test.Path == "." {
				return fmt.Errorf("%w: invalid sealed test path %q", ErrInvalidContract, test.Path)
			}
			if _, duplicate := seen[test.Path]; duplicate {
				return fmt.Errorf("%w: sealed test %q is listed more than once", ErrInvalidContract, test.Path)
			}
			seen[test.Path] = struct{}{}
			if err := ValidateDigest(test.Digest); err != nil {
				return err
			}
		}
	}
	return nil
}

// reconcileTestSeal rejects a verification pass whose observed sealed tests no
// longer match the seal. Drift is only legitimate through a recorded
// amendment, so it is never repairable by another implementation pass. Only an
// acceptance needs green evidence; a rejection, cancellation, or block is
// reporting that the work is not done.
func reconcileTestSeal(seal *TestSeal, observation *TestObservation, decision VerificationDecision) error {
	if seal == nil {
		return nil
	}
	if observation == nil {
		switch decision {
		case VerificationAccept:
			return fmt.Errorf("%w: sealed verification requires observed test digests and green evidence", ErrInvalidContract)
		case VerificationReject:
			// A rejection releases another implementation pass, so the seal has
			// to be reconciled before the writer starts again. Block and cancel
			// are terminal and may honestly report that the verifier could not
			// run anything at all.
			return fmt.Errorf("%w: sealed rejection requires the observed sealed-test digests", ErrInvalidContract)
		}
		return nil
	}
	expected := seal.CurrentTests()
	digests := make(map[string]string, len(expected))
	for _, test := range expected {
		digests[test.Path] = test.Digest
	}
	observed := make(map[string]struct{}, len(observation.Tests))
	for _, test := range observation.Tests {
		sealed, known := digests[test.Path]
		if !known || sealed != test.Digest {
			return fmt.Errorf("%w: sealed test %q changed and no amendment is recorded", ErrInvalidContract, test.Path)
		}
		observed[test.Path] = struct{}{}
	}
	if len(observed) != len(digests) {
		return fmt.Errorf("%w: observed sealed tests differ from the seal and no amendment is recorded", ErrInvalidContract)
	}
	if decision != VerificationAccept {
		return nil
	}
	if !observation.Green.Passed || !observation.Green.Current || observation.Green.CommandID != observation.Command.CommandID {
		return fmt.Errorf("%w: green check must be passing, current, and tied to its command", ErrInvalidContract)
	}
	if observation.Command.ExitCode != 0 {
		return fmt.Errorf("%w: green command exited %d", ErrInvalidContract, observation.Command.ExitCode)
	}
	if _, err := RequireGuardEvidence(observation.Guard, "green run", observation.Command, true, GuardRecordGreen); err != nil {
		return err
	}
	if err := validateCommandEvidence(observation.Command); err != nil {
		return err
	}
	sealedAt, err := time.Parse(time.RFC3339Nano, seal.SealedAt)
	if err != nil {
		return fmt.Errorf("%w: invalid seal timestamp %q", ErrInvalidContract, seal.SealedAt)
	}
	started, err := time.Parse(time.RFC3339Nano, observation.Command.StartedAt)
	if err != nil || started.Before(sealedAt) {
		return fmt.Errorf("%w: no green command evidence postdates the test seal", ErrInvalidContract)
	}
	return nil
}

func SealVerification(state *VerificationState) error {
	if state == nil {
		return fmt.Errorf("%w: nil verification state", ErrInvalidContract)
	}
	state.Digest = ""
	digest, err := digestWithoutField(*state, "digest")
	if err != nil {
		return err
	}
	state.Digest = digest
	return ValidateVerification(*state)
}

func ValidateVerification(state VerificationState) error {
	if state.APIVersion != VerificationAPIVersion {
		return fmt.Errorf("%w: verification apiVersion %q", ErrInvalidContractVer, state.APIVersion)
	}
	for _, value := range []string{state.VerificationID, state.GoalID, state.GenerationID, state.AssignmentID, state.WriterRoleID} {
		if err := ValidateIdentifier(value); err != nil {
			return err
		}
	}
	for _, digest := range []string{state.InitialResultDigest, state.RepositoryDigest, state.EvidenceDigest} {
		if err := ValidateDigest(digest); err != nil {
			return err
		}
	}
	if state.Policy != DefaultVerificationPolicy() {
		return fmt.Errorf("%w: verification policy must be exactly two passes and one repair", ErrInvalidContract)
	}
	if state.Passes < 0 || state.Passes > state.Policy.MaxPasses || state.Repairs < 0 || state.Repairs > state.Policy.MaxRepairs {
		return fmt.Errorf("%w: verification counters exceed policy", ErrInvalidContract)
	}
	if state.Events == nil || len(state.Events) > state.Policy.MaxPasses+state.Policy.MaxRepairs {
		return fmt.Errorf("%w: verification event sequence is missing or unbounded", ErrInvalidContract)
	}
	if err := validateVerificationUsage(state.Budget.Maximum); err != nil {
		return err
	}
	if err := validateVerificationUsage(state.Budget.Consumed); err != nil {
		return err
	}
	if exceedsVerificationUsage(state.Budget.Consumed, state.Budget.Maximum) {
		return fmt.Errorf("%w: verification consumed budget exceeds maximum", ErrInvalidContract)
	}
	verificationEvents, repairEvents := 0, 0
	for index, event := range state.Events {
		if event.Sequence != index+1 || event.Reason == "" {
			return fmt.Errorf("%w: invalid verification event sequence", ErrInvalidContract)
		}
		if err := ValidateIdentifier(event.ActorRoleID); err != nil {
			return err
		}
		for _, digest := range []string{event.RepositoryDigest, event.EvidenceDigest, event.ResultDigest} {
			if err := ValidateDigest(digest); err != nil {
				return err
			}
		}
		if err := ValidateTimestamp(event.At); err != nil {
			return err
		}
		switch event.Kind {
		case "verification":
			verificationEvents++
			if event.ActorRoleID == state.WriterRoleID {
				return fmt.Errorf("%w: writer recorded as independent verifier", ErrInvalidContract)
			}
			switch event.Decision {
			case VerificationAccept, VerificationReject, VerificationCancel, VerificationBlock:
			default:
				return fmt.Errorf("%w: invalid recorded verification decision %q", ErrInvalidContract, event.Decision)
			}
		case "repair":
			repairEvents++
			if event.ActorRoleID != state.WriterRoleID || event.Decision != "" || event.Repairable {
				return fmt.Errorf("%w: invalid recorded repair ownership", ErrInvalidContract)
			}
		default:
			return fmt.Errorf("%w: invalid verification event kind %q", ErrInvalidContract, event.Kind)
		}
	}
	if verificationEvents != state.Passes || repairEvents != state.Repairs {
		return fmt.Errorf("%w: verification counters do not match event history", ErrInvalidContract)
	}
	if err := ValidateTimestamp(state.StartedAt); err != nil {
		return err
	}
	if state.TestSeal != nil {
		if err := validateTestSeal(*state.TestSeal); err != nil {
			return err
		}
	}
	if state.Phase == VerificationTerminal {
		if state.Outcome == VerificationPending || state.FinishedAt == "" {
			return fmt.Errorf("%w: terminal verification lacks outcome or finish time", ErrInvalidContract)
		}
		if err := ValidateTimestamp(state.FinishedAt); err != nil {
			return err
		}
	} else {
		if state.Outcome != VerificationPending || state.FinishedAt != "" {
			return fmt.Errorf("%w: active verification has terminal state", ErrInvalidContract)
		}
		if state.Phase != VerificationAwaitingReview && state.Phase != VerificationAwaitingRepair {
			return fmt.Errorf("%w: invalid active verification phase %q", ErrInvalidContract, state.Phase)
		}
	}
	return validateSelfDigest(state, state.Digest)
}

func addVerificationUsage(budget *VerificationBudget, usage VerificationUsage) error {
	if err := validateVerificationUsage(usage); err != nil {
		return err
	}
	next := VerificationUsage{Tokens: budget.Consumed.Tokens + usage.Tokens, DurationSeconds: budget.Consumed.DurationSeconds + usage.DurationSeconds}
	if exceedsVerificationUsage(next, budget.Maximum) {
		return fmt.Errorf("%w: verification budget exhausted", ErrInvalidContract)
	}
	budget.Consumed = next
	return nil
}

func validateVerificationUsage(usage VerificationUsage) error {
	if usage.Tokens < 0 || usage.DurationSeconds < 0 {
		return fmt.Errorf("%w: verification usage cannot be negative", ErrInvalidContract)
	}
	return nil
}

func exceedsVerificationUsage(value, ceiling VerificationUsage) bool {
	return value.Tokens > ceiling.Tokens || value.DurationSeconds > ceiling.DurationSeconds
}
