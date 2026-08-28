package controlplane

import "testing"

func TestWorkflowResultFailClosedCorpus(t *testing.T) {
	base, expected := validWorkflowResult(t)
	cases := map[string]func(*WorkflowResult){
		"version":                    func(v *WorkflowResult) { v.APIVersion = "wrong" },
		"cycle":                      func(v *WorkflowResult) { v.Cycle = 0 },
		"pass":                       func(v *WorkflowResult) { v.Pass = 3 },
		"digest":                     func(v *WorkflowResult) { v.RouteDigest = "bad" },
		"nil-files":                  func(v *WorkflowResult) { v.Files = nil },
		"path":                       func(v *WorkflowResult) { v.Files = []string{"../escape"} },
		"duplicate-command":          func(v *WorkflowResult) { v.Commands = append(v.Commands, v.Commands[0]) },
		"bad-command-time":           func(v *WorkflowResult) { v.Commands[0].FinishedAt = "2026-08-22T20:00:00Z" },
		"bad-command-digest":         func(v *WorkflowResult) { v.Commands[0].ArgvDigest = "bad" },
		"duplicate-check":            func(v *WorkflowResult) { v.Checks = append(v.Checks, v.Checks[0]) },
		"check-command":              func(v *WorkflowResult) { v.Checks[0].CommandID = "absent" },
		"duplicate-artifact":         func(v *WorkflowResult) { v.Artifacts = append(v.Artifacts, v.Artifacts[0]) },
		"artifact-path":              func(v *WorkflowResult) { v.Artifacts[0].Path = "../escape" },
		"bad-mutation":               func(v *WorkflowResult) { v.Mutations[0].BeforeDigest = "bad" },
		"finished-before-start":      func(v *WorkflowResult) { v.FinishedAt = "2026-08-22T20:00:00Z" },
		"bad-disposition":            func(v *WorkflowResult) { v.Disposition = "invented" },
		"budget-overrun":             func(v *WorkflowResult) { v.BudgetConsumed.Tokens = v.BudgetReserved.Tokens + 1 },
		"missing-specialist-details": func(v *WorkflowResult) { v.Disposition = DispositionMissingSpecialist },
	}
	for name, mutate := range cases {
		t.Run(name, func(t *testing.T) {
			value := base
			value.Files = append([]string(nil), base.Files...)
			value.Commands = append([]CommandEvidence(nil), base.Commands...)
			value.Checks = append([]CheckEvidence(nil), base.Checks...)
			value.Artifacts = append([]ArtifactEvidence(nil), base.Artifacts...)
			value.Mutations = append([]MutationEvidence(nil), base.Mutations...)
			value.Decisions = append([]string(nil), base.Decisions...)
			mutate(&value)
			value.Digest, _ = digestWithoutField(value, "digest")
			if err := ValidateWorkflowResult(value, expected); err == nil {
				t.Fatal("invalid workflow result accepted")
			}
		})
	}
}

func TestRouteFailClosedCorpus(t *testing.T) {
	base := validRouteEnvelope(t)
	cases := map[string]func(*RouteEnvelope){
		"version":         func(v *RouteEnvelope) { v.APIVersion = "wrong" },
		"route-id":        func(v *RouteEnvelope) { v.RouteID = "" },
		"role-digest":     func(v *RouteEnvelope) { v.RoleDigest = "bad" },
		"unavailable":     func(v *RouteEnvelope) { v.OnUnavailable = "guess" },
		"bad-issued":      func(v *RouteEnvelope) { v.IssuedAt = "bad" },
		"bad-expires":     func(v *RouteEnvelope) { v.ExpiresAt = v.IssuedAt },
		"wrong-effective": func(v *RouteEnvelope) { v.EffectiveRoute.Model = "other" },
		"bad-capability":  func(v *RouteEnvelope) { v.Capability.Digest = "bad" },
	}
	for name, mutate := range cases {
		t.Run(name, func(t *testing.T) {
			value := base
			value.OwnershipClaimIDs = append([]string(nil), base.OwnershipClaimIDs...)
			value.Evidence.RequiredChecks = append([]string(nil), base.Evidence.RequiredChecks...)
			value.Evidence.RequiredArtifacts = append([]string(nil), base.Evidence.RequiredArtifacts...)
			mutate(&value)
			value.Digest, _ = digestWithoutField(value, "digest")
			if err := ValidateRoute(value); err == nil {
				t.Fatal("invalid route accepted")
			}
		})
	}
}

