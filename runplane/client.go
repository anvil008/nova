package runplane

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"time"
)

const (
	defaultClientTimeout  = 30 * time.Second
	maxClientResponseSize = 4 << 20
	maxMessageSize        = 64 << 10
	maxBriefSize          = 256 << 10
)

var jobIDPattern = regexp.MustCompile(`^[a-f0-9]{32}$`)

// Client is the typed, loopback-only client for the supervisor HTTP API.  It
// intentionally exposes fixed lifecycle methods instead of an arbitrary
// method/path primitive.
type Client struct {
	base       *url.URL
	token      string
	httpClient *http.Client
}

type ClientOptions struct {
	BaseURL    string
	Token      string
	HTTPClient *http.Client
}

type Health struct {
	Status        string           `json:"status"`
	APIVersion    string           `json:"apiVersion"`
	MaxConcurrent int              `json:"maxConcurrent"`
	Visibility    VisibilityHealth `json:"visibility"`
}

func NewClient(options ClientOptions) (*Client, error) {
	parsed, err := url.Parse(options.BaseURL)
	if err != nil {
		return nil, fmt.Errorf("parse run-plane URL: %w", err)
	}
	if parsed.Scheme != "http" || parsed.Host == "" || parsed.User != nil || parsed.RawQuery != "" || parsed.Fragment != "" || (parsed.Path != "" && parsed.Path != "/") {
		return nil, errors.New("run-plane URL must be an http loopback origin without credentials, path, query, or fragment")
	}
	host := parsed.Hostname()
	if host != "localhost" {
		ip := net.ParseIP(host)
		if ip == nil || !ip.IsLoopback() {
			return nil, errors.New("run-plane URL must resolve syntactically to a loopback address")
		}
	}
	if strings.TrimSpace(options.Token) == "" {
		return nil, errors.New("run-plane bearer token is required")
	}
	transport := options.HTTPClient
	if transport == nil {
		transport = &http.Client{Timeout: defaultClientTimeout}
	} else if transport.Timeout <= 0 {
		return nil, errors.New("run-plane HTTP client must have a positive timeout")
	}
	parsed.Path = ""
	return &Client{base: parsed, token: strings.TrimSpace(options.Token), httpClient: transport}, nil
}

func (c *Client) Health(ctx context.Context) (Health, error) {
	var output Health
	err := c.request(ctx, http.MethodGet, "/v1/health", nil, &output)
	return output, err
}

func (c *Client) Capabilities(ctx context.Context) ([]Capability, error) {
	var output []Capability
	err := c.request(ctx, http.MethodGet, "/v1/capabilities", nil, &output)
	return output, err
}

func (c *Client) Start(ctx context.Context, input StartRequest) (Job, error) {
	var output Job
	err := c.request(ctx, http.MethodPost, "/v1/jobs", input, &output)
	return output, err
}

func (c *Client) List(ctx context.Context) ([]Job, error) {
	var output []Job
	err := c.request(ctx, http.MethodGet, "/v1/jobs", nil, &output)
	return output, err
}

func (c *Client) Status(ctx context.Context, jobID string) (Job, error) {
	var output Job
	path, err := jobPath(jobID)
	if err != nil {
		return output, err
	}
	err = c.request(ctx, http.MethodGet, path, nil, &output)
	return output, err
}

func (c *Client) Events(ctx context.Context, jobID string, after uint64) ([]Event, error) {
	var output []Event
	path, err := jobPath(jobID)
	if err != nil {
		return output, err
	}
	path += "/events?after=" + strconv.FormatUint(after, 10)
	err = c.request(ctx, http.MethodGet, path, nil, &output)
	return output, err
}

