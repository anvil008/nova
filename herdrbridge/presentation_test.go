package herdrbridge

import (
	"context"
	"errors"
	"reflect"
	"strconv"
	"strings"
	"testing"
	"time"
)

func TestMetadataUsesOnlySafeDeterministicFields(t *testing.T) {
	client, err := New(testConfig())
	if err != nil {
		t.Fatal(err)
	}
	var got []string
	client.run = func(_ context.Context, args []string) ([]byte, []byte, error) {
		got = append([]string(nil), args...)
		return []byte(`{"id":"cli","result":{"type":"ok"}}`), nil, nil
	}
	err = client.ReportMetadata(context.Background(),
		Locator{WorkspaceID: "opaque-workspace", TabID: "tab", PaneID: "pane"},
		MetadataUpdate{Presentation: Presentation{
			TaskRef: "SWM-503", Task: "Show job activity", Phase: "execution", Summary: "running focused tests", Model: "gpt-5.6-sol", Attempt: "attempt-2",
		}, Sequence: 19, TTL: ActiveTTL},
	)
	if err != nil {
		t.Fatal(err)
	}
	want := []string{
		"pane", "report-metadata", "pane", "--source", MetadataSource,
		"--title", "SWM-503 · Show job activity", "--display-agent", "gpt-5.6-sol",
		"--token", "attempt=attempt-2", "--token", "model=gpt-5.6-sol", "--token", "phase=execution",
		"--token", "summary=running focused tests", "--token", "task=Show job activity", "--token", "taskRef=SWM-503",
		"--seq", "19", "--ttl-ms", "600000",
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("argv\n got: %#v\nwant: %#v", got, want)
	}
	joined := strings.Join(got, " ")
	for _, forbidden := range []string{"report-agent", "brief", "bearer", "claimNonce", "providerInput"} {
		if strings.Contains(joined, forbidden) {
			t.Fatalf("metadata argv contains forbidden field %q: %s", forbidden, joined)
		}
	}
}

func TestMetadataDoesNotFakeAgentLifecycle(t *testing.T) {
	client, err := New(testConfig())
	if err != nil {
		t.Fatal(err)
	}
	calls := 0
	client.run = func(_ context.Context, args []string) ([]byte, []byte, error) {
		calls++
		if len(args) < 2 || args[0] != "pane" || args[1] != "report-metadata" {
			t.Fatalf("presentation invoked lifecycle operation: %#v", args)
		}
		return []byte(`{"result":{"type":"ok"}}`), nil, nil
	}
	err = client.ReportMetadata(context.Background(), Locator{WorkspaceID: "opaque-workspace", TabID: "t", PaneID: "p"}, MetadataUpdate{Presentation: validPresentation(), Sequence: 1})
	if err != nil || calls != 1 {
		t.Fatalf("ReportMetadata calls=%d err=%v", calls, err)
	}
	if err := client.ReportAgent(context.Background(), Locator{WorkspaceID: "opaque-workspace", TabID: "t", PaneID: "p"}, LifecycleReport{
		Agent: "codex", State: AgentWorking, Sequence: 1,
	}); err == nil {
		t.Fatal("agent lifecycle was reported without authoritative evidence")
	}
}

func TestClientLifecycleUsesOneAuthorityAndNoProviderMessage(t *testing.T) {
	client, _ := New(testConfig())
	var calls [][]string
	client.run = func(_ context.Context, args []string) ([]byte, []byte, error) {
		calls = append(calls, append([]string(nil), args...))
		return []byte(`{"result":{"type":"ok"}}`), nil, nil
	}
	locator := Locator{WorkspaceID: "opaque-workspace", TabID: "t", PaneID: "p"}
	if err := client.ReportAgent(context.Background(), locator, LifecycleReport{Agent: "codex", State: AgentWorking, Sequence: 7, Authoritative: true}); err != nil {
		t.Fatal(err)
	}
	if err := client.ReleaseAgent(context.Background(), locator, "codex", 8); err != nil {
		t.Fatal(err)
	}
	want := [][]string{
		{"pane", "report-agent", "p", "--source", LifecycleSource, "--agent", "codex", "--state", "working", "--seq", "7"},
		{"pane", "release-agent", "p", "--source", LifecycleSource, "--agent", "codex", "--seq", "8"},
	}
	if !reflect.DeepEqual(calls, want) {
		t.Fatalf("lifecycle argv = %#v, want %#v", calls, want)
	}
}

