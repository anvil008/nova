package runplane

import (
	"context"
	"embed"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strings"

	"github.com/anvil008/swarm-coder/codingfleet"
	"github.com/anvil008/swarm-coder/controlplane"
)

const ConformanceAPIVersion = "anvil.adapter-conformance/v1"

type AdapterSeam string

const (
	SeamNative AdapterSeam = "native"
	SeamClaude AdapterSeam = "claude"
	SeamAGY    AdapterSeam = "antigravity"
)

type ConformanceFixture struct {
	APIVersion            string                `json:"apiVersion"`
	Name                  string                `json:"name"`
	Scenario              string                `json:"scenario"`
	InputKinds            []EvaluationInputKind `json:"inputKinds"`
	ExpectedDisposition   string                `json:"expectedDisposition"`
	ExpectedPasses        int                   `json:"expectedPasses"`
	ExpectedRepairs       int                   `json:"expectedRepairs"`
	ExpectedFinalOutputs  int                   `json:"expectedFinalOutputs"`
	ExpectedProcessStarts int                   `json:"expectedProcessStarts"`
	ExpectedMutations     int                   `json:"expectedMutations"`
}

type NormalizedConformance struct {
	Disposition    string `json:"disposition"`
	RejectionStage string `json:"rejectionStage,omitempty"`
	Passes         int    `json:"passes"`
	Repairs        int    `json:"repairs"`
	FinalOutputs   int    `json:"finalOutputs"`
	ProcessStarts  int    `json:"processStarts"`
	Mutations      int    `json:"mutations"`
	EvidenceDigest string `json:"evidenceDigest"`
}

type ConformanceReport struct {
	APIVersion        string                           `json:"apiVersion"`
	Fixtures          int                              `json:"fixtures"`
	Seams             []AdapterSeam                    `json:"seams"`
	ProjectionDigests map[string]string                `json:"projectionDigests"`
	Results           map[string]NormalizedConformance `json:"results"`
}

//go:embed testdata/conformance/*.json
var conformanceFixtures embed.FS

