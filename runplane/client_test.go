package runplane

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"
)

func TestClientRejectsNonLoopbackAndUnboundedTransport(t *testing.T) {
	for _, address := range []string{"https://127.0.0.1:8083", "http://example.com:8083", "http://127.0.0.1:8083/arbitrary", "http://user:pass@127.0.0.1:8083"} {
		if _, err := NewClient(ClientOptions{BaseURL: address, Token: "token", HTTPClient: &http.Client{Timeout: time.Second}}); err == nil {
			t.Fatalf("NewClient(%q) succeeded", address)
		}
	}
	if _, err := NewClient(ClientOptions{BaseURL: "http://127.0.0.1:8083", Token: "token", HTTPClient: &http.Client{}}); err == nil {
		t.Fatal("NewClient accepted client without timeout")
	}
}

func TestClientFixedLifecycleRequests(t *testing.T) {
	const jobID = "0123456789abcdef0123456789abcdef"
	requests := make(chan *http.Request, 10)
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		requests <- request.Clone(request.Context())
		if request.Header.Get("Authorization") != "Bearer secret-token" {
			t.Errorf("authorization=%q", request.Header.Get("Authorization"))
		}
		writer.Header().Set("Content-Type", "application/json")
		switch {
		case request.URL.Path == "/v1/health":
			_ = json.NewEncoder(writer).Encode(Health{Status: "ok", APIVersion: APIVersion, MaxConcurrent: 25})
		case request.URL.Path == "/v1/capabilities":
			_ = json.NewEncoder(writer).Encode([]Capability{})
		case request.URL.Path == "/v1/jobs" && request.Method == http.MethodPost:
			_ = json.NewEncoder(writer).Encode(Job{ID: jobID})
		case request.URL.Path == "/v1/jobs" && request.Method == http.MethodGet:
			_ = json.NewEncoder(writer).Encode([]Job{{ID: jobID}})
		case strings.HasSuffix(request.URL.Path, "/events"):
			_ = json.NewEncoder(writer).Encode([]Event{})
		case strings.HasSuffix(request.URL.Path, "/message"), strings.HasSuffix(request.URL.Path, "/cancel"):
			_ = json.NewEncoder(writer).Encode(map[string]bool{"accepted": true})
		case strings.HasSuffix(request.URL.Path, "/resume"):
			_ = json.NewEncoder(writer).Encode(Job{ID: jobID, ResumeOf: jobID})
		case strings.HasSuffix(request.URL.Path, "/evidence"):
			_ = json.NewEncoder(writer).Encode(Evidence{Job: Job{ID: jobID}})
		default:
			_ = json.NewEncoder(writer).Encode(Job{ID: jobID})
		}
	}))
	defer server.Close()

	httpClient := server.Client()
	httpClient.Timeout = time.Second
	client, err := NewClient(ClientOptions{BaseURL: strings.Replace(server.URL, "127.0.0.1", "localhost", 1), Token: "secret-token", HTTPClient: httpClient})
	if err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()
	if _, err := client.Health(ctx); err != nil {
		t.Fatal(err)
	}
	if _, err := client.Capabilities(ctx); err != nil {
		t.Fatal(err)
	}
	if _, err := client.Start(ctx, StartRequest{}); err != nil {
		t.Fatal(err)
	}
	if _, err := client.List(ctx); err != nil {
		t.Fatal(err)
	}
	if _, err := client.Status(ctx, jobID); err != nil {
		t.Fatal(err)
	}
	if _, err := client.Events(ctx, jobID, 7); err != nil {
		t.Fatal(err)
	}
	if err := client.Send(ctx, jobID, "checkpoint"); err != nil {
		t.Fatal(err)
	}
	if _, err := client.Resume(ctx, jobID, "continue"); err != nil {
		t.Fatal(err)
	}
	if err := client.Cancel(ctx, jobID); err != nil {
		t.Fatal(err)
	}
	if _, err := client.Evidence(ctx, jobID); err != nil {
		t.Fatal(err)
	}
	if got := len(requests); got != 10 {
		t.Fatalf("requests=%d, want 10", got)
	}
	close(requests)
	for request := range requests {
		if request.Host == "" || !strings.HasPrefix(request.URL.Path, "/v1/") {
			t.Fatalf("unexpected request: %s", request.URL.String())
		}
	}
}

func TestClientBoundsIdentifiersAndPayloads(t *testing.T) {
	client := &Client{base: mustURL(t, "http://127.0.0.1:8083"), token: "x", httpClient: &http.Client{Timeout: time.Second}}
	if err := client.Send(context.Background(), "../escape", "x"); err == nil {
		t.Fatal("invalid job ID reached transport")
	}
	if err := client.Send(context.Background(), strings.Repeat("a", 32), strings.Repeat("x", maxMessageSize+1)); err == nil {
		t.Fatal("oversized message accepted")
	}
}

func mustURL(t *testing.T, value string) *url.URL {
	t.Helper()
	parsed, err := url.Parse(value)
	if err != nil {
		t.Fatal(err)
	}
	return parsed
}

func TestClientSurfacesNon2xxErrors(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		writer.Header().Set("Content-Type", "application/json")
		writer.WriteHeader(http.StatusConflict)
		_ = json.NewEncoder(writer).Encode(map[string]string{
			"error": "provider and family must both be explicit",
		})
	}))
	defer server.Close()

	httpClient := server.Client()
	httpClient.Timeout = time.Second
	client, err := NewClient(ClientOptions{BaseURL: server.URL, Token: "secret-token", HTTPClient: httpClient})
	if err != nil {
		t.Fatal(err)
	}

	_, err = client.Start(context.Background(), StartRequest{})
	if err == nil {
		t.Fatal("expected error on HTTP 409 Conflict response, got nil")
	}
	if !strings.Contains(err.Error(), "409") || !strings.Contains(err.Error(), "provider and family must both be explicit") {
		t.Fatalf("error = %q, want status code 409 and server error text", err)
	}
}