func TestSelectionFailClosedCorpus(t *testing.T) {
	base := validSelectionEnvelope(t)
	cases := map[string]func(*SelectionEnvelope){
		"version":            func(v *SelectionEnvelope) { v.APIVersion = "wrong" },
		"id":                 func(v *SelectionEnvelope) { v.SelectionID = "" },
		"nil-lenses":         func(v *SelectionEnvelope) { v.ProposedLenses = nil },
		"duplicate-lens":     func(v *SelectionEnvelope) { v.ProposedLenses = append(v.ProposedLenses, v.ProposedLenses[0]) },
		"bad-lens-kind":      func(v *SelectionEnvelope) { v.ProposedLenses[0].Kind = RoleKindWorkflow },
		"empty-reason":       func(v *SelectionEnvelope) { v.ProposedLenses[0].Reason = "" },
		"duplicate-selected": func(v *SelectionEnvelope) { v.SelectedLeafIDs = append(v.SelectedLeafIDs, v.SelectedLeafIDs[0]) },
		"unknown-selected":   func(v *SelectionEnvelope) { v.SelectedLeafIDs = []string{"toolchain-rust"} },
		"bad-edge":           func(v *SelectionEnvelope) { v.Invocations[0].ParentKind = RoleKindTechnical },
		"bad-digest":         func(v *SelectionEnvelope) { v.CatalogDigest = "bad" },
		"bad-time":           func(v *SelectionEnvelope) { v.IssuedAt = "bad" },
	}
	for name, mutate := range cases {
		t.Run(name, func(t *testing.T) {
			value := base
			value.ProposedLenses = append([]LensProposal(nil), base.ProposedLenses...)
			value.SelectedLeafIDs = append([]string(nil), base.SelectedLeafIDs...)
			value.Invocations = append([]InvocationEdge(nil), base.Invocations...)
			mutate(&value)
			value.Digest, _ = digestWithoutField(value, "digest")
			if err := ValidateSelection(value); err == nil {
				t.Fatal("invalid selection accepted")
			}
		})
	}
}

func TestLifecycleFailClosedCorpus(t *testing.T) {
	generation := GenerationRecord{APIVersion: LifecycleAPIVersion, GoalID: "goal-1", GenerationID: "generation-1", GenerationNumber: 1, RepositoryDigest: testDigest("repo"), CreatedAt: "2026-08-23T20:00:00Z"}
	if err := SealGeneration(&generation); err != nil {
		t.Fatal(err)
	}
	for name, mutate := range map[string]func(*GenerationRecord){
		"version":      func(v *GenerationRecord) { v.APIVersion = "wrong" },
		"number":       func(v *GenerationRecord) { v.GenerationNumber = 0 },
		"first-parent": func(v *GenerationRecord) { v.ParentGenerationID = "generation-0" },
		"digest":       func(v *GenerationRecord) { v.RepositoryDigest = "bad" },
		"time":         func(v *GenerationRecord) { v.CreatedAt = "bad" },
	} {
		t.Run("generation/"+name, func(t *testing.T) {
			value := generation
			mutate(&value)
			value.Digest, _ = digestWithoutField(value, "digest")
			if ValidateGeneration(value) == nil {
				t.Fatal("invalid generation accepted")
			}
		})
	}
	if SealGeneration(nil) == nil {
		t.Fatal("nil generation accepted")
	}
}