func RunConformanceFixture(fixture ConformanceFixture, seam AdapterSeam) (NormalizedConformance, error) {
	if seam != SeamNative && seam != SeamClaude && seam != SeamAGY {
		return NormalizedConformance{}, fmt.Errorf("unsupported adapter seam %q", seam)
	}
	if fixture.APIVersion != ConformanceAPIVersion || fixture.Name == "" || fixture.InputKinds == nil {
		return NormalizedConformance{}, errors.New("invalid conformance fixture")
	}
	result := NormalizedConformance{}
	if fixture.Scenario == "authority-expansion" || fixture.Scenario == "direct-leaf" || fixture.Scenario == "unavailable-route" {
		if err := runAdmissionRejectionProbe(fixture.Scenario); err == nil {
			return result, fmt.Errorf("scenario %q failed to reject", fixture.Scenario)
		}
		result.Disposition, result.RejectionStage = "rejected", "admission"
		return sealNormalizedConformance(fixture, result)
	}
	if fixture.Scenario == "diff-review-continuity" || fixture.Scenario == "unverified-assurance" || fixture.Scenario == "forged-command-id" || fixture.Scenario == "arch-review-record" {
		disposition, stage, err := runResultContractProbe(fixture.Scenario)
		if err != nil {
			return result, err
		}
		result.Disposition, result.RejectionStage = disposition, stage
		return sealNormalizedConformance(fixture, result)
	}
	request := adapterRequestForFixture(fixture)
	state, err := StartAdapter(request, "2026-08-23T20:00:00Z")
	if err != nil {
		result.Disposition, result.RejectionStage = "rejected", "boundary"
		return sealNormalizedConformance(fixture, result)
	}
	if fixture.Scenario == "sealed-green" || fixture.Scenario == "sealed-test-drift" {
		state, err = AttachAdapterTestSeal(state, conformanceTestSeal(), nil)
		if err != nil {
			return result, err
		}
	}
	switch fixture.Scenario {
	case "valid", "one-final-patch":
		state, err = ApplyAdapterVerification(state, controlplane.VerificationObservation{
			VerifierRoleID: "workflow-code-review", Decision: controlplane.VerificationAccept,
			RepositoryDigest: state.Verification.RepositoryDigest, EvidenceDigest: factoryDigest([]byte(fixture.Name + "-review")), ResultDigest: factoryDigest([]byte(fixture.Name + "-review-result")),
			Reason: "provider-free conformance accepted current proof", At: "2026-08-23T20:01:00Z",
		})
		if err == nil {
			state, err = EmitAdapterFinal(state, "diff --git a/a b/a\n", "verified conformance patch", "2026-08-23T20:02:00Z")
		}
		if err == nil && fixture.Scenario == "one-final-patch" {
			if _, duplicateErr := EmitAdapterFinal(state, "duplicate", "duplicate", "2026-08-23T20:03:00Z"); duplicateErr == nil {
				return result, errors.New("one-final-patch fixture permitted duplicate output")
			}
		}
	case "stale-result":
		_, err = ApplyAdapterVerification(state, controlplane.VerificationObservation{
			VerifierRoleID: "workflow-code-review", Decision: controlplane.VerificationAccept,
			RepositoryDigest: factoryDigest([]byte("stale-repo")), EvidenceDigest: factoryDigest([]byte("proof")), ResultDigest: factoryDigest([]byte("result")), Reason: "stale", At: "2026-08-23T20:01:00Z",
		})
	case "missing-proof":
		_, err = ApplyAdapterVerification(state, controlplane.VerificationObservation{
			VerifierRoleID: "workflow-code-review", Decision: controlplane.VerificationAccept,
			RepositoryDigest: state.Verification.RepositoryDigest, ResultDigest: factoryDigest([]byte("result")), Reason: "missing proof", At: "2026-08-23T20:01:00Z",
		})
	case "sealed-green", "sealed-test-drift":
		observation := conformanceTestObservation()
		if fixture.Scenario == "sealed-test-drift" {
			// The writer moved a sealed test without recording an amendment.
			observation.Tests = []controlplane.TestSealTest{{Path: "guard/guard_test.go", Digest: factoryDigest([]byte("weakened-test"))}}
		}
		state, err = ApplyAdapterVerification(state, controlplane.VerificationObservation{
			VerifierRoleID: "workflow-code-review", Decision: controlplane.VerificationAccept,
			RepositoryDigest: state.Verification.RepositoryDigest, EvidenceDigest: factoryDigest([]byte(fixture.Name + "-review")), ResultDigest: factoryDigest([]byte(fixture.Name + "-review-result")),
			Reason: "sealed tests reconciled against the RED baseline", At: "2026-08-23T20:01:00Z", Tests: observation,
		})
		if err == nil {
			state, err = EmitAdapterFinal(state, "diff --git a/a b/a\n", "sealed conformance patch", "2026-08-23T20:02:00Z")
		}
	case "unverified-non-success":
		state, err = ApplyAdapterVerification(state, controlplane.VerificationObservation{
			VerifierRoleID: "workflow-code-review", Decision: controlplane.VerificationReject,
			RepositoryDigest: state.Verification.RepositoryDigest, EvidenceDigest: factoryDigest([]byte("failure-proof")), ResultDigest: factoryDigest([]byte("failure-result")), Reason: "verification failed", At: "2026-08-23T20:01:00Z",
		})
		if err == nil {
			state, err = EmitAdapterFinal(state, "", "verification did not establish success", "2026-08-23T20:02:00Z")
		}
	default:
		return result, fmt.Errorf("unknown conformance scenario %q", fixture.Scenario)
	}
	if err != nil {
		result.Disposition, result.RejectionStage = "rejected", "verification"
	} else if state.Final != nil {
		result.Disposition = string(state.Final.Disposition)
	}
	result.Passes, result.Repairs, result.FinalOutputs = state.Verification.Passes, state.Verification.Repairs, state.FinalEmissions
	return sealNormalizedConformance(fixture, result)
}

