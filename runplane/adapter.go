package runplane

import (
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"github.com/anvil008/swarm-coder/controlplane"
)

const AdapterAPIVersion = "anvil.one-attempt-adapter/v1"

type EvaluationInputKind string

const (
	InputTask        EvaluationInputKind = "task"
	InputRepository  EvaluationInputKind = "repository"
	InputPublicTests EvaluationInputKind = "public-tests"
	InputToolPolicy  EvaluationInputKind = "tool-policy"

	InputScorerOutput   EvaluationInputKind = "scorer-output"
	InputHiddenTests    EvaluationInputKind = "hidden-tests"
	InputReferencePatch EvaluationInputKind = "reference-patch"
	InputOracle         EvaluationInputKind = "oracle"
	InputPriorSolution  EvaluationInputKind = "prior-solution"
)

type EvaluationInput struct {
	Kind   EvaluationInputKind `json:"kind"`
	Digest string              `json:"digest"`
}

type AdapterRequest struct {
	APIVersion       string                         `json:"apiVersion"`
	AttemptID        string                         `json:"attemptId"`
	OuterAttempt     int                            `json:"outerAttempt"`
	GoalID           string                         `json:"goalId"`
	GenerationID     string                         `json:"generationId"`
	AssignmentID     string                         `json:"assignmentId"`
	WriterRoleID     string                         `json:"writerRoleId"`
	WriterResult     string                         `json:"writerResultDigest"`
	RepositoryDigest string                         `json:"repositoryDigest"`
	EvidenceDigest   string                         `json:"evidenceDigest"`
	Inputs           []EvaluationInput              `json:"inputs"`
	Budget           controlplane.VerificationUsage `json:"budget"`
}

type AdapterFinalOutput struct {
	Disposition  controlplane.WorkflowDisposition `json:"disposition"`
	Patch        string                           `json:"patch,omitempty"`
	PatchDigest  string                           `json:"patchDigest,omitempty"`
	Answer       string                           `json:"answer"`
	AnswerDigest string                           `json:"answerDigest"`
	EmittedAt    string                           `json:"emittedAt"`
}

type AdapterState struct {
	APIVersion     string                         `json:"apiVersion"`
	AttemptID      string                         `json:"attemptId"`
	OuterAttempt   int                            `json:"outerAttempt"`
	BoundaryDigest string                         `json:"boundaryDigest"`
	Verification   controlplane.VerificationState `json:"verification"`
	FinalEmissions int                            `json:"finalEmissions"`
	Final          *AdapterFinalOutput            `json:"final,omitempty"`
}

func StartAdapter(request AdapterRequest, startedAt string) (AdapterState, error) {
	if request.APIVersion != AdapterAPIVersion {
		return AdapterState{}, fmt.Errorf("adapter apiVersion %q", request.APIVersion)
	}
	if request.OuterAttempt != 1 {
		return AdapterState{}, errors.New("one-pass adapter permits exactly one outer attempt")
	}
	for _, identifier := range []string{request.AttemptID, request.GoalID, request.GenerationID, request.AssignmentID, request.WriterRoleID} {
		if err := controlplane.ValidateIdentifier(identifier); err != nil {
			return AdapterState{}, err
		}
	}
	for _, digest := range []string{request.WriterResult, request.RepositoryDigest, request.EvidenceDigest} {
		if err := controlplane.ValidateDigest(digest); err != nil {
			return AdapterState{}, err
		}
	}
	if request.Inputs == nil || len(request.Inputs) == 0 || len(request.Inputs) > 64 {
		return AdapterState{}, errors.New("adapter inputs must be explicit and bounded")
	}
	seen := map[EvaluationInputKind]struct{}{}
	for _, input := range request.Inputs {
		if err := controlplane.ValidateDigest(input.Digest); err != nil {
			return AdapterState{}, err
		}
		switch input.Kind {
		case InputTask, InputRepository, InputPublicTests, InputToolPolicy:
		case InputScorerOutput, InputHiddenTests, InputReferencePatch, InputOracle, InputPriorSolution:
			return AdapterState{}, fmt.Errorf("forbidden evaluation input %q", input.Kind)
		default:
			return AdapterState{}, fmt.Errorf("unknown evaluation input %q", input.Kind)
		}
		if _, duplicate := seen[input.Kind]; duplicate {
			return AdapterState{}, fmt.Errorf("duplicate evaluation input %q", input.Kind)
		}
		seen[input.Kind] = struct{}{}
	}
	if _, ok := seen[InputTask]; !ok {
		return AdapterState{}, errors.New("adapter task input is required")
	}
	if _, ok := seen[InputRepository]; !ok {
		return AdapterState{}, errors.New("adapter repository input is required")
	}
	boundaryJSON, err := json.Marshal(request.Inputs)
	if err != nil {
		return AdapterState{}, err
	}
	boundaryDigest, err := controlplane.CanonicalDigest(boundaryJSON)
	if err != nil {
		return AdapterState{}, err
	}
	verification, err := controlplane.NewVerificationState(
		"verification-"+request.AttemptID, request.GoalID, request.GenerationID, request.AssignmentID,
		request.WriterRoleID, request.WriterResult, request.RepositoryDigest, request.EvidenceDigest, startedAt, request.Budget,
	)
	if err != nil {
		return AdapterState{}, err
	}
	return AdapterState{APIVersion: AdapterAPIVersion, AttemptID: request.AttemptID, OuterAttempt: 1, BoundaryDigest: boundaryDigest, Verification: verification}, nil
}