func TestVerificationStateFailClosedCorpus(t *testing.T) {
	base := newTestVerification(t)
	cases := map[string]func(*VerificationState){
		"version":         func(v *VerificationState) { v.APIVersion = "wrong" },
		"identity":        func(v *VerificationState) { v.VerificationID = "" },
		"digest":          func(v *VerificationState) { v.InitialResultDigest = "bad" },
		"policy":          func(v *VerificationState) { v.Policy.MaxPasses++ },
		"passes":          func(v *VerificationState) { v.Passes = 3 },
		"nil-events":      func(v *VerificationState) { v.Events = nil },
		"negative-budget": func(v *VerificationState) { v.Budget.Maximum.Tokens = -1 },
		"over-budget":     func(v *VerificationState) { v.Budget.Consumed.Tokens = v.Budget.Maximum.Tokens + 1 },
		"bad-start":       func(v *VerificationState) { v.StartedAt = "bad" },
		"active-outcome":  func(v *VerificationState) { v.Outcome = VerificationAccepted },
		"active-finished": func(v *VerificationState) { v.FinishedAt = v.StartedAt },
		"bad-phase":       func(v *VerificationState) { v.Phase = "invented" },
	}
	for name, mutate := range cases {
		t.Run(name, func(t *testing.T) {
			value := base
			value.Events = append([]VerificationEvent(nil), base.Events...)
			mutate(&value)
			value.Digest, _ = digestWithoutField(value, "digest")
			if ValidateVerification(value) == nil {
				t.Fatal("invalid verification state accepted")
			}
		})
	}
	if SealVerification(nil) == nil {
		t.Fatal("nil verification state accepted")
	}

	terminal := base
	terminal.Phase, terminal.Outcome = VerificationTerminal, VerificationPending
	terminal.Digest, _ = digestWithoutField(terminal, "digest")
	if ValidateVerification(terminal) == nil {
		t.Fatal("terminal pending state accepted")
	}
}

func TestAuthorityFailClosedCorpus(t *testing.T) {
	base := validAuthorityEnvelope(t)
	cases := map[string]func(*AuthorityEnvelope){
		"version":         func(v *AuthorityEnvelope) { v.APIVersion = "wrong" },
		"identity":        func(v *AuthorityEnvelope) { v.GrantID = "" },
		"parent":          func(v *AuthorityEnvelope) { v.ParentGrantID = "/bad" },
		"role-digest":     func(v *AuthorityEnvelope) { v.RoleDigest = "bad" },
		"mode":            func(v *AuthorityEnvelope) { v.CapabilityMode = "invented" },
		"time":            func(v *AuthorityEnvelope) { v.IssuedAt = "bad" },
		"effective":       func(v *AuthorityEnvelope) { v.EffectiveGrant.ToolAllow = []string{"shell"} },
		"spurious-denial": func(v *AuthorityEnvelope) { v.DenialReasons = []string{"none"} },
		"self-digest":     func(v *AuthorityEnvelope) { v.Digest = testDigest("other") },
	}
	for name, mutate := range cases {
		t.Run(name, func(t *testing.T) {
			value := base
			value.EffectiveGrant.ToolAllow = append([]string(nil), base.EffectiveGrant.ToolAllow...)
			value.DenialReasons = append([]string(nil), base.DenialReasons...)
			mutate(&value)
			if name != "self-digest" {
				value.Digest, _ = digestWithoutField(value, "digest")
			}
			if ValidateAuthority(value) == nil {
				t.Fatal("invalid authority accepted")
			}
		})
	}
	if SealAuthority(nil) == nil {
		t.Fatal("nil authority accepted")
	}

	for name, mutate := range map[string]func(*AuthorityGrant){
		"empty":     func(v *AuthorityGrant) { v.ToolAllow = []string{""} },
		"duplicate": func(v *AuthorityGrant) { v.ToolAllow = []string{"read", "read"} },
		"scope":     func(v *AuthorityGrant) { v.FilesystemRead = []string{"../escape"} },
		"budget":    func(v *AuthorityGrant) { v.Budget.MaxTokens = -1 },
	} {
		t.Run("grant/"+name, func(t *testing.T) {
			value := fullTestGrant()
			mutate(&value)
			if _, err := IntersectAuthority(value, fullTestGrant(), fullTestGrant(), fullTestGrant()); err == nil {
				t.Fatal("invalid grant accepted")
			}
		})
	}
}

