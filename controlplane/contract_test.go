package controlplane

import (
	"bytes"
	"math"
	"strings"
	"testing"
)

func mustContractJSON(t *testing.T, value any) []byte {
	t.Helper()
	raw, err := EncodeCanonical(value)
	if err != nil {
		t.Fatal(err)
	}
	return raw
}

func malformedContracts() map[string][]byte {
	return map[string][]byte{
		"oversize":  bytes.Repeat([]byte{' '}, MaxContractBytes+1),
		"deep":      []byte(strings.Repeat("[", MaxContractJSONDepth+1) + "0" + strings.Repeat("]", MaxContractJSONDepth+1)),
		"duplicate": []byte(`{"apiVersion":"one","apiVersion":"two"}`),
	}
}

func TestControlplaneDecodersFailClosed(t *testing.T) {
	result, expected := validWorkflowResult(t)
	route := validRouteEnvelope(t)
	selection := validSelectionEnvelope(t)
	decoders := map[string]struct {
		canonical []byte
		decode    func([]byte) error
		traverse  func() []byte
	}{
		"workflow-result": {
			canonical: mustContractJSON(t, result),
			decode:    func(raw []byte) error { _, err := DecodeWorkflowResult(raw, expected); return err },
			traverse: func() []byte {
				bad := result
				bad.ResultID = "result/../escape"
				bad.Digest, _ = digestWithoutField(bad, "digest")
				return mustContractJSON(t, bad)
			},
		},
		"route": {
			canonical: mustContractJSON(t, route),
			decode:    func(raw []byte) error { _, err := DecodeRoute(raw); return err },
			traverse: func() []byte {
				bad := route
				bad.RouteID = "route/../escape"
				bad.Digest, _ = digestWithoutField(bad, "digest")
				return mustContractJSON(t, bad)
			},
		},
		"selection": {
			canonical: mustContractJSON(t, selection),
			decode:    func(raw []byte) error { _, err := DecodeSelection(raw); return err },
			traverse: func() []byte {
				bad := selection
				bad.SelectionID = "selection/../escape"
				bad.Digest, _ = digestWithoutField(bad, "digest")
				return mustContractJSON(t, bad)
			},
		},
	}
	for name, decoder := range decoders {
		t.Run(name+"/canonical", func(t *testing.T) {
			if err := decoder.decode(decoder.canonical); err != nil {
				t.Fatalf("canonical fixture rejected: %v", err)
			}
		})
		for kind, raw := range malformedContracts() {
			t.Run(name+"/"+kind, func(t *testing.T) {
				if err := decoder.decode(raw); err == nil {
					t.Fatal("malformed contract accepted")
				}
			})
		}
		t.Run(name+"/traversal", func(t *testing.T) {
			if err := decoder.decode(decoder.traverse()); err == nil {
				t.Fatal("traversal identifier accepted")
			}
		})
	}
}

func TestLifecycleCoreRecordsSealAndValidate(t *testing.T) {
	goal := GoalRecord{APIVersion: LifecycleAPIVersion, GoalID: "goal-1", RepositoryDigest: testDigest("repo"), CreatedAt: "2026-08-23T20:00:00Z"}
	assignment := AssignmentRecord{APIVersion: LifecycleAPIVersion, AssignmentID: "assignment-1", GoalID: "goal-1", GenerationID: "generation-1", RoleID: "workflow-executor", Lane: "execution", CreatedAt: "2026-08-23T20:00:00Z"}
	dispatch := DispatchRecord{APIVersion: LifecycleAPIVersion, DispatchID: "dispatch-1", ParentDispatchID: "dispatch-root", GoalID: "goal-1", AssignmentID: "assignment-1", GenerationID: "generation-1", RoleID: "workflow-executor", CreatedAt: "2026-08-23T20:00:00Z"}
	if err := SealGoal(&goal); err != nil {
		t.Fatal(err)
	}
	if err := ValidateGoal(goal); err != nil {
		t.Fatal(err)
	}
	if err := SealAssignment(&assignment); err != nil {
		t.Fatal(err)
	}
	if err := ValidateAssignment(assignment); err != nil {
		t.Fatal(err)
	}
	if err := SealDispatch(&dispatch); err != nil {
		t.Fatal(err)
	}
	if err := ValidateDispatch(dispatch); err != nil {
		t.Fatal(err)
	}
	if SealGoal(nil) == nil || SealAssignment(nil) == nil || SealDispatch(nil) == nil {
		t.Fatal("nil lifecycle record accepted")
	}

	badGoal := goal
	badGoal.GoalID = "goal/../escape"
	badGoal.Digest, _ = digestWithoutField(badGoal, "digest")
	if ValidateGoal(badGoal) == nil {
		t.Fatal("goal traversal accepted")
	}
	badAssignment := assignment
	badAssignment.AssignmentID = "/assignment"
	badAssignment.Digest, _ = digestWithoutField(badAssignment, "digest")
	if ValidateAssignment(badAssignment) == nil {
		t.Fatal("absolute assignment accepted")
	}
	badDispatch := dispatch
	badDispatch.ParentDispatchID = badDispatch.DispatchID
	badDispatch.Digest, _ = digestWithoutField(badDispatch, "digest")
	if ValidateDispatch(badDispatch) == nil {
		t.Fatal("self-parented dispatch accepted")
	}
}