func sealNormalizedConformance(fixture ConformanceFixture, result NormalizedConformance) (NormalizedConformance, error) {
	if result.Disposition != fixture.ExpectedDisposition || result.Passes != fixture.ExpectedPasses || result.Repairs != fixture.ExpectedRepairs || result.FinalOutputs != fixture.ExpectedFinalOutputs || result.ProcessStarts != fixture.ExpectedProcessStarts || result.Mutations != fixture.ExpectedMutations {
		return result, fmt.Errorf("conformance fixture %q got %+v, expected disposition=%s passes=%d repairs=%d outputs=%d starts=%d mutations=%d", fixture.Name, result, fixture.ExpectedDisposition, fixture.ExpectedPasses, fixture.ExpectedRepairs, fixture.ExpectedFinalOutputs, fixture.ExpectedProcessStarts, fixture.ExpectedMutations)
	}
	digestInput := result
	digestInput.EvidenceDigest = ""
	raw, err := json.Marshal(digestInput)
	if err != nil {
		return result, err
	}
	result.EvidenceDigest, err = controlplane.CanonicalDigest(raw)
	return result, err
}

func adapterRequestForFixture(fixture ConformanceFixture) AdapterRequest {
	inputs := make([]EvaluationInput, len(fixture.InputKinds))
	for index, kind := range fixture.InputKinds {
		inputs[index] = EvaluationInput{Kind: kind, Digest: factoryDigest([]byte(fixture.Name + "-" + string(kind)))}
	}
	return AdapterRequest{
		APIVersion: AdapterAPIVersion, AttemptID: "attempt-" + fixture.Name, OuterAttempt: 1,
		GoalID: "goal-conformance", GenerationID: "generation-conformance", AssignmentID: "assignment-conformance", WriterRoleID: "workflow-executor",
		WriterResult: factoryDigest([]byte("writer-result")), RepositoryDigest: factoryDigest([]byte("repository")), EvidenceDigest: factoryDigest([]byte("writer-evidence")), Inputs: inputs,
		Budget: controlplane.VerificationUsage{Tokens: 10_000, DurationSeconds: 600},
	}
}

// conformanceTestSeal is the RED baseline the sealed fixtures reconcile against.
func conformanceTestSeal() controlplane.TestSeal {
	return controlplane.TestSeal{
		SealedAt:     "2026-08-23T20:00:30Z",
		Tests:        []controlplane.TestSealTest{{Path: "guard/guard_test.go", Digest: factoryDigest([]byte("red-test"))}},
		RedCommandID: "command-red",
		Amendments:   []controlplane.TestSealAmendment{},
	}
}

func conformanceTestObservation() *controlplane.TestObservation {
	command := controlplane.CommandEvidence{
		CommandID: "command-green", ArgvDigest: factoryDigest([]byte("green-argv")), ExitCode: 0,
		StartedAt: "2026-08-23T20:00:45Z", FinishedAt: "2026-08-23T20:00:50Z",
		StdoutDigest: factoryDigest([]byte("green-out")), StderrDigest: factoryDigest([]byte("green-err")),
	}
	return &controlplane.TestObservation{
		Tests:   conformanceTestSeal().Tests,
		Green:   controlplane.CheckEvidence{CheckID: "green", CommandID: command.CommandID, Passed: true, Current: true, EvidenceDigest: factoryDigest([]byte("green-proof"))},
		Command: command,
	}
}