func TestOwnershipAndCancellationFailClosedCorpus(t *testing.T) {
	claim := OwnershipClaim{APIVersion: LifecycleAPIVersion, ClaimID: "claim-1", GoalID: "goal-1", GenerationID: "generation-1", DispatchID: "dispatch-1", Mode: OwnershipWrite, Paths: []string{"controlplane"}, Symbols: []SymbolClaim{}, IssuedAt: "2026-08-23T20:00:00Z", ExpiresAt: "2026-08-23T21:00:00Z"}
	if err := SealOwnership(&claim); err != nil {
		t.Fatal(err)
	}
	for name, mutate := range map[string]func(*OwnershipClaim){
		"version":   func(v *OwnershipClaim) { v.APIVersion = "wrong" },
		"mode":      func(v *OwnershipClaim) { v.Mode = "invented" },
		"empty":     func(v *OwnershipClaim) { v.Paths, v.Symbols = nil, nil },
		"duplicate": func(v *OwnershipClaim) { v.Paths = []string{"controlplane", "controlplane"} },
		"expires":   func(v *OwnershipClaim) { v.ExpiresAt = v.IssuedAt },
	} {
		t.Run("ownership/"+name, func(t *testing.T) {
			value := claim
			value.Paths = append([]string(nil), claim.Paths...)
			mutate(&value)
			value.Digest, _ = digestWithoutField(value, "digest")
			if ValidateOwnership(value) == nil {
				t.Fatal("invalid ownership accepted")
			}
		})
	}
	if SealOwnership(nil) == nil {
		t.Fatal("nil ownership accepted")
	}

	fence := CancellationFence{APIVersion: LifecycleAPIVersion, FenceID: "fence-1", GoalID: "goal-1", GenerationID: "generation-1", GenerationNumber: 1, State: CancellationRequested, CancelledDispatchIDs: []string{}, LateEventDisposition: "record-only-stale", RequestedAt: "2026-08-23T20:00:00Z"}
	if err := SealCancellation(&fence); err != nil {
		t.Fatal(err)
	}
	for name, mutate := range map[string]func(*CancellationFence){
		"version":        func(v *CancellationFence) { v.APIVersion = "wrong" },
		"generation":     func(v *CancellationFence) { v.GenerationNumber = 0 },
		"counts":         func(v *CancellationFence) { v.ActiveLeaseCount = -1 },
		"late":           func(v *CancellationFence) { v.LateEventDisposition = "drop" },
		"time":           func(v *CancellationFence) { v.RequestedAt = "bad" },
		"undrained-time": func(v *CancellationFence) { v.DrainedAt = v.RequestedAt },
		"state":          func(v *CancellationFence) { v.State = "invented" },
	} {
		t.Run("cancellation/"+name, func(t *testing.T) {
			value := fence
			mutate(&value)
			value.Digest, _ = digestWithoutField(value, "digest")
			if ValidateCancellation(value) == nil {
				t.Fatal("invalid cancellation accepted")
			}
		})
	}
	if SealCancellation(nil) == nil {
		t.Fatal("nil cancellation accepted")
	}
}

