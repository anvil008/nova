package runplane

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/anvil008/swarm-coder/codingfleet"
	"github.com/anvil008/swarm-coder/controlplane"
)

// recordAgentHandoff accepts the small native/foreign integration boundary.
// It intentionally does not duplicate provider session state, durable ledgers,
// or harness process details.
func (s *Supervisor) recordAgentHandoff(jobID, text string) bool {
	raw := []byte(strings.TrimSpace(text))
	if len(raw) == 0 || len(raw) > controlplane.MaxContractBytes || raw[0] != '{' || !bytes.Contains(raw, []byte(codingfleet.AgentHandoffAPIVersion)) {
		return false
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	var handoff codingfleet.AgentHandoff
	if err := decoder.Decode(&handoff); err != nil {
		s.recordHandoffFailure(jobID, fmt.Errorf("decode agent handoff: %w", err))
		return true
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		s.recordHandoffFailure(jobID, fmt.Errorf("decode agent handoff: trailing data"))
		return true
	}
	if err := codingfleet.ValidateAgentHandoff(handoff); err != nil {
		s.recordHandoffFailure(jobID, err)
		return true
	}

	s.mu.Lock()
	job := s.jobs[jobID]
	if job == nil || isTerminalCancellation(job) {
		s.mu.Unlock()
		return true
	}
	route := job.Route
	s.mu.Unlock()

	wantMode := codingfleet.CapabilityMode(route.CapabilityMode)
	if handoff.RunID != route.DispatchID || handoff.ParentRunID != route.ParentDispatchID ||
		handoff.CanonicalRole != route.CanonicalRoleID || handoff.Provider != route.Provider ||
		handoff.Model != route.ExactModel || handoff.Effort != route.Effort || handoff.Mode != wantMode ||
		handoff.Limits != route.Limits || !sameStrings(handoff.OwnedFiles, route.FileOwnership) {
		s.recordHandoffFailure(jobID, fmt.Errorf("agent handoff does not match admitted route"))
		return true
	}
	if route.CapabilityMode == ModeReadOnly && len(handoff.ChangedFiles) != 0 {
		s.recordHandoffFailure(jobID, fmt.Errorf("read-only agent handoff reports changed files"))
		return true
	}
	for _, changed := range handoff.ChangedFiles {
		if !pathCoveredByOwnership(changed, route.FileOwnership) {
			s.recordHandoffFailure(jobID, fmt.Errorf("agent handoff reports changed file outside ownership"))
			return true
		}
	}
	checks := make(map[string]bool, len(handoff.Tests))
	for _, check := range handoff.Tests {
		checks[check.Name] = check.Passed
	}
	for _, required := range route.Evidence.RequiredChecks {
		if !checks[required] {
			s.recordHandoffFailure(jobID, fmt.Errorf("required test %q is missing or failed", required))
			return true
		}
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	job = s.jobs[jobID]
	if job == nil || isTerminalCancellation(job) {
		return true
	}
	job.Handoff = &handoff
	job.HandoffFailure = ""
	job.WorkflowDisposition = handoffWorkflowDisposition(handoff.Disposition)
	job.UpdatedAt = time.Now().UTC()
	if err := s.persistJob(*job); err != nil {
		s.markDurabilityFailureLocked(jobID, "agent handoff", err)
		return true
	}
	if err := s.appendEventLocked(jobID, "agent.handoff", map[string]any{"runId": handoff.RunID, "role": handoff.CanonicalRole, "disposition": handoff.Disposition}); err != nil {
		s.markDurabilityFailureLocked(jobID, "agent handoff event", err)
	}
	return true
}

func (s *Supervisor) recordHandoffFailure(jobID string, cause error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	job := s.jobs[jobID]
	if job == nil {
		return
	}
	job.Handoff = nil
	job.HandoffFailure = redactError(cause.Error())
	job.WorkflowDisposition = controlplane.DispositionUncertain
	job.UpdatedAt = time.Now().UTC()
	if err := s.persistJob(*job); err != nil {
		s.markDurabilityFailureLocked(jobID, "agent handoff failure", err)
		return
	}
	if err := s.appendEventLocked(jobID, "agent.handoff_rejected", map[string]any{"error": job.HandoffFailure}); err != nil {
		s.markDurabilityFailureLocked(jobID, "agent handoff rejection event", err)
	}
}

func handoffWorkflowDisposition(value codingfleet.HandoffDisposition) controlplane.WorkflowDisposition {
	switch value {
	case codingfleet.HandoffSucceeded:
		return controlplane.DispositionSucceeded
	case codingfleet.HandoffFailed:
		return controlplane.DispositionFailed
	case codingfleet.HandoffBlocked:
		return controlplane.DispositionBlocked
	case codingfleet.HandoffCancelled:
		return controlplane.DispositionCancelled
	default:
		return controlplane.DispositionUncertain
	}
}

func sameStrings(left, right []string) bool {
	leftCopy, rightCopy := append([]string(nil), left...), append([]string(nil), right...)
	sort.Strings(leftCopy)
	sort.Strings(rightCopy)
	return strings.Join(leftCopy, "\x00") == strings.Join(rightCopy, "\x00")
}

func pathCoveredByOwnership(changed string, ownership []string) bool {
	for _, owned := range ownership {
		if changed == owned || strings.HasPrefix(changed, owned+"/") {
			return true
		}
	}
	return false
}

func (s *Supervisor) recordWorkflowResult(jobID, text string) {
	raw := []byte(strings.TrimSpace(text))
	if len(raw) == 0 || len(raw) > controlplane.MaxContractBytes || raw[0] != '{' {
		return
	}
	var result controlplane.WorkflowResult
	if err := controlplane.DecodeStrict(raw, &result); err != nil {
		if bytes.Contains(raw, []byte(controlplane.WorkflowResultAPIVersion)) {
			s.recordWorkflowFailure(jobID, fmt.Errorf("decode workflow result: %w", err))
		}
		return
	}

	s.mu.Lock()
	job := s.jobs[jobID]
	if job == nil || job.ControlPlane == nil || isTerminalCancellation(job) {
		s.mu.Unlock()
		return
	}
	jobCopy := *job
	s.mu.Unlock()
	currentRepository, err := s.repositorySnapshot(jobCopy.Route.RepositoryRoot)
	if err != nil {
		s.recordWorkflowFailure(jobID, fmt.Errorf("snapshot current repository: %w", err))
		return
	}
	admission := jobCopy.ControlPlane
	expected := controlplane.ResultExpectation{
		GoalID: admission.Goal.GoalID, AssignmentID: admission.Assignment.AssignmentID,
		GenerationID: admission.Generation.GenerationID, DispatchID: admission.Dispatch.DispatchID,
		ParentDispatchID: admission.Dispatch.ParentDispatchID, RoleID: admission.Assignment.RoleID,
		Lane: admission.Assignment.Lane, RouteDigest: admission.Route.Digest,
		AuthorityDigest: admission.Authority.Digest, SelectionDigest: admission.Selection.Digest,
		RoleDigest: admission.Authority.RoleDigest, CatalogDigest: admission.Selection.CatalogDigest,
		RepositoryBefore: admission.Goal.RepositoryDigest, CurrentRepositoryDigest: currentRepository,
		CapabilityDigest: admission.Route.Capability.Digest,
		RequiredChecks:   admission.Route.Evidence.RequiredChecks, RequiredArtifacts: admission.Route.Evidence.RequiredArtifacts,
	}
	if err := controlplane.ValidateWorkflowResult(result, expected); err != nil {
		s.recordWorkflowFailure(jobID, err)
		return
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	job = s.jobs[jobID]
	if job == nil || job.ControlPlane == nil || job.ControlPlane.Generation.GenerationID != admission.Generation.GenerationID || isTerminalCancellation(job) {
		return
	}
	job.WorkflowResult = &result
	job.WorkflowDisposition = result.Disposition
	job.WorkflowFailure = ""
	job.UpdatedAt = time.Now().UTC()
	if err := s.persistJob(*job); err != nil {
		s.markDurabilityFailureLocked(jobID, "workflow result", err)
		return
	}
	if err := s.appendEventLocked(jobID, "workflow.result", map[string]any{"digest": result.Digest, "disposition": result.Disposition}); err != nil {
		s.markDurabilityFailureLocked(jobID, "workflow result event", err)
	}
}

func (s *Supervisor) recordWorkflowFailure(jobID string, cause error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	job := s.jobs[jobID]
	if job == nil {
		return
	}
	job.WorkflowDisposition = controlplane.DispositionUncertain
	job.WorkflowFailure = redactError(cause.Error())
	job.UpdatedAt = time.Now().UTC()
	if err := s.persistJob(*job); err != nil {
		s.markDurabilityFailureLocked(jobID, "workflow failure", err)
		return
	}
	if err := s.appendEventLocked(jobID, "workflow.result_rejected", map[string]any{"error": job.WorkflowFailure}); err != nil {
		s.markDurabilityFailureLocked(jobID, "workflow rejection event", err)
	}
}

func isTerminalCancellation(job *Job) bool {
	return job.Status == StatusCanceled || job.WorkflowDisposition == controlplane.DispositionCancelled || job.WorkflowDisposition == controlplane.DispositionStale
}

// snapshotRepository returns only a digest. Raw status, paths, and tool output
// never enter run-plane evidence.
func snapshotRepository(root string) (string, error) {
	if root == "" || !filepath.IsAbs(root) {
		return "", fmt.Errorf("repository root is not absolute")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	var identity, status []byte
	var err error
	switch {
	case directoryExists(filepath.Join(root, ".jj")):
		identity, err = boundedCommandOutput(ctx, root, "jj", "log", "-r", "@", "--no-graph", "-T", `change_id ++ "\n"`)
		if err == nil {
			status, err = boundedCommandOutput(ctx, root, "jj", "status", "--no-pager")
		}
	case directoryExists(filepath.Join(root, ".git")):
		identity, err = boundedCommandOutput(ctx, root, "git", "rev-parse", "HEAD")
		if err == nil {
			status, err = boundedCommandOutput(ctx, root, "git", "status", "--porcelain=v1", "-z", "--untracked-files=all")
		}
	default:
		return "", fmt.Errorf("repository has neither .git nor .jj metadata")
	}
	if err != nil {
		return "", err
	}
	payload := struct {
		Identity string `json:"identity"`
		Status   string `json:"status"`
	}{Identity: string(identity), Status: string(status)}
	encoded, err := controlplane.EncodeCanonical(payload)
	if err != nil {
		return "", err
	}
	return controlplane.CanonicalDigest(encoded)
}

func boundedCommandOutput(ctx context.Context, directory, name string, arguments ...string) ([]byte, error) {
	command := exec.CommandContext(ctx, name, arguments...)
	command.Dir = directory
	command.Stdin = nil
	output, err := command.CombinedOutput()
	if len(output) > 8<<20 {
		return nil, fmt.Errorf("repository snapshot output exceeds 8 MiB")
	}
	if err != nil {
		return nil, fmt.Errorf("repository snapshot command failed: %w", err)
	}
	return output, nil
}

func directoryExists(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.IsDir()
}