// conformanceWorkflowResult is a sealed execution result carrying the diff
// review the assurance lane must certify the same change against.
func conformanceWorkflowResult(lane, diffDigest string, disposition controlplane.WorkflowDisposition, withCommands bool) (controlplane.WorkflowResult, error) {
	command := controlplane.CommandEvidence{
		CommandID: "command-diff", ArgvDigest: factoryDigest([]byte("diff-argv")), ExitCode: 0,
		StartedAt: "2026-08-23T20:00:02Z", FinishedAt: "2026-08-23T20:00:03Z",
		StdoutDigest: factoryDigest([]byte("diff-out")), StderrDigest: factoryDigest([]byte("diff-err")),
	}
	result := controlplane.WorkflowResult{
		APIVersion: controlplane.WorkflowResultAPIVersion, ResultID: "result-conformance", GoalID: "goal-conformance",
		AssignmentID: "assignment-conformance", GenerationID: "generation-conformance", DispatchID: "dispatch-conformance",
		ParentDispatchID: "dispatch-root", Cycle: 1, Pass: 1, RoleID: "workflow-executor", Lane: lane,
		RouteDigest: factoryDigest([]byte("route")), AuthorityDigest: factoryDigest([]byte("authority")),
		SelectionDigest: factoryDigest([]byte("selection")), RoleDigest: factoryDigest([]byte("role")),
		CatalogDigest: factoryDigest([]byte("catalog")), RepositoryBefore: factoryDigest([]byte("repo-before")),
		RepositoryAfter: factoryDigest([]byte("repo-after")), CapabilityDigest: factoryDigest([]byte("capability")),
		SpecialistChoices: []controlplane.SpecialistChoice{}, Files: []string{}, Symbols: []controlplane.SymbolClaim{},
		Mutations: []controlplane.MutationEvidence{}, Commands: []controlplane.CommandEvidence{},
		Checks: []controlplane.CheckEvidence{}, Artifacts: []controlplane.ArtifactEvidence{},
		Findings: []controlplane.FindingEvidence{}, Uncertainty: []string{}, Decisions: []string{"conformance probe"},
		Errors: []string{}, Assumptions: []string{}, MissingEvidence: []string{}, ChildResultDigests: []string{},
		StartedAt: "2026-08-23T20:00:00Z", FinishedAt: "2026-08-23T20:01:00Z", Disposition: disposition,
	}
	if withCommands {
		result.Commands = []controlplane.CommandEvidence{command}
		result.DiffReview = &controlplane.DiffReview{
			CommandID: command.CommandID, DiffDigest: diffDigest, ReviewedAt: "2026-08-23T20:00:04Z",
			Findings: []string{"read the real diff, not the handoff summary"},
		}
	}
	if err := controlplane.SealWorkflowResult(&result); err != nil {
		return controlplane.WorkflowResult{}, err
	}
	return result, nil
}

// runResultContractProbe exercises the §3.3 result contracts that have no
// adapter state machine of their own.
func runResultContractProbe(scenario string) (string, string, error) {
	switch scenario {
	case "diff-review-continuity":
		execution, err := conformanceWorkflowResult("execution", factoryDigest([]byte("the-change")), controlplane.DispositionSucceeded, true)
		if err != nil {
			return "", "", err
		}
		assurance, err := conformanceWorkflowResult("assurance", factoryDigest([]byte("the-change")), controlplane.DispositionSucceeded, true)
		if err != nil {
			return "", "", err
		}
		if err := controlplane.RequireDiffReviewContinuity(execution, assurance); err != nil {
			return "", "", fmt.Errorf("continuity probe rejected a matching review: %w", err)
		}
		other, err := conformanceWorkflowResult("assurance", factoryDigest([]byte("a-different-change")), controlplane.DispositionSucceeded, true)
		if err != nil {
			return "", "", err
		}
		if err := controlplane.RequireDiffReviewContinuity(execution, other); err == nil {
			return "", "", errors.New("continuity probe accepted a review of a different change")
		}
		return "rejected", "diff-review", nil
	case "unverified-assurance":
		expectation := func(result controlplane.WorkflowResult) controlplane.ResultExpectation {
			return controlplane.ResultExpectation{
				GoalID: result.GoalID, AssignmentID: result.AssignmentID, GenerationID: result.GenerationID,
				DispatchID: result.DispatchID, ParentDispatchID: result.ParentDispatchID, RoleID: result.RoleID,
				Lane: result.Lane, RouteDigest: result.RouteDigest, AuthorityDigest: result.AuthorityDigest,
				SelectionDigest: result.SelectionDigest, RoleDigest: result.RoleDigest, CatalogDigest: result.CatalogDigest,
				RepositoryBefore: result.RepositoryBefore, CurrentRepositoryDigest: result.RepositoryAfter,
				CapabilityDigest: result.CapabilityDigest, RequiredChecks: []string{}, RequiredArtifacts: []string{},
			}
		}
		for _, claimed := range []controlplane.WorkflowDisposition{controlplane.DispositionSucceeded, controlplane.DispositionUncertain} {
			result, err := conformanceWorkflowResult("assurance", "", claimed, false)
			if err != nil {
				return "", "", err
			}
			if err := controlplane.ValidateWorkflowResult(result, expectation(result)); err == nil {
				return "", "", fmt.Errorf("assurance result with no executed command carried %q", claimed)
			}
		}
		honest, err := conformanceWorkflowResult("assurance", "", controlplane.DispositionUnverified, false)
		if err != nil {
			return "", "", err
		}
		if err := controlplane.ValidateWorkflowResult(honest, expectation(honest)); err != nil {
			return "", "", fmt.Errorf("unverified assurance result rejected: %w", err)
		}
		return string(controlplane.DispositionUnverified), "", nil
	case "forged-command-id":
		return runForgedCommandIDProbe()
	case "arch-review-record":
		return runArchReviewProbe()
	}
	return "", "", fmt.Errorf("unknown result contract probe %q", scenario)
}