func TestBudgetAndSymbolClaimsFailClosedCorpus(t *testing.T) {
	reservation := BudgetReservation{APIVersion: LifecycleAPIVersion, ReservationID: "budget-1", GoalID: "goal-1", GenerationID: "generation-1", DispatchID: "dispatch-1", Reserved: BudgetAmount{Delegates: 1, Writers: 1, Tokens: 100, DurationSeconds: 10}, Active: BudgetAmount{Delegates: 1, Writers: 1, Tokens: 100, DurationSeconds: 10}, UpdatedAt: "2026-08-23T20:00:00Z"}
	if err := SealBudgetReservation(&reservation); err != nil {
		t.Fatal(err)
	}
	ceiling := BudgetLimit{MaxDelegates: 1, MaxWriters: 1, MaxTokens: 100, MaxDurationSeconds: 10}
	if err := ValidateBudgetReservation(reservation, ceiling); err != nil {
		t.Fatal(err)
	}
	for name, mutate := range map[string]func(*BudgetReservation){
		"version":           func(v *BudgetReservation) { v.APIVersion = "wrong" },
		"identity":          func(v *BudgetReservation) { v.ReservationID = "" },
		"negative-reserved": func(v *BudgetReservation) { v.Reserved.Tokens = -1 },
		"negative-part":     func(v *BudgetReservation) { v.Consumed.Tokens = -1 },
		"unknown":           func(v *BudgetReservation) { v.UnknownUsage = true },
		"unbalanced":        func(v *BudgetReservation) { v.Active.Tokens-- },
		"over-ceiling":      func(v *BudgetReservation) { v.Reserved.Tokens++; v.Active.Tokens++ },
		"time":              func(v *BudgetReservation) { v.UpdatedAt = "bad" },
	} {
		t.Run(name, func(t *testing.T) {
			value := reservation
			mutate(&value)
			value.Digest, _ = digestWithoutField(value, "digest")
			if ValidateBudgetReservation(value, ceiling) == nil {
				t.Fatal("invalid reservation accepted")
			}
		})
	}
	if SealBudgetReservation(nil) == nil {
		t.Fatal("nil reservation accepted")
	}

	claim := OwnershipClaim{APIVersion: LifecycleAPIVersion, ClaimID: "claim-symbol", GoalID: "goal-1", GenerationID: "generation-1", DispatchID: "dispatch-1", Mode: OwnershipWrite, Paths: []string{}, Symbols: []SymbolClaim{{Language: "go", Path: "controlplane/result.go", QualifiedName: "WorkflowResult.Validate"}}, IssuedAt: "2026-08-23T20:00:00Z", ExpiresAt: "2026-08-23T21:00:00Z"}
	if err := SealOwnership(&claim); err != nil {
		t.Fatal(err)
	}
	for name, mutate := range map[string]func(*OwnershipClaim){
		"language":  func(v *OwnershipClaim) { v.Symbols[0].Language = "" },
		"path":      func(v *OwnershipClaim) { v.Symbols[0].Path = "../escape" },
		"qualified": func(v *OwnershipClaim) { v.Symbols[0].QualifiedName = "bad name" },
		"duplicate": func(v *OwnershipClaim) { v.Symbols = append(v.Symbols, v.Symbols[0]) },
	} {
		t.Run("symbol/"+name, func(t *testing.T) {
			value := claim
			value.Symbols = append([]SymbolClaim(nil), claim.Symbols...)
			mutate(&value)
			value.Digest, _ = digestWithoutField(value, "digest")
			if ValidateOwnership(value) == nil {
				t.Fatal("invalid symbol claim accepted")
			}
		})
	}
}

func TestVerificationEventFailClosedCorpus(t *testing.T) {
	base, err := ApplyVerification(newTestVerification(t), VerificationObservation{VerifierRoleID: "workflow-code-review", Decision: VerificationAccept, RepositoryDigest: testDigest("repo-1"), EvidenceDigest: testDigest("review"), ResultDigest: testDigest("result"), Reason: "accepted", At: "2026-08-23T20:01:00Z"})
	if err != nil {
		t.Fatal(err)
	}
	cases := map[string]func(*VerificationState){
		"sequence":        func(v *VerificationState) { v.Events[0].Sequence = 2 },
		"reason":          func(v *VerificationState) { v.Events[0].Reason = "" },
		"actor":           func(v *VerificationState) { v.Events[0].ActorRoleID = "" },
		"event-digest":    func(v *VerificationState) { v.Events[0].ResultDigest = "bad" },
		"event-time":      func(v *VerificationState) { v.Events[0].At = "bad" },
		"writer-verifier": func(v *VerificationState) { v.Events[0].ActorRoleID = v.WriterRoleID },
		"decision":        func(v *VerificationState) { v.Events[0].Decision = "invented" },
		"kind":            func(v *VerificationState) { v.Events[0].Kind = "invented" },
		"counter":         func(v *VerificationState) { v.Passes = 0 },
		"finished":        func(v *VerificationState) { v.FinishedAt = "bad" },
	}
	for name, mutate := range cases {
		t.Run(name, func(t *testing.T) {
			value := base
			value.Events = append([]VerificationEvent(nil), base.Events...)
			mutate(&value)
			value.Digest, _ = digestWithoutField(value, "digest")
			if ValidateVerification(value) == nil {
				t.Fatal("invalid event history accepted")
			}
		})
	}
}