func TestClientBlockedAndUnknownRemainNonTerminalStates(t *testing.T) {
	client, _ := New(testConfig())
	var states []string
	client.run = func(_ context.Context, args []string) ([]byte, []byte, error) {
		for index := range args {
			if args[index] == "--state" {
				states = append(states, args[index+1])
			}
		}
		return []byte(`{"result":{"type":"ok"}}`), nil, nil
	}
	locator := Locator{WorkspaceID: "opaque-workspace", TabID: "t", PaneID: "p"}
	for sequence, state := range []AgentState{AgentBlocked, AgentUnknown} {
		if err := client.ReportAgent(context.Background(), locator, LifecycleReport{Agent: "codex", State: state, Sequence: uint64(sequence + 1), Authoritative: true}); err != nil {
			t.Fatal(err)
		}
	}
	if !reflect.DeepEqual(states, []string{"blocked", "unknown"}) {
		t.Fatalf("reported states = %#v", states)
	}
}

func TestClientHandoffReleasesThenReportsUnknown(t *testing.T) {
	client, _ := New(testConfig())
	var calls [][]string
	client.run = func(_ context.Context, args []string) ([]byte, []byte, error) {
		calls = append(calls, append([]string(nil), args...))
		return []byte(`{"result":{"type":"ok"}}`), nil, nil
	}
	locator := Locator{WorkspaceID: "opaque-workspace", TabID: "t", PaneID: "p"}
	if err := client.HandoffAgent(context.Background(), locator, "codex", "claude", 11, 12, true); err != nil {
		t.Fatal(err)
	}
	if len(calls) != 2 || calls[0][1] != "release-agent" || calls[1][1] != "report-agent" || !strings.Contains(strings.Join(calls[1], " "), "--state unknown") {
		t.Fatalf("handoff calls = %#v", calls)
	}
	if err := client.HandoffAgent(context.Background(), locator, "codex", "claude", 11, 12, false); err == nil {
		t.Fatal("unauthoritative handoff was accepted")
	}
}

func TestSequenceOrderIsDeterministic(t *testing.T) {
	presentation := validPresentation()
	ordered, err := SequenceOrder([]MetadataUpdate{{Presentation: presentation, Sequence: 3}, {Presentation: presentation, Sequence: 1}, {Presentation: presentation, Sequence: 2}})
	if err != nil {
		t.Fatal(err)
	}
	for index, sequence := range []uint64{1, 2, 3} {
		if ordered[index].Sequence != sequence {
			t.Fatalf("ordered[%d] = %d", index, ordered[index].Sequence)
		}
	}
	if _, err := SequenceOrder([]MetadataUpdate{{Presentation: presentation, Sequence: 1}, {Presentation: presentation, Sequence: 1}}); err == nil {
		t.Fatal("duplicate sequence was accepted")
	}
}

func TestSequenceReplayIsAscendingAndMetadataOnly(t *testing.T) {
	client, _ := New(testConfig())
	var sequences []string
	client.run = func(_ context.Context, args []string) ([]byte, []byte, error) {
		if args[1] != "report-metadata" {
			t.Fatalf("replay invoked lifecycle command: %#v", args)
		}
		for index := range args {
			if args[index] == "--seq" {
				sequences = append(sequences, args[index+1])
			}
		}
		return []byte(`{"result":{"type":"ok"}}`), nil, nil
	}
	presentation := validPresentation()
	updates := []MetadataUpdate{{Presentation: presentation, Sequence: 9}, {Presentation: presentation, Sequence: 7}, {Presentation: presentation, Sequence: 8}}
	if err := client.ReplayMetadata(context.Background(), Locator{WorkspaceID: "opaque-workspace", TabID: "t", PaneID: "p"}, updates); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(sequences, []string{"7", "8", "9"}) {
		t.Fatalf("replay sequences = %#v", sequences)
	}
}

