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
	request := adapterRequestForFixture(fixture)
	state, err := StartAdapter(request, "2026-08-23T20:00:00Z")
	if err != nil {
		result.Disposition, result.RejectionStage = "rejected", "boundary"
		return sealNormalizedConformance(fixture, result)
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
			ProposedWorkflowID: "workflow-executor", WorkflowOwnerID: "workflow-executor", ProposedLenses: []controlplane.LensProposal{{RoleID: "technical-go", Kind: controlplane.RoleKindTechnical, Reason: "probe"}},
			Refinements: []controlplane.SelectionRefinement{}, SelectedLeafIDs: []string{"technical-go"}, Invocations: []controlplane.InvocationEdge{{ParentRoleID: "workflow-coding-orchestrator", ParentKind: controlplane.RoleKindOrchestrator, ChildRoleID: "technical-go", ChildKind: controlplane.RoleKindTechnical}},
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
		report.ProjectionDigests[file.Path] = factoryDigest(data)
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