func TestResultSymbolsPointersAndArchReview(t *testing.T) {
	result, expected := validWorkflowResult(t)
	result.Symbols = []SymbolClaim{{Language: "go", Path: "controlplane/result.go", QualifiedName: "WorkflowResult.Validate"}}
	result.SpecialistChoices = []SpecialistChoice{{RoleID: "toolchain-go", Action: "selected", Reason: "Go implementation", EvidenceDigest: testDigest("specialist")}}
	result.Findings = []FindingEvidence{{FindingID: "finding-1", Severity: "low", Summary: "minor observation", EvidenceDigest: testDigest("finding")}}
	result.ChildResultDigests = []string{testDigest("child")}
	result.ArchReview = &ArchReview{CheckID: "architecture", CommandID: result.Commands[0].CommandID, Digest: testDigest("arch"), Assertions: 2, Passed: 2, Current: true}
	if err := SealWorkflowResult(&result); err != nil {
		t.Fatal(err)
	}
	if err := ValidateWorkflowResult(result, expected); err != nil {
		t.Fatal(err)
	}
	for name, mutate := range map[string]func(*WorkflowResult){
		"symbol-language":   func(v *WorkflowResult) { v.Symbols[0].Language = "" },
		"symbol-path":       func(v *WorkflowResult) { v.Symbols[0].Path = "../escape" },
		"arch-command":      func(v *WorkflowResult) { v.ArchReview.CommandID = "absent" },
		"arch-digest":       func(v *WorkflowResult) { v.ArchReview.Digest = "bad" },
		"arch-assertions":   func(v *WorkflowResult) { v.ArchReview.Assertions = 0 },
		"arch-passed":       func(v *WorkflowResult) { v.ArchReview.Passed = 3 },
		"finding-severity":  func(v *WorkflowResult) { v.Findings[0].Severity = "invented" },
		"specialist-action": func(v *WorkflowResult) { v.SpecialistChoices[0].Action = "invented" },
		"child-digest":      func(v *WorkflowResult) { v.ChildResultDigests[0] = "bad" },
	} {
		t.Run(name, func(t *testing.T) {
			value := result
			value.Symbols = append([]SymbolClaim(nil), result.Symbols...)
			value.Findings = append([]FindingEvidence(nil), result.Findings...)
			value.SpecialistChoices = append([]SpecialistChoice(nil), result.SpecialistChoices...)
			value.ChildResultDigests = append([]string(nil), result.ChildResultDigests...)
			arch := *result.ArchReview
			value.ArchReview = &arch
			mutate(&value)
			value.Digest, _ = digestWithoutField(value, "digest")
			if ValidateWorkflowResult(value, expected) == nil {
				t.Fatal("invalid evidence accepted")
			}
		})
	}
	discovery := result
	discovery.RoleID, discovery.Lane = "workflow-research", laneDiscovery
	expected.RoleID, expected.Lane = discovery.RoleID, discovery.Lane
	discovery.Mutations, discovery.DiffReview, discovery.ArchReview = []MutationEvidence{}, nil, nil
	discovery.Pointers = []Pointer{{Path: "controlplane/result.go", StartLine: 1, EndLine: 2, Symbol: "WorkflowResult", Why: "contract definition"}}
	if err := SealWorkflowResult(&discovery); err != nil {
		t.Fatal(err)
	}
	for name, mutate := range map[string]func(*Pointer){
		"path":   func(v *Pointer) { v.Path = "../escape" },
		"start":  func(v *Pointer) { v.StartLine = 0 },
		"range":  func(v *Pointer) { v.EndLine = v.StartLine - 1 },
		"symbol": func(v *Pointer) { v.Symbol = "bad symbol" },
		"why":    func(v *Pointer) { v.Why = "" },
	} {
		t.Run("pointer-"+name, func(t *testing.T) {
			value := discovery
			value.Pointers = append([]Pointer(nil), discovery.Pointers...)
			mutate(&value.Pointers[0])
			value.Digest, _ = digestWithoutField(value, "digest")
			if ValidateWorkflowResult(value, expected) == nil {
				t.Fatal("invalid pointer accepted")
			}
		})
	}
}