// runForgedCommandIDProbe exercises the amendment that evidence must resolve to
// records anvil-guard produced. The forged id is internally consistent across
// the handoff and the result because one author wrote both; only the guard
// snapshot, produced by a different process, disagrees.
func runForgedCommandIDProbe() (string, string, error) {
	snapshot := &controlplane.GuardSnapshot{
		APIVersion: controlplane.GuardSnapshotAPIVersion, Repository: "/conformance/repository",
		Records: []controlplane.GuardRecord{{
			Kind: controlplane.GuardRecordDiffReview, CommandID: "command-diff",
			Evidence: controlplane.CommandEvidence{
				CommandID: "command-diff", ArgvDigest: factoryDigest([]byte("diff-argv")), ExitCode: 0,
				StartedAt: "2026-08-23T20:00:02Z", FinishedAt: "2026-08-23T20:00:03Z",
				StdoutDigest: factoryDigest([]byte("diff-out")), StderrDigest: factoryDigest([]byte("diff-err")),
			},
		}},
	}
	expectation := func(result controlplane.WorkflowResult) controlplane.ResultExpectation {
		return controlplane.ResultExpectation{
			GoalID: result.GoalID, AssignmentID: result.AssignmentID, GenerationID: result.GenerationID,
			DispatchID: result.DispatchID, ParentDispatchID: result.ParentDispatchID, RoleID: result.RoleID,
			Lane: result.Lane, RouteDigest: result.RouteDigest, AuthorityDigest: result.AuthorityDigest,
			SelectionDigest: result.SelectionDigest, RoleDigest: result.RoleDigest, CatalogDigest: result.CatalogDigest,
			RepositoryBefore: result.RepositoryBefore, CurrentRepositoryDigest: result.RepositoryAfter,
			CapabilityDigest: result.CapabilityDigest, RequiredChecks: []string{}, RequiredArtifacts: []string{},
			Guard: snapshot,
		}
	}
	honest, err := conformanceWorkflowResult("execution", factoryDigest([]byte("the-change")), controlplane.DispositionSucceeded, true)
	if err != nil {
		return "", "", err
	}
	if err := controlplane.ValidateWorkflowResult(honest, expectation(honest)); err != nil {
		return "", "", fmt.Errorf("guard-backed diff review rejected: %w", err)
	}

	forged := honest
	forged.Commands = []controlplane.CommandEvidence{{
		CommandID: "command-fabricated", ArgvDigest: factoryDigest([]byte("diff-argv")), ExitCode: 0,
		StartedAt: "2026-08-23T20:00:02Z", FinishedAt: "2026-08-23T20:00:03Z",
		StdoutDigest: factoryDigest([]byte("diff-out")), StderrDigest: factoryDigest([]byte("diff-err")),
	}}
	review := *honest.DiffReview
	review.CommandID = "command-fabricated"
	forged.DiffReview = &review
	if err := controlplane.SealWorkflowResult(&forged); err != nil {
		return "", "", err
	}
	if err := controlplane.ValidateWorkflowResult(forged, expectation(forged)); err == nil {
		return "", "", errors.New("a commandId no guard record backs was accepted")
	}

	handoff := codingfleet.AgentHandoff{Tests: []codingfleet.AgentHandoffTest{{
		Name: "diff review", Passed: true, CommandID: "command-fabricated",
	}}}
	if err := codingfleet.ReconcileHandoffTests(handoff, forged, snapshot); err == nil {
		return "", "", errors.New("a fabricated handoff commandId was reconciled")
	}
	return "rejected", "guard-record", nil
}

