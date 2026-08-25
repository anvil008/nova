package runplane

import (
	"context"
	"errors"
	"fmt"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/anvil008/swarm-coder/codingfleet"
	"github.com/anvil008/swarm-coder/herdrbridge"
)

// HerdrVisibilityClient is the narrow fakeable boundary used by the run
// plane. Tests provide an in-memory implementation; production uses only the
// explicitly configured Herdr 0.8.2 client.
type HerdrVisibilityClient interface {
	Probe(context.Context) error
	ApplyLayout(context.Context, herdrbridge.LayoutSpec) (herdrbridge.Locator, error)
	Snapshot(context.Context) (herdrbridge.Snapshot, error)
	ReportMetadata(context.Context, herdrbridge.Locator, herdrbridge.MetadataUpdate) error
	ClearMetadata(context.Context, herdrbridge.Locator, uint64) error
}

type VisibilityClientFactory func(herdrbridge.Config) (HerdrVisibilityClient, error)

// VisibilityController owns volatile pane locators and an immutable runtime
// configuration. Durable presentation state remains on Job.
type VisibilityController struct {
	mu        sync.Mutex
	config    VisibilityConfig
	client    HerdrVisibilityClient
	configErr error
	locators  map[string]herdrbridge.Locator
	lastProbe error
}

func newVisibilityController(config VisibilityConfig, factory VisibilityClientFactory) *VisibilityController {
	if config.Mode == "" {
		config.Mode = VisibilityOff
	}
	controller := &VisibilityController{config: config, locators: map[string]herdrbridge.Locator{}}
	if err := validateVisibilityConfig(config); err != nil {
		controller.configErr = err
		controller.lastProbe = err
		return controller
	}
	if config.Mode == VisibilityOff {
		return controller
	}
	if factory == nil {
		factory = func(config herdrbridge.Config) (HerdrVisibilityClient, error) { return herdrbridge.New(config) }
	}
	client, err := factory(herdrbridge.Config{
		Mode: herdrMode(config.Mode), HerdrEnv: config.HerdrEnv, BinaryPath: config.BinaryPath,
		SocketPath: config.SocketPath, SessionID: config.SessionID, WorkspaceID: config.WorkspaceID,
		Timeout: config.Timeout,
	})
	if err != nil {
		controller.configErr = err
		controller.lastProbe = err
		return controller
	}
	controller.client = client
	return controller
}

func validateVisibilityConfig(config VisibilityConfig) error {
	switch config.Mode {
	case VisibilityOff:
		return nil
	case VisibilityAuto, VisibilityRequired:
	default:
		return fmt.Errorf("unsupported visibility mode %q", config.Mode)
	}
	if !config.HerdrEnv {
		return errors.New("HERDR_ENV=1 is required")
	}
	for name, value := range map[string]string{
		"HERDR_BIN_PATH": config.BinaryPath, "HERDR_SOCKET_PATH": config.SocketPath,
		"worker binary": config.WorkerBinary,
	} {
		if value == "" || !filepath.IsAbs(value) {
			return fmt.Errorf("%s must be an explicit absolute path", name)
		}
	}
	for name, value := range map[string]string{"HERDR_SESSION": config.SessionID, "workspace": config.WorkspaceID} {
		if value == "" || len(value) > 256 || strings.ContainsAny(value, "\x00\r\n") {
			return fmt.Errorf("%s must be an explicit bounded identity", name)
		}
	}
	if config.Timeout < 0 || config.Timeout > 30*time.Second {
		return errors.New("visibility timeout must be at most 30 seconds")
	}
	return nil
}

func herdrMode(mode VisibilityMode) herdrbridge.Mode {
	switch mode {
	case VisibilityAuto:
		return herdrbridge.ModeAuto
	case VisibilityRequired:
		return herdrbridge.ModeRequired
	default:
		return herdrbridge.ModeOff
	}
}

func (c *VisibilityController) eligible(route Route) bool {
	return c != nil && c.config.Mode != VisibilityOff && route.SourceHarness != route.TargetHarness
}

func (c *VisibilityController) probe(ctx context.Context) error {
	c.mu.Lock()
	client, configErr := c.client, c.configErr
	c.mu.Unlock()
	if configErr != nil {
		return configErr
	}
	if client == nil {
		return herdrbridge.ErrDisabled
	}
	err := client.Probe(ctx)
	c.mu.Lock()
	c.lastProbe = err
	c.mu.Unlock()
	return err
}