func TestCapabilityAndRefinementFailClosedCorpus(t *testing.T) {
	capability := testCapability(t)
	for name, mutate := range map[string]func(*CapabilitySnapshot){
		"harness":    func(v *CapabilitySnapshot) { v.HarnessID = "" },
		"nil-routes": func(v *CapabilitySnapshot) { v.Routes = nil },
		"bad-route":  func(v *CapabilitySnapshot) { v.Routes[0].Provider = "" },
		"duplicate":  func(v *CapabilitySnapshot) { v.Routes = append(v.Routes, v.Routes[0]) },
		"observed":   func(v *CapabilitySnapshot) { v.ObservedAt = "bad" },
		"expires":    func(v *CapabilitySnapshot) { v.ExpiresAt = v.ObservedAt },
		"digest":     func(v *CapabilitySnapshot) { v.Digest = "bad" },
	} {
		t.Run(name, func(t *testing.T) {
			value := capability
			value.Routes = append([]ExactRoute(nil), capability.Routes...)
			mutate(&value)
			if name != "digest" {
				value.Digest, _ = digestWithoutField(value, "digest")
			}
			if validateCapabilitySnapshot(value) == nil {
				t.Fatal("invalid capability accepted")
			}
		})
	}
	if SealCapabilitySnapshot(nil) == nil {
		t.Fatal("nil capability accepted")
	}
	duplicate := capability
	duplicate.Routes = append(duplicate.Routes, duplicate.Routes[0])
	if SealCapabilitySnapshot(&duplicate) == nil {
		t.Fatal("duplicate capability sealed")
	}

	for _, action := range []RefinementAction{RefinementAdd, RefinementRemove, RefinementRetain, "invented"} {
		t.Run("refinement-"+string(action), func(t *testing.T) {
			value := validSelectionEnvelope(t)
			roleID := "toolchain-go"
			if action == RefinementAdd {
				roleID = "toolchain-rust"
			}
			value.Refinements = []SelectionRefinement{{ActorRoleID: value.WorkflowOwnerID, RoleID: roleID, Kind: RoleKindTechnical, Action: action, Reason: "evidence-driven refinement", Evidence: []string{testDigest("refinement")}}}
			value.Digest, _ = digestWithoutField(value, "digest")
			err := ValidateSelection(value)
			if action == RefinementAdd || action == RefinementRetain {
				if err != nil {
					t.Fatal(err)
				}
			} else if err == nil {
				t.Fatal("invalid refinement accepted")
			}
		})
	}
}

func TestResolveRouteFailClosedCorpus(t *testing.T) {
	parent := testExactRoute()
	capability := testCapability(t)
	other := parent
	other.Model = "other"
	badParent := parent
	badParent.Provider = ""
	cases := map[string]func() error{
		"bad-time": func() error {
			_, err := ResolveRoute(&parent, parent, RouteInherit, false, "", capability, "bad")
			return err
		},
		"before-observation": func() error {
			_, err := ResolveRoute(&parent, parent, RouteInherit, false, "", capability, "2026-08-23T19:00:00Z")
			return err
		},
		"bad-request": func() error {
			_, err := ResolveRoute(&parent, badParent, RouteInherit, false, "", capability, "2026-08-23T20:00:00Z")
			return err
		},
		"nil-parent": func() error {
			_, err := ResolveRoute(nil, parent, RouteInherit, false, "", capability, "2026-08-23T20:00:00Z")
			return err
		},
		"bad-parent": func() error {
			_, err := ResolveRoute(&badParent, parent, RouteInherit, false, "", capability, "2026-08-23T20:00:00Z")
			return err
		},
		"changed-inherit": func() error {
			_, err := ResolveRoute(&parent, other, RouteInherit, false, "", capability, "2026-08-23T20:00:00Z")
			return err
		},
		"inherit-authority": func() error {
			_, err := ResolveRoute(&parent, parent, RouteInherit, true, "reason", capability, "2026-08-23T20:00:00Z")
			return err
		},
		"nil-refine-parent": func() error {
			_, err := ResolveRoute(nil, parent, RouteRefine, true, "reason", capability, "2026-08-23T20:00:00Z")
			return err
		},
		"refine-without-reason": func() error {
			_, err := ResolveRoute(&parent, parent, RouteRefine, true, "", capability, "2026-08-23T20:00:00Z")
			return err
		},
		"reject": func() error {
			_, err := ResolveRoute(&parent, parent, RouteReject, false, "", capability, "2026-08-23T20:00:00Z")
			return err
		},
		"unknown": func() error {
			_, err := ResolveRoute(&parent, parent, "invented", false, "", capability, "2026-08-23T20:00:00Z")
			return err
		},
	}
	for name, run := range cases {
		t.Run(name, func(t *testing.T) {
			if run() == nil {
				t.Fatal("invalid route resolved")
			}
		})
	}
	if SealRoute(nil) == nil {
		t.Fatal("nil route sealed")
	}
}