func ApplyAdapterVerification(state AdapterState, observation controlplane.VerificationObservation) (AdapterState, error) {
	if err := validateAdapterState(state); err != nil {
		return AdapterState{}, err
	}
	if state.FinalEmissions != 0 {
		return AdapterState{}, errors.New("adapter already emitted its final output")
	}
	next, err := controlplane.ApplyVerification(state.Verification, observation)
	if err != nil {
		return AdapterState{}, err
	}
	state.Verification = next
	return state, nil
}

func ApplyAdapterRepair(state AdapterState, observation controlplane.RepairObservation) (AdapterState, error) {
	if err := validateAdapterState(state); err != nil {
		return AdapterState{}, err
	}
	if state.FinalEmissions != 0 {
		return AdapterState{}, errors.New("adapter already emitted its final output")
	}
	next, err := controlplane.ApplyRepair(state.Verification, observation)
	if err != nil {
		return AdapterState{}, err
	}
	state.Verification = next
	return state, nil
}

// EmitAdapterFinal is the sole output edge. Successful output may contain one
// patch; all non-success outcomes must emit no patch and a truthful answer.
func EmitAdapterFinal(state AdapterState, patch, answer, emittedAt string) (AdapterState, error) {
	if err := validateAdapterState(state); err != nil {
		return AdapterState{}, err
	}
	if state.FinalEmissions != 0 || state.Final != nil {
		return AdapterState{}, errors.New("adapter final output has already been emitted")
	}
	if state.Verification.Phase != controlplane.VerificationTerminal {
		return AdapterState{}, errors.New("adapter cannot emit before verification terminates")
	}
	if len(patch) > 2<<20 || len(answer) == 0 || len(answer) > 256<<10 {
		return AdapterState{}, errors.New("adapter final patch or answer is outside bounded size")
	}
	if err := controlplane.ValidateTimestamp(emittedAt); err != nil {
		return AdapterState{}, err
	}
	disposition := adapterDisposition(state.Verification.Outcome)
	if disposition == controlplane.DispositionSucceeded {
		if strings.TrimSpace(patch) == "" {
			return AdapterState{}, errors.New("accepted adapter result requires one final patch")
		}
	} else if patch != "" {
		return AdapterState{}, errors.New("non-success adapter result may not emit a patch")
	}
	output := &AdapterFinalOutput{
		Disposition: disposition, Patch: patch, Answer: answer, AnswerDigest: factoryDigest([]byte(answer)), EmittedAt: emittedAt,
	}
	if patch != "" {
		output.PatchDigest = factoryDigest([]byte(patch))
	}
	state.Final, state.FinalEmissions = output, 1
	return state, validateAdapterState(state)
}

func validateAdapterState(state AdapterState) error {
	if state.APIVersion != AdapterAPIVersion || state.OuterAttempt != 1 {
		return errors.New("invalid one-attempt adapter state")
	}
	if err := controlplane.ValidateIdentifier(state.AttemptID); err != nil {
		return err
	}
	if err := controlplane.ValidateDigest(state.BoundaryDigest); err != nil {
		return err
	}
	if err := controlplane.ValidateVerification(state.Verification); err != nil {
		return err
	}
	if state.FinalEmissions < 0 || state.FinalEmissions > 1 || (state.FinalEmissions == 0) != (state.Final == nil) {
		return errors.New("adapter final emission count is inconsistent")
	}
	if state.Final != nil {
		if state.Verification.Phase != controlplane.VerificationTerminal || state.Final.Disposition != adapterDisposition(state.Verification.Outcome) {
			return errors.New("adapter final disposition does not match terminal verification")
		}
		if err := controlplane.ValidateDigest(state.Final.AnswerDigest); err != nil {
			return err
		}
		if state.Final.Patch != "" {
			if err := controlplane.ValidateDigest(state.Final.PatchDigest); err != nil {
				return err
			}
		}
	}
	return nil
}

func adapterDisposition(outcome controlplane.VerificationOutcome) controlplane.WorkflowDisposition {
	switch outcome {
	case controlplane.VerificationAccepted:
		return controlplane.DispositionSucceeded
	case controlplane.VerificationExhausted:
		return controlplane.DispositionFailed
	case controlplane.VerificationCancelled:
		return controlplane.DispositionCancelled
	case controlplane.VerificationBlocked:
		return controlplane.DispositionBlocked
	case controlplane.VerificationNoProgress:
		return controlplane.DispositionUncertain
	default:
		return controlplane.DispositionUncertain
	}
}

func factoryDigest(data []byte) string {
	raw, _ := json.Marshal(string(data))
	digest, _ := controlplane.CanonicalDigest(raw)
	return digest
}
