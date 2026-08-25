package runplane

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestHTTPRequiresBearerAndLoopbackHost(t *testing.T) {
	supervisor := newTestSupervisor(t, testDefinitionRoots(t), 20, 4)
	handler := supervisor.Handler()
	request := httptest.NewRequest(http.MethodGet, "http://127.0.0.1/v1/health", nil)
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusUnauthorized {
		t.Fatalf("unauthorized status=%d", recorder.Code)
	}

	request = httptest.NewRequest(http.MethodGet, "http://evil.example/v1/health", nil)
	request.Header.Set("Authorization", "Bearer "+supervisor.authToken)
	recorder = httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusForbidden {
		t.Fatalf("bad-host status=%d", recorder.Code)
	}

	request = httptest.NewRequest(http.MethodGet, "http://localhost/v1/health", nil)
	request.Header.Set("Authorization", "Bearer "+supervisor.authToken)
	recorder = httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK {
		t.Fatalf("authorized status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var health struct {
		MaxConcurrent int              `json:"maxConcurrent"`
		Visibility    VisibilityHealth `json:"visibility"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &health); err != nil || health.MaxConcurrent != 4 {
		t.Fatalf("health=%+v error=%v, want configured maxConcurrent 4", health, err)
	}
	if health.Visibility.Mode != VisibilityOff || !health.Visibility.Ready || !health.Visibility.ForeignJobsOnly {
		t.Fatalf("unsafe or incomplete visibility health = %+v", health.Visibility)
	}
}

func TestHTTPServerBoundsAllConnectionLifetimes(t *testing.T) {
	supervisor := newTestSupervisor(t, testDefinitionRoots(t), 20, 4)
	server := supervisor.HTTPServer()
	if server.ReadHeaderTimeout <= 0 || server.ReadTimeout <= 0 || server.WriteTimeout <= 0 || server.IdleTimeout <= 0 {
		t.Fatalf("unbounded HTTP server timeouts: %+v", server)
	}
}
