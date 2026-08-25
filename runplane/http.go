package runplane

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"strconv"
	"strings"
	"time"
)

func (s *Supervisor) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /v1/health", func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, Health{Status: "ok", APIVersion: APIVersion, MaxConcurrent: s.maxConcurrent, Visibility: s.visibility.health()})
	})
	mux.HandleFunc("GET /v1/capabilities", s.handleCapabilities)
	mux.HandleFunc("GET /v1/jobs", s.handleList)
	mux.HandleFunc("POST /v1/jobs", s.handleStart)
	mux.HandleFunc("GET /v1/jobs/{id}", s.handleStatus)
	mux.HandleFunc("GET /v1/jobs/{id}/events", s.handleEvents)
	mux.HandleFunc("POST /v1/jobs/{id}/message", s.handleMessage)
	mux.HandleFunc("POST /v1/jobs/{id}/resume", s.handleResume)
	mux.HandleFunc("POST /v1/jobs/{id}/cancel", s.handleCancel)
	mux.HandleFunc("GET /v1/jobs/{id}/evidence", s.handleEvidence)
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		writer.Header().Set("Content-Type", "application/json")
		writer.Header().Set("Cache-Control", "no-store")
		if !validLoopbackHost(request.Host) {
			writeError(writer, http.StatusForbidden, fmt.Errorf("invalid Host header"))
			return
		}
		const prefix = "Bearer "
		authorization := request.Header.Get("Authorization")
		if !strings.HasPrefix(authorization, prefix) || !s.Authenticate(strings.TrimPrefix(authorization, prefix)) {
			writer.Header().Set("WWW-Authenticate", "Bearer")
			writeError(writer, http.StatusUnauthorized, fmt.Errorf("authentication required"))
			return
		}
		mux.ServeHTTP(writer, request)
	})
}

func (s *Supervisor) HTTPServer() *http.Server {
	return &http.Server{
		Handler:           s.Handler(),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       15 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
}

func validLoopbackHost(value string) bool {
	host := value
	if parsed, _, err := net.SplitHostPort(value); err == nil {
		host = parsed
	}
	host = strings.Trim(host, "[]")
	return host == "localhost" || (net.ParseIP(host) != nil && net.ParseIP(host).IsLoopback())
}

func ListenLoopback(address string) (net.Listener, error) {
	listener, err := net.Listen("tcp", address)
	if err != nil {
		return nil, err
	}
	host, _, err := net.SplitHostPort(listener.Addr().String())
	if err != nil || !net.ParseIP(host).IsLoopback() {
		listener.Close()
		return nil, fmt.Errorf("run-plane service must listen on a loopback address")
	}
	return listener, nil
}

func (s *Supervisor) handleCapabilities(writer http.ResponseWriter, request *http.Request) {
	writeJSON(writer, http.StatusOK, s.Capabilities(request.Context()))
}
func (s *Supervisor) handleList(writer http.ResponseWriter, _ *http.Request) {
	writeJSON(writer, http.StatusOK, s.List())
}
func (s *Supervisor) handleStart(writer http.ResponseWriter, request *http.Request) {
	var input StartRequest
	if err := decodeJSONBody(request, &input); err != nil {
		writeError(writer, http.StatusBadRequest, err)
		return
	}
	job, err := s.Start(request.Context(), input)
	if err != nil {
		writeError(writer, http.StatusConflict, err)
		return
	}
	writeJSON(writer, http.StatusAccepted, job)
}
func (s *Supervisor) handleStatus(writer http.ResponseWriter, request *http.Request) {
	job, err := s.Status(request.PathValue("id"))
	if err != nil {
		writeError(writer, http.StatusNotFound, err)
		return
	}
	writeJSON(writer, http.StatusOK, job)
}
func (s *Supervisor) handleEvents(writer http.ResponseWriter, request *http.Request) {
	after, err := strconv.ParseUint(request.URL.Query().Get("after"), 10, 64)
	if request.URL.Query().Get("after") == "" {
		after, err = 0, nil
	}
	if err != nil {
		writeError(writer, http.StatusBadRequest, fmt.Errorf("after must be an unsigned sequence"))
		return
	}
	events, err := s.Events(request.PathValue("id"), after)
	if err != nil {
		writeError(writer, http.StatusNotFound, err)
		return
	}
	writeJSON(writer, http.StatusOK, events)
}
func (s *Supervisor) handleMessage(writer http.ResponseWriter, request *http.Request) {
	var input struct {
		Message string `json:"message"`
	}
	if err := decodeJSONBody(request, &input); err != nil {
		writeError(writer, http.StatusBadRequest, err)
		return
	}
	if err := s.Send(request.PathValue("id"), input.Message); err != nil {
		writeError(writer, http.StatusConflict, err)
		return
	}
	writeJSON(writer, http.StatusAccepted, map[string]any{"accepted": true})
}
func (s *Supervisor) handleResume(writer http.ResponseWriter, request *http.Request) {
	var input struct {
		Brief string `json:"brief"`
	}
	if err := decodeJSONBody(request, &input); err != nil {
		writeError(writer, http.StatusBadRequest, err)
		return
	}
	job, err := s.Resume(request.Context(), request.PathValue("id"), input.Brief)
	if err != nil {
		writeError(writer, http.StatusConflict, err)
		return
	}
	writeJSON(writer, http.StatusAccepted, job)
}
func (s *Supervisor) handleCancel(writer http.ResponseWriter, request *http.Request) {
	if err := s.Cancel(request.PathValue("id")); err != nil {
		writeError(writer, http.StatusConflict, err)
		return
	}
	writeJSON(writer, http.StatusAccepted, map[string]any{"accepted": true})
}
func (s *Supervisor) handleEvidence(writer http.ResponseWriter, request *http.Request) {
	evidence, err := s.Evidence(request.PathValue("id"))
	if err != nil {
		writeError(writer, http.StatusNotFound, err)
		return
	}
	writeJSON(writer, http.StatusOK, evidence)
}

func decodeJSONBody(request *http.Request, target any) error {
	defer request.Body.Close()
	decoder := json.NewDecoder(http.MaxBytesReader(nil, request.Body, 256<<10))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return fmt.Errorf("decode request: %w", err)
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return fmt.Errorf("request must contain exactly one JSON value")
	}
	return nil
}

func writeJSON(writer http.ResponseWriter, status int, value any) {
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(value)
}
func writeError(writer http.ResponseWriter, status int, err error) {
	writeJSON(writer, status, map[string]string{"error": redactError(err.Error())})
}
func redactError(value string) string {
	redacted, _ := redactValue(value).(string)
	return strings.TrimSpace(redacted)
}
