// Package herdrbridge provides a fail-closed bridge between Swarm jobs and an
// explicitly injected Herdr 0.8.2 runtime. It owns display and layout
// projection only; Swarm remains the authority for job lifecycle state.
package herdrbridge

import (
	"errors"
	"fmt"
	"path/filepath"
	"strings"
	"time"

	"github.com/anvil008/swarm-coder/codingfleet"
)

const (
	SupportedVersion  = "0.8.2"
	SupportedProtocol = 20
	MetadataSource    = "swarm:task-display"
	LifecycleSource   = "swarm:runplane-lifecycle"
	ActiveTTL         = 10 * time.Minute
	TerminalTTL       = time.Hour
	DefaultTTL        = ActiveTTL
	MaxTTL            = TerminalTTL
	DefaultTimeout    = 5 * time.Second
	MaxTimeout        = 30 * time.Second
	MaxSocketBytes    = 1 << 20
)

var (
	ErrDisabled     = errors.New("herdr visibility is disabled")
	ErrNotFound     = errors.New("herdr pane was not found")
	ErrAmbiguous    = errors.New("herdr pane resolution is ambiguous")
	ErrIncompatible = errors.New("herdr runtime is incompatible")
)

// Mode controls whether a visibility failure is ignored or returned to the
// caller. The caller must never translate a visibility error into a provider
// job status or disposition.
type Mode string

const (
	ModeOff      Mode = "off"
	ModeAuto     Mode = "auto"
	ModeRequired Mode = "required"
)

// Config deliberately has no ambient-environment fallback. A runtime can only
// be targeted when the caller supplies the Herdr marker, exact binary, socket,
// and workspace identity.
type Config struct {
	Mode        Mode
	HerdrEnv    bool
	BinaryPath  string
	SocketPath  string
	SessionID   string
	WorkspaceID string
	Timeout     time.Duration
}

func (c Config) validate() (Config, error) {
	if c.Mode == "" {
		c.Mode = ModeOff
	}
	if c.Mode != ModeOff && c.Mode != ModeAuto && c.Mode != ModeRequired {
		return Config{}, fmt.Errorf("unsupported herdr visibility mode %q", c.Mode)
	}
	if c.Timeout == 0 {
		c.Timeout = DefaultTimeout
	}
	if c.Timeout < time.Millisecond || c.Timeout > MaxTimeout {
		return Config{}, fmt.Errorf("herdr timeout must be between 1ms and %s", MaxTimeout)
	}
	if c.Mode == ModeOff {
		return c, nil
	}
	if !c.HerdrEnv {
		return Config{}, errors.New("HERDR_ENV=1 marker was not explicitly injected")
	}
	for name, value := range map[string]string{
		"HERDR_BIN_PATH":    c.BinaryPath,
		"HERDR_SOCKET_PATH": c.SocketPath,
	} {
		if value == "" || !filepath.IsAbs(value) {
			return Config{}, fmt.Errorf("%s must be an explicitly injected absolute path", name)
		}
	}
	if err := validateOpaque("session ID", c.SessionID, 256); err != nil {
		return Config{}, err
	}
	if err := validateOpaque("workspace ID", c.WorkspaceID, 256); err != nil {
		return Config{}, err
	}
	return c, nil
}

// Locator contains only opaque identities returned by Herdr. A pane move must
// replace this complete value with the locator from the move response.
type Locator struct {
	WorkspaceID string `json:"workspaceId"`
	TabID       string `json:"tabId"`
	PaneID      string `json:"paneId"`
	TerminalID  string `json:"terminalId"`
	JobLabel    string `json:"jobLabel"`
}

func (l Locator) validate() error {
	for name, value := range map[string]string{
		"workspace ID": l.WorkspaceID,
		"tab ID":       l.TabID,
		"pane ID":      l.PaneID,
	} {
		if err := validateOpaque(name, value, 256); err != nil {
			return err
		}
	}
	for name, value := range map[string]string{"terminal ID": l.TerminalID, "job label": l.JobLabel} {
		if value != "" {
			if err := validateOpaque(name, value, 256); err != nil {
				return err
			}
		}
	}
	return nil
}

// Presentation is the complete allowlist of Swarm data that may be shown in
// Herdr. Briefs, credentials, claims, provider input, and arbitrary event
// payloads have no representation here.
type Presentation = codingfleet.AgentPresentation

func validatePresentation(p Presentation) error {
	return p.Validate()
}

// MetadataUpdate carries an explicit durable sequence. The bridge never
// invents a sequence from time or a pane ID, so replay and restart ordering are
// deterministic.
type MetadataUpdate struct {
	Presentation Presentation
	Sequence     uint64
	TTL          time.Duration
}

func (u MetadataUpdate) validate() (MetadataUpdate, error) {
	if err := validatePresentation(u.Presentation); err != nil {
		return MetadataUpdate{}, err
	}
	if u.Sequence == 0 {
		return MetadataUpdate{}, errors.New("metadata sequence must be positive")
	}
	if u.TTL == 0 {
		u.TTL = DefaultTTL
	}
	if u.TTL != ActiveTTL && u.TTL != TerminalTTL {
		return MetadataUpdate{}, fmt.Errorf("metadata TTL must be active %s or terminal %s", ActiveTTL, TerminalTTL)
	}
	return u, nil
}

// LayoutSpec requests exactly one non-focused root pane in a new tab. Command
// is an argv vector, never a shell string; sensitive provider input belongs on
// stdin or another private channel owned by the run-plane integration.
type LayoutSpec struct {
	TabLabel string
	CWD      string
	Command  []string
	Env      map[string]string
}

func (s LayoutSpec) validate() error {
	if err := validateDisplay("tab label", s.TabLabel, 128); err != nil {
		return err
	}
	if s.CWD == "" || !filepath.IsAbs(s.CWD) {
		return errors.New("layout cwd must be absolute")
	}
	if len(s.Command) == 0 || len(s.Command) > 128 {
		return errors.New("layout command must contain 1..128 argv elements")
	}
	for _, arg := range s.Command {
		if err := validateOpaque("command argument", arg, 16<<10); err != nil {
			return err
		}
	}
	for key, value := range s.Env {
		if key == "" || strings.ContainsAny(key, "=\x00\r\n") || strings.ContainsRune(value, 0) {
			return errors.New("layout environment contains an invalid entry")
		}
	}
	return nil
}

// VisibilityOutcome keeps presentation policy separate from provider job
// truth. Required mode returns the visibility error to the orchestration layer,
// but it still does not imply a provider failure or terminal disposition.
type VisibilityOutcome struct {
	Attempted bool
	Visible   bool
	Required  bool
	Error     error
}

func Outcome(mode Mode, err error) VisibilityOutcome {
	if mode == ModeOff {
		return VisibilityOutcome{}
	}
	return VisibilityOutcome{Attempted: true, Visible: err == nil, Required: mode == ModeRequired, Error: err}
}

func validateOpaque(name, value string, maximum int) error {
	if value == "" || len(value) > maximum || strings.ContainsAny(value, "\x00\r\n") {
		return fmt.Errorf("%s must contain 1..%d non-control bytes", name, maximum)
	}
	return nil
}

func validateDisplay(name, value string, maximum int) error {
	if len(value) > maximum || strings.ContainsAny(value, "\x00\r\n") {
		return fmt.Errorf("%s must contain at most %d single-line bytes", name, maximum)
	}
	return nil
}