func TestTTLBoundsAndDefault(t *testing.T) {
	milliseconds, err := ttlMilliseconds(0)
	if err != nil || milliseconds != uint64(DefaultTTL.Milliseconds()) {
		t.Fatalf("default TTL = %d err=%v", milliseconds, err)
	}
	for _, invalid := range []time.Duration{time.Nanosecond, MaxTTL + time.Millisecond} {
		if _, err := ttlMilliseconds(invalid); err == nil {
			t.Fatalf("TTL %s was accepted", invalid)
		}
	}
	if milliseconds, err := ttlMilliseconds(MaxTTL); err != nil || milliseconds != 3_600_000 {
		t.Fatalf("max TTL = %d err=%v", milliseconds, err)
	}
}

func validPresentation() Presentation {
	return Presentation{TaskRef: "SWM-503", Task: "Show job activity", Phase: "execution", Model: "gpt-5.6-sol", Attempt: "attempt-1"}
}

func TestClearMetadataOwnsAllAndOnlyPresentationTokens(t *testing.T) {
	client, err := New(testConfig())
	if err != nil {
		t.Fatal(err)
	}
	var got []string
	client.run = func(_ context.Context, args []string) ([]byte, []byte, error) {
		got = append([]string(nil), args...)
		return []byte(`{"result":{"type":"ok"}}`), nil, nil
	}
	if err := client.ClearMetadata(context.Background(), Locator{WorkspaceID: "opaque-workspace", TabID: "t", PaneID: "p"}, 20); err != nil {
		t.Fatal(err)
	}
	joined := strings.Join(got, " ")
	for _, name := range presentationTokens {
		if !strings.Contains(joined, "--clear-token "+name) {
			t.Fatalf("clear argv omitted %q: %#v", name, got)
		}
	}
	if !strings.Contains(joined, "--clear-title --clear-display-agent") || !strings.HasSuffix(joined, "--seq 20") {
		t.Fatalf("clear argv is incomplete: %#v", got)
	}
}

func TestMetadataFailureOutcomeNeverClaimsJobDisposition(t *testing.T) {
	transport := errors.New("socket lost")
	auto := Outcome(ModeAuto, transport)
	required := Outcome(ModeRequired, transport)
	if !auto.Attempted || auto.Visible || auto.Required || !errors.Is(auto.Error, transport) {
		t.Fatalf("auto outcome = %#v", auto)
	}
	if !required.Attempted || required.Visible || !required.Required || !errors.Is(required.Error, transport) {
		t.Fatalf("required outcome = %#v", required)
	}
	// VisibilityOutcome deliberately exposes no JobStatus or disposition field.
	typeOf := reflect.TypeOf(required)
	for index := 0; index < typeOf.NumField(); index++ {
		name := strings.ToLower(typeOf.Field(index).Name)
		if strings.Contains(name, "status") || strings.Contains(name, "disposition") {
			t.Fatal("visibility outcome can mutate job truth")
		}
	}
}

func TestSequenceRejectsZero(t *testing.T) {
	client, _ := New(testConfig())
	client.run = func(context.Context, []string) ([]byte, []byte, error) {
		t.Fatal("zero sequence reached transport")
		return nil, nil, nil
	}
	if err := client.ReportMetadata(context.Background(), Locator{WorkspaceID: "opaque-workspace", TabID: "t", PaneID: "p"}, MetadataUpdate{}); err == nil {
		t.Fatal("zero metadata sequence was accepted")
	}
	if err := client.ClearMetadata(context.Background(), Locator{WorkspaceID: "opaque-workspace", TabID: "t", PaneID: "p"}, 0); err == nil {
		t.Fatal("zero clear sequence was accepted")
	}
	_ = strconv.IntSize // keep this test explicit about native integer independence.
}