// runArchReviewProbe exercises the executable architecture-conformance amendment
// (CodeSpec RQ3): the structural check a change carries must resolve to an
// arch-review run anvil-guard recorded, not to prose the agent authored. The
// forged id is self-consistent across the result's own text; only the guard
// snapshot, produced by a different process, disagrees.
func runArchReviewProbe() (string, string, error) {
	archCommand := controlplane.CommandEvidence{
		CommandID: "command-arch", ArgvDigest: factoryDigest([]byte("arch-argv")), ExitCode: 0,
		StartedAt: "2026-08-23T20:02:00Z", FinishedAt: "2026-08-23T20:02:05Z",
		StdoutDigest: factoryDigest([]byte("arch-out")), StderrDigest: factoryDigest([]byte("arch-err")),
	}
	snapshot := &controlplane.GuardSnapshot{
		APIVersion: controlplane.GuardSnapshotAPIVersion, Repository: "/conformance/repository",
		Records: []controlplane.GuardRecord{{
			Kind: controlplane.GuardRecordArchReview, CommandID: archCommand.CommandID, Evidence: archCommand,
		}},
	}
	build := func(command controlplane.CommandEvidence) (controlplane.WorkflowResult, error) {
		result := controlplane.WorkflowResult{
			APIVersion: controlplane.WorkflowResultAPIVersion, ResultID: "result-arch", GoalID: "goal-conformance",
			AssignmentID: "assignment-conformance", GenerationID: "generation-conformance", DispatchID: "dispatch-conformance",
			ParentDispatchID: "dispatch-root", Cycle: 1, Pass: 1, RoleID: "workflow-code-review", Lane: "assurance",
			RouteDigest: factoryDigest([]byte("route")), AuthorityDigest: factoryDigest([]byte("authority")),
			SelectionDigest: factoryDigest([]byte("selection")), RoleDigest: factoryDigest([]byte("role")),
			CatalogDigest: factoryDigest([]byte("catalog")), RepositoryBefore: factoryDigest([]byte("repo-before")),
			RepositoryAfter: factoryDigest([]byte("repo-after")), CapabilityDigest: factoryDigest([]byte("capability")),
			SpecialistChoices: []controlplane.SpecialistChoice{}, Files: []string{}, Symbols: []controlplane.SymbolClaim{},
			Mutations: []controlplane.MutationEvidence{}, Commands: []controlplane.CommandEvidence{command},
			ArchReview: &controlplane.ArchReview{
				CheckID: "arch", CommandID: command.CommandID, Digest: factoryDigest([]byte("arch-assertions")),
				Assertions: 2, Passed: 2, Current: true,
			},
			Checks: []controlplane.CheckEvidence{}, Artifacts: []controlplane.ArtifactEvidence{},
			Findings: []controlplane.FindingEvidence{}, Uncertainty: []string{}, Decisions: []string{"structural design conformance"},
			Errors: []string{}, Assumptions: []string{}, MissingEvidence: []string{}, ChildResultDigests: []string{},
			StartedAt: "2026-08-23T20:00:00Z", FinishedAt: "2026-08-23T20:03:00Z", Disposition: controlplane.DispositionSucceeded,
		}
		if err := controlplane.SealWorkflowResult(&result); err != nil {
			return controlplane.WorkflowResult{}, err
		}
		return result, nil
	}
	expectation := func(result controlplane.WorkflowResult) controlplane.ResultExpectation {
		return controlplane.ResultExpectation{
			GoalID: result.GoalID, AssignmentID: result.AssignmentID, GenerationID: result.GenerationID,
			DispatchID: result.DispatchID, ParentDispatchID: result.ParentDispatchID, RoleID: result.RoleID,
			Lane: result.Lane, RouteDigest: result.RouteDigest, AuthorityDigest: result.AuthorityDigest,
			SelectionDigest: result.SelectionDigest, RoleDigest: result.RoleDigest, CatalogDigest: result.CatalogDigest,
			RepositoryBefore: result.RepositoryBefore, CurrentRepositoryDigest: result.RepositoryAfter,
			CapabilityDigest: result.CapabilityDigest, RequiredChecks: []string{}, RequiredArtifacts: []string{},
			Guard: snapshot,
		}
	}
	honest, err := build(archCommand)
	if err != nil {
		return "", "", err
	}
	if err := controlplane.ValidateWorkflowResult(honest, expectation(honest)); err != nil {
		return "", "", fmt.Errorf("guard-backed arch review rejected: %w", err)
	}
	forged, err := build(controlplane.CommandEvidence{
		CommandID: "command-fabricated", ArgvDigest: factoryDigest([]byte("arch-argv")), ExitCode: 0,
		StartedAt: "2026-08-23T20:02:00Z", FinishedAt: "2026-08-23T20:02:05Z",
		StdoutDigest: factoryDigest([]byte("arch-out")), StderrDigest: factoryDigest([]byte("arch-err")),
	})
	if err != nil {
		return "", "", err
	}
	if err := controlplane.ValidateWorkflowResult(forged, expectation(forged)); err == nil {
		return "", "", errors.New("an arch review citing a commandId no guard record backs was accepted")
	}
	return "rejected", "arch-review", nil
}

