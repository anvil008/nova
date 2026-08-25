package runplane

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

func TestMCPExposesOneClosedLifecycleTool(t *testing.T) {
	backend := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.URL.Path != "/v1/health" {
			t.Fatalf("unexpected backend path %q", request.URL.Path)
		}
		_ = json.NewEncoder(writer).Encode(Health{Status: "ok", APIVersion: APIVersion, MaxConcurrent: 25})
	}))
	defer backend.Close()
	httpClient := backend.Client()
	httpClient.Timeout = time.Second
	client, err := NewClient(ClientOptions{BaseURL: backend.URL, Token: "secret", HTTPClient: httpClient})
	if err != nil {
		t.Fatal(err)
	}
	server, err := NewMCPServer(client, t.TempDir())
	if err != nil {
		t.Fatal(err)
	}

	ctx := context.Background()
	serverTransport, clientTransport := mcp.NewInMemoryTransports()
	serverSession, err := server.Connect(ctx, serverTransport, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer serverSession.Close()
	mcpClient := mcp.NewClient(&mcp.Implementation{Name: "test", Version: "v1"}, nil)
	clientSession, err := mcpClient.Connect(ctx, clientTransport, nil)
	if err != nil {
		t.Fatal(err)
	}
	defer clientSession.Close()

	listed, err := clientSession.ListTools(ctx, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(listed.Tools) != 1 || listed.Tools[0].Name != MCPToolName {
		t.Fatalf("tools=%v, want only %q", listed.Tools, MCPToolName)
	}
	schema, ok := listed.Tools[0].InputSchema.(map[string]any)
	if !ok {
		t.Fatalf("input schema type %T", listed.Tools[0].InputSchema)
	}
	properties, ok := schema["properties"].(map[string]any)
	if !ok {
		t.Fatalf("properties=%T", schema["properties"])
	}
	operation, ok := properties["operation"].(map[string]any)
	if !ok {
		t.Fatalf("operation schema=%T", properties["operation"])
	}
	values, ok := operation["enum"].([]any)
	if !ok || len(values) != len(lifecycleOperations) {
		t.Fatalf("operation enum=%v", operation["enum"])
	}
	result, err := clientSession.CallTool(ctx, &mcp.CallToolParams{Name: MCPToolName, Arguments: map[string]any{"operation": "health"}})
	if err != nil {
		t.Fatal(err)
	}
	if result.IsError {
		t.Fatalf("health result is tool error: %+v", result.Content)
	}
}

func TestLifecycleRejectsCrossOperationAndArbitraryInputs(t *testing.T) {
	client := &Client{}
	invalid := []LifecycleInput{
		{Operation: "shell"},
		{Operation: OperationHealth, JobID: "0123456789abcdef0123456789abcdef"},
		{Operation: OperationStart},
		{Operation: OperationStatus, JobID: "../escape"},
		{Operation: OperationSend, JobID: "0123456789abcdef0123456789abcdef"},
		{Operation: OperationResume, JobID: "0123456789abcdef0123456789abcdef"},
		{Operation: OperationCancel, JobID: "0123456789abcdef0123456789abcdef", After: 1},
	}
	for _, input := range invalid {
		if _, err := executeLifecycle(context.Background(), client, t.TempDir(), input); err == nil {
			t.Fatalf("executeLifecycle(%+v) succeeded", input)
		}
	}
}