func (c *VisibilityController) health() VisibilityHealth {
	if c == nil {
		return VisibilityHealth{Mode: VisibilityOff, Ready: true, ForeignJobsOnly: true}
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	result := VisibilityHealth{Mode: c.config.Mode, Ready: c.config.Mode == VisibilityOff || c.configErr == nil && c.client != nil && c.lastProbe == nil, ForeignJobsOnly: true}
	if c.configErr != nil {
		result.Error = safeVisibilityError(c.configErr)
	} else if c.lastProbe != nil {
		result.Error = safeVisibilityError(c.lastProbe)
	}
	return result
}

func safeVisibilityError(err error) string {
	if err == nil {
		return ""
	}
	text := strings.Map(func(r rune) rune {
		if r < 0x20 || r == 0x7f {
			return ' '
		}
		return r
	}, err.Error())
	if len(text) > 256 {
		text = text[:256]
	}
	return text
}

func (c *VisibilityController) setLocator(jobID string, locator herdrbridge.Locator) {
	c.mu.Lock()
	c.locators[jobID] = locator
	c.mu.Unlock()
}

func (c *VisibilityController) locator(jobID string) (herdrbridge.Locator, bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	locator, ok := c.locators[jobID]
	return locator, ok
}

func bridgePresentation(p codingfleet.AgentPresentation) herdrbridge.Presentation {
	return herdrbridge.Presentation{TaskRef: p.TaskRef, Task: p.Task, Phase: p.Phase, Summary: p.Summary, Model: p.Model, Attempt: p.Attempt}
}

// persistVisibilityAdvanceLocked persists the next sequence before any
// external patch, replay, refresh, or clear. The caller must hold s.mu.
func (s *Supervisor) persistVisibilityAdvanceLocked(job *Job, terminal bool, ttl time.Duration) (uint64, error) {
	if job.Visibility == nil {
		return 0, errors.New("job has no presentation state")
	}
	job.Visibility.Sequence++
	job.Visibility.TTLMillis = ttl.Milliseconds()
	job.Visibility.Terminal = terminal
	job.UpdatedAt = time.Now().UTC()
	if err := s.persistJob(*job); err != nil {
		return 0, err
	}
	return job.Visibility.Sequence, nil
}

func (s *Supervisor) publishVisibility(jobID string, terminal bool) {
	locator, ok := s.visibility.locator(jobID)
	if !ok {
		return
	}
	ttl := ActiveVisibilityTTL
	if terminal {
		ttl = TerminalVisibilityTTL
	}
	s.mu.Lock()
	job := s.jobs[jobID]
	if job == nil || job.Visibility == nil {
		s.mu.Unlock()
		return
	}
	sequence, err := s.persistVisibilityAdvanceLocked(job, terminal, ttl)
	presentation := job.Visibility.Presentation
	s.mu.Unlock()
	if err == nil {
		err = s.visibility.client.ReportMetadata(context.Background(), locator, herdrbridge.MetadataUpdate{
			Presentation: bridgePresentation(presentation), Sequence: sequence, TTL: ttl,
		})
		if err != nil {
			if snapshot, snapshotErr := s.visibility.client.Snapshot(context.Background()); snapshotErr == nil {
				if moved, resolveErr := herdrbridge.ResolveLocator(snapshot, locator, bridgePresentation(presentation)); resolveErr == nil {
					s.visibility.setLocator(jobID, moved)
					err = s.visibility.client.ReportMetadata(context.Background(), moved, herdrbridge.MetadataUpdate{Presentation: bridgePresentation(presentation), Sequence: sequence, TTL: ttl})
				}
			}
		}
	}
	s.recordVisibilityOutcome(jobID, sequence, "publish", err)
}

func (s *Supervisor) recoverVisibility(jobID string) {
	s.mu.Lock()
	job := s.jobs[jobID]
	if job == nil || job.Visibility == nil || s.visibility == nil || s.visibility.client == nil {
		s.mu.Unlock()
		return
	}
	presentation := job.Visibility.Presentation
	terminalState := terminal(job.Status)
	previous := herdrbridge.Locator{WorkspaceID: s.visibility.config.WorkspaceID, JobLabel: "swarm-job-" + jobID}
	s.mu.Unlock()
	snapshot, err := s.visibility.client.Snapshot(context.Background())
	if err != nil {
		s.recordVisibilityOutcome(jobID, 0, "recovery-snapshot", err)
		return
	}
	locator, err := herdrbridge.ResolveLocator(snapshot, previous, bridgePresentation(presentation))
	if err != nil {
		s.recordVisibilityOutcome(jobID, 0, "recovery-resolve", err)
		return
	}
	s.visibility.setLocator(jobID, locator)
	s.publishVisibility(jobID, terminalState)
}

func (s *Supervisor) clearVisibility(jobID string) {
	locator, ok := s.visibility.locator(jobID)
	if !ok {
		return
	}
	s.mu.Lock()
	job := s.jobs[jobID]
	if job == nil || job.Visibility == nil {
		s.mu.Unlock()
		return
	}
	sequence, err := s.persistVisibilityAdvanceLocked(job, true, TerminalVisibilityTTL)
	s.mu.Unlock()
	if err == nil {
		err = s.visibility.client.ClearMetadata(context.Background(), locator, sequence)
	}
	s.recordVisibilityOutcome(jobID, sequence, "clear", err)
}

func (s *Supervisor) recordVisibilityOutcome(jobID string, sequence uint64, operation string, outcome error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	job := s.jobs[jobID]
	if job == nil || job.Visibility == nil {
		return
	}
	now := time.Now().UTC()
	if outcome == nil {
		job.Visibility.LastPublishedAt = &now
		job.Visibility.LastError = ""
	} else {
		job.Visibility.LastError = safeVisibilityError(outcome)
	}
	job.UpdatedAt = now
	_ = s.persistJob(*job)
	kind := "visibility.published"
	payload := map[string]any{"operation": operation, "sequence": sequence}
	if outcome != nil {
		kind = "visibility.error"
		payload["error"] = safeVisibilityError(outcome)
	}
	// Visibility persistence failures are diagnostics only. They must never be
	// translated into job status, workflow disposition, or provider signals.
	_ = s.appendEventLocked(jobID, kind, payload)
}

func (s *Supervisor) refreshVisibility(jobID string, done <-chan struct{}) {
	ticker := time.NewTicker(VisibilityRefreshInterval)
	defer ticker.Stop()
	for {
		select {
		case <-done:
			return
		case <-ticker.C:
			s.publishVisibility(jobID, false)
		}
	}
}