func runAdmissionRejectionProbe(scenario string) error {
	switch scenario {
	case "authority-expansion":
		grant := controlplane.AuthorityGrant{
			ToolAllow: []string{"read"}, ToolDeny: []string{}, FilesystemRead: []string{"."}, FilesystemWrite: []string{},
			InvocableRoleKinds: []string{}, InvocableRoleIDs: []string{}, Routes: controlplane.RouteConstraint{Providers: []string{"openai"}, Families: []string{"gpt"}, Models: []string{"gpt-5.6-sol"}, Efforts: []string{"max"}},
			Budget: controlplane.BudgetLimit{}, Evidence: controlplane.EvidenceRequirement{RequiredChecks: []string{}, RequiredArtifacts: []string{}},
		}
		requested := grant
		requested.ToolAllow = []string{"read", "write"}
		effective, err := controlplane.IntersectAuthority(grant, grant, requested, grant)
		if err != nil {
			return err
		}
		for _, tool := range effective.ToolAllow {
			if tool == "write" {
				return nil
			}
		}
		return errors.New("authority expansion was denied")
	case "direct-leaf":
		envelope := controlplane.SelectionEnvelope{
			APIVersion: controlplane.SelectionAPIVersion, SelectionID: "selection-conformance", GoalID: "goal-conformance", GenerationID: "generation-conformance", DispatchID: "dispatch-conformance",
			ProposedWorkflowID: "workflow-executor", WorkflowOwnerID: "workflow-executor", ProposedLenses: []controlplane.LensProposal{{RoleID: "toolchain-go", Kind: controlplane.RoleKindTechnical, Reason: "probe"}},
			Refinements: []controlplane.SelectionRefinement{}, SelectedLeafIDs: []string{"toolchain-go"}, Invocations: []controlplane.InvocationEdge{{ParentRoleID: "workflow-coding-orchestrator", ParentKind: controlplane.RoleKindOrchestrator, ChildRoleID: "toolchain-go", ChildKind: controlplane.RoleKindTechnical}},
			CatalogDigest: factoryDigest([]byte("catalog")), RoleDigest: factoryDigest([]byte("role")), IssuedAt: "2026-08-23T20:00:00Z",
		}
		if err := controlplane.SealSelection(&envelope); err != nil {
			return err
		}
		return controlplane.ValidateSelection(envelope)
	case "unavailable-route":
		parent := controlplane.ExactRoute{Provider: "google", Family: "gemini", Model: "gemini-3.7-flash", Effort: "max"}
		capability := controlplane.CapabilitySnapshot{HarnessID: "antigravity", Routes: []controlplane.ExactRoute{parent}, ObservedAt: "2026-08-23T20:00:00Z", ExpiresAt: "2026-08-23T20:05:00Z"}
		if err := controlplane.SealCapabilitySnapshot(&capability); err != nil {
			return err
		}
		unavailable := parent
		unavailable.Model = "gemini-unavailable"
		_, err := controlplane.ResolveRoute(&parent, unavailable, controlplane.RouteRefine, true, "explicit", capability, "2026-08-23T20:01:00Z")
		return err
	default:
		return nil
	}
}