func TestCanonicalDigestContract(t *testing.T) {
	left, err := CanonicalDigest([]byte(`{"b":2,"a":1}`))
	if err != nil {
		t.Fatal(err)
	}
	right, err := CanonicalDigest([]byte(`{"a":1,"b":2}`))
	if err != nil {
		t.Fatal(err)
	}
	if left != right {
		t.Fatalf("canonical digests differ: %s != %s", left, right)
	}
	for name, raw := range malformedContracts() {
		t.Run(name, func(t *testing.T) {
			if _, err := CanonicalDigest(raw); err == nil {
				t.Fatal("malformed JSON digested")
			}
		})
	}
	if _, err := CanonicalDigest([]byte(`{"x":1} trailing`)); err == nil {
		t.Fatal("trailing data digested")
	}
	if _, err := CanonicalDigest([]byte{0xff}); err == nil {
		t.Fatal("invalid UTF-8 digested")
	}
}

func TestValidIdentifierRejectsPathTraversal(t *testing.T) {
	for _, value := range []string{"../escape", "role/../escape", "/absolute"} {
		if ValidIdentifier(value) {
			t.Fatalf("ValidIdentifier(%q) = true", value)
		}
	}
	for _, value := range []string{"workflow-executor", "provider/model@max", "role.name:v1"} {
		if !ValidIdentifier(value) {
			t.Fatalf("ValidIdentifier(%q) = false", value)
		}
	}
}

func TestCodecFailClosedCorpus(t *testing.T) {
	for name, raw := range map[string][]byte{
		"empty": {}, "trailing": []byte(`null null`), "bad-syntax": []byte(`{"x":}`),
		"lone-high-surrogate": []byte(`"\uD800"`), "lone-low-surrogate": []byte(`"\uDC00"`),
		"bad-pair": []byte(`"\uD800\u0041"`), "huge-number": []byte(`1e9999`),
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := CanonicalJSON(raw); err == nil {
				t.Fatal("invalid JSON accepted")
			}
		})
	}
	if got, err := CanonicalJSON([]byte(`"\uD83D\uDE00"`)); err != nil || len(got) == 0 {
		t.Fatalf("valid surrogate pair: %q %v", got, err)
	}
	if _, err := EncodeCanonical(nil); err == nil {
		t.Fatal("nil value encoded")
	}
	if _, err := EncodeCanonical(math.NaN()); err == nil {
		t.Fatal("NaN encoded")
	}
	if err := DecodeStrict([]byte(`{}`), nil); err == nil {
		t.Fatal("nil destination accepted")
	}
	var nonPointer map[string]any
	if err := DecodeStrict([]byte(`{}`), nonPointer); err == nil {
		t.Fatal("non-pointer destination accepted")
	}
	var target struct {
		A int `json:"a"`
	}
	if err := DecodeStrict([]byte(`{"unknown":1}`), &target); err == nil {
		t.Fatal("unknown field accepted")
	}
	for _, value := range []string{"", "sha256-short", "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"} {
		if ValidateDigest(value) == nil {
			t.Fatalf("invalid digest %q accepted", value)
		}
	}
	for _, value := range []string{"", "2026-99-99", "0001-01-01T00:00:00Z"} {
		if ValidateTimestamp(value) == nil {
			t.Fatalf("invalid timestamp %q accepted", value)
		}
	}
}