func (c *Client) Send(ctx context.Context, jobID, message string) error {
	if len(message) == 0 || len(message) > maxMessageSize {
		return fmt.Errorf("message must be between 1 byte and %d bytes", maxMessageSize)
	}
	path, err := jobPath(jobID)
	if err != nil {
		return err
	}
	var output struct {
		Accepted bool `json:"accepted"`
	}
	if err := c.request(ctx, http.MethodPost, path+"/message", map[string]string{"message": message}, &output); err != nil {
		return err
	}
	if !output.Accepted {
		return errors.New("run plane did not accept message")
	}
	return nil
}

func (c *Client) Resume(ctx context.Context, jobID, brief string) (Job, error) {
	if len(brief) == 0 || len(brief) > maxBriefSize {
		return Job{}, fmt.Errorf("resume brief must be between 1 byte and %d bytes", maxBriefSize)
	}
	path, err := jobPath(jobID)
	if err != nil {
		return Job{}, err
	}
	var output Job
	err = c.request(ctx, http.MethodPost, path+"/resume", map[string]string{"brief": brief}, &output)
	return output, err
}

func (c *Client) Cancel(ctx context.Context, jobID string) error {
	path, err := jobPath(jobID)
	if err != nil {
		return err
	}
	var output struct {
		Accepted bool `json:"accepted"`
	}
	if err := c.request(ctx, http.MethodPost, path+"/cancel", map[string]any{}, &output); err != nil {
		return err
	}
	if !output.Accepted {
		return errors.New("run plane did not accept cancellation")
	}
	return nil
}

func (c *Client) Evidence(ctx context.Context, jobID string) (Evidence, error) {
	var output Evidence
	path, err := jobPath(jobID)
	if err != nil {
		return output, err
	}
	err = c.request(ctx, http.MethodGet, path+"/evidence", nil, &output)
	return output, err
}

func jobPath(jobID string) (string, error) {
	if !jobIDPattern.MatchString(jobID) {
		return "", errors.New("job ID must be exactly 32 lowercase hexadecimal characters")
	}
	return "/v1/jobs/" + jobID, nil
}

func (c *Client) request(ctx context.Context, method, path string, input, output any) error {
	if c == nil || c.base == nil || c.httpClient == nil {
		return errors.New("run-plane client is not initialized")
	}
	if strings.Contains(path, "..") || !strings.HasPrefix(path, "/v1/") {
		return errors.New("invalid fixed run-plane API path")
	}
	var body io.Reader
	if input != nil {
		data, err := json.Marshal(input)
		if err != nil {
			return fmt.Errorf("encode run-plane request: %w", err)
		}
		if len(data) > maxBriefSize {
			return fmt.Errorf("run-plane request exceeds %d bytes", maxBriefSize)
		}
		body = bytes.NewReader(data)
	}
	request, err := http.NewRequestWithContext(ctx, method, strings.TrimRight(c.base.String(), "/")+path, body)
	if err != nil {
		return fmt.Errorf("create run-plane request: %w", err)
	}
	request.Header.Set("Authorization", "Bearer "+c.token)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Accept", "application/json")
	response, err := c.httpClient.Do(request)
	if err != nil {
		return fmt.Errorf("call run-plane supervisor: %w", err)
	}
	defer response.Body.Close()
	data, err := io.ReadAll(io.LimitReader(response.Body, maxClientResponseSize+1))
	if err != nil {
		return fmt.Errorf("read run-plane response: %w", err)
	}
	if len(data) > maxClientResponseSize {
		return fmt.Errorf("run-plane response exceeds %d bytes", maxClientResponseSize)
	}
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		var envelope struct {
			Error string `json:"error"`
		}
		if json.Unmarshal(data, &envelope) == nil && envelope.Error != "" {
			return fmt.Errorf("run plane returned %s: %s", response.Status, redactError(envelope.Error))
		}
		return fmt.Errorf("run plane returned %s", response.Status)
	}
	if output == nil {
		return nil
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(output); err != nil {
		return fmt.Errorf("decode run-plane response: %w", err)
	}
	if decoder.Decode(new(any)) != io.EOF {
		return errors.New("run-plane response must contain exactly one JSON value")
	}
	return nil
}