func LoadConformanceFixtures() ([]ConformanceFixture, error) {
	entries, err := fs.Glob(conformanceFixtures, "testdata/conformance/*.json")
	if err != nil {
		return nil, err
	}
	sort.Strings(entries)
	fixtures := make([]ConformanceFixture, 0, len(entries))
	for _, entry := range entries {
		data, err := conformanceFixtures.ReadFile(entry)
		if err != nil {
			return nil, err
		}
		var fixture ConformanceFixture
		decoder := json.NewDecoder(strings.NewReader(string(data)))
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(&fixture); err != nil {
			return nil, fmt.Errorf("decode %s: %w", entry, err)
		}
		fixtures = append(fixtures, fixture)
	}
	return fixtures, nil
}

// RunOfflineConformance validates projections and contract behavior without
// starting a model, benchmark, scorer, or provider process.
func RunOfflineConformance(ctx context.Context, definitionsRoot string) (ConformanceReport, error) {
	_ = ctx
	absolute, err := filepath.Abs(definitionsRoot)
	if err != nil {
		return ConformanceReport{}, err
	}
	repositoryRoot := filepath.Dir(filepath.Dir(absolute))
	document, err := codingfleet.Load()
	if err != nil {
		return ConformanceReport{}, err
	}
	rendered, err := codingfleet.Render(repositoryRoot, document)
	if err != nil {
		return ConformanceReport{}, err
	}
	report := ConformanceReport{APIVersion: ConformanceAPIVersion, Seams: []AdapterSeam{SeamNative, SeamClaude, SeamAGY}, ProjectionDigests: map[string]string{}, Results: map[string]NormalizedConformance{}}
	for _, file := range rendered.Files {
		pathname := filepath.Join(absolute, filepath.FromSlash(file.Path))
		data, err := os.ReadFile(pathname)
		if err != nil {
			return report, fmt.Errorf("read conformance definition %s: %w", file.Path, err)
		}
		if !reflect.DeepEqual(data, file.Content) {
			return report, fmt.Errorf("conformance definition drift: %s", file.Path)
		}
		if !strings.HasPrefix(file.Path, "knowledge/") {
			report.ProjectionDigests[file.Path] = factoryDigest(data)
		}
	}
	fixtures, err := LoadConformanceFixtures()
	if err != nil {
		return report, err
	}
	report.Fixtures = len(fixtures)
	for _, fixture := range fixtures {
		var reference *NormalizedConformance
		for _, seam := range report.Seams {
			result, err := RunConformanceFixture(fixture, seam)
			if err != nil {
				return report, err
			}
			if reference == nil {
				copy := result
				reference = &copy
			} else if !reflect.DeepEqual(*reference, result) {
				return report, fmt.Errorf("fixture %q differs across adapter seams", fixture.Name)
			}
		}
		report.Results[fixture.Name] = *reference
	}
	return report, nil
}
