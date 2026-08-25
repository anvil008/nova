package runplane

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

type stateStore struct {
	root          string
	maxEvents     int
	maxEventBytes int
}

const maxStoredEventBytes = 2 << 20
const stateSchemaVersion = 3

type stateVersionRecord struct {
	Version int `json:"version"`
}

func newStateStore(root string, maxEvents int) (stateStore, error) {
	if root == "" || !filepath.IsAbs(root) {
		return stateStore{}, fmt.Errorf("state directory %q must be absolute", root)
	}
	if maxEvents <= 0 {
		maxEvents = 500
	}
	for _, directory := range []string{root, filepath.Join(root, "jobs"), filepath.Join(root, "events")} {
		if err := os.MkdirAll(directory, 0o700); err != nil {
			return stateStore{}, fmt.Errorf("create run-plane state directory: %w", err)
		}
	}
	store := stateStore{root: filepath.Clean(root), maxEvents: maxEvents, maxEventBytes: maxStoredEventBytes}
	if err := store.ensureStateVersion(); err != nil {
		return stateStore{}, err
	}
	return store, nil
}

func (s stateStore) ensureStateVersion() error {
	path := filepath.Join(s.root, "state-version.json")
	data, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		encoded, _ := json.Marshal(stateVersionRecord{Version: stateSchemaVersion})
		return atomicWrite(path, append(encoded, '\n'))
	}
	if err != nil {
		return fmt.Errorf("read run-plane state version: %w", err)
	}
	decoder := json.NewDecoder(strings.NewReader(string(data)))
	decoder.DisallowUnknownFields()
	var record stateVersionRecord
	if err := decoder.Decode(&record); err != nil {
		return fmt.Errorf("decode run-plane state version: %w", err)
	}
	var extra any
	if err := decoder.Decode(&extra); err != io.EOF {
		return fmt.Errorf("decode run-plane state version: trailing data")
	}
	switch record.Version {
	case stateSchemaVersion:
		return nil
	case 1, 2:
		encoded, _ := json.Marshal(stateVersionRecord{Version: stateSchemaVersion})
		if err := atomicWrite(path, append(encoded, '\n')); err != nil {
			return fmt.Errorf("migrate run-plane state version: %w", err)
		}
		return nil
	default:
		return fmt.Errorf("unsupported run-plane state version %d", record.Version)
	}
}

func (s stateStore) saveJob(job Job) error {
	data, err := json.MarshalIndent(job, "", "  ")
	if err != nil {
		return fmt.Errorf("encode job %q: %w", job.ID, err)
	}
	return atomicWrite(filepath.Join(s.root, "jobs", job.ID+".json"), append(data, '\n'))
}

func (s stateStore) loadJobs() (map[string]*Job, error) {
	entries, err := os.ReadDir(filepath.Join(s.root, "jobs"))
	if err != nil {
		return nil, fmt.Errorf("read job state: %w", err)
	}
	jobs := make(map[string]*Job, len(entries))
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".json") {
			continue
		}
		data, err := os.ReadFile(filepath.Join(s.root, "jobs", entry.Name()))
		if err != nil {
			return nil, fmt.Errorf("read job state %q: %w", entry.Name(), err)
		}
		var job Job
		if err := json.Unmarshal(data, &job); err != nil {
			return nil, fmt.Errorf("decode job state %q: %w", entry.Name(), err)
		}
		if job.APIVersion == "anvil.run-plane/v1" {
			job.APIVersion = APIVersion
			job.WorkflowDisposition = "uncertain"
			if job.RecoveryNote == "" {
				job.RecoveryNote = "migrated from anvil.run-plane/v1 without a control-plane admission bundle"
			}
			if err := s.saveJob(job); err != nil {
				return nil, fmt.Errorf("migrate job state %q: %w", entry.Name(), err)
			}
		}
		if job.APIVersion != APIVersion || job.ID == "" {
			return nil, fmt.Errorf("job state %q has an unsupported or missing identity", entry.Name())
		}
		copy := job
		jobs[job.ID] = &copy
	}
	return jobs, nil
}

func (s stateStore) appendEvent(event Event) error {
	events, err := s.events(event.JobID, 0)
	if err != nil && !os.IsNotExist(err) {
		return err
	}
	events = append(events, event)
	var lines [][]byte
	total := 0
	for _, item := range events {
		line, err := json.Marshal(item)
		if err != nil {
			return fmt.Errorf("encode event for job %q: %w", event.JobID, err)
		}
		line = append(line, '\n')
		lines = append(lines, line)
		total += len(line)
	}
	for len(lines) > 0 && (len(lines) > s.maxEvents || total > s.maxEventBytes) {
		total -= len(lines[0])
		lines = lines[1:]
	}
	if len(lines) == 0 {
		return fmt.Errorf("event for job %q exceeds bounded storage", event.JobID)
	}
	data := make([]byte, 0, total)
	for _, line := range lines {
		data = append(data, line...)
	}
	return atomicWrite(filepath.Join(s.root, "events", event.JobID+".jsonl"), data)
}

func (s stateStore) events(jobID string, after uint64) ([]Event, error) {
	file, err := os.Open(filepath.Join(s.root, "events", jobID+".jsonl"))
	if err != nil {
		return nil, err
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil {
		return nil, fmt.Errorf("stat events for job %q: %w", jobID, err)
	}
	if info.Size() > int64(s.maxEventBytes) {
		return nil, fmt.Errorf("events for job %q exceed bounded storage", jobID)
	}
	var events []Event
	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 4096), 1<<20)
	for scanner.Scan() {
		var event Event
		if err := json.Unmarshal(scanner.Bytes(), &event); err != nil {
			return nil, fmt.Errorf("decode event for job %q: %w", jobID, err)
		}
		if event.Sequence > after {
			events = append(events, event)
		}
	}
	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("read events for job %q: %w", jobID, err)
	}
	return events, nil
}

func (s stateStore) list(jobs map[string]*Job) []Job {
	out := make([]Job, 0, len(jobs))
	for _, job := range jobs {
		out = append(out, *job)
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].StartedAt.Equal(out[j].StartedAt) {
			return out[i].ID < out[j].ID
		}
		return out[i].StartedAt.Before(out[j].StartedAt)
	})
	return out
}

func atomicWrite(path string, data []byte) error {
	directory := filepath.Dir(path)
	file, err := os.CreateTemp(directory, ".runplane-*")
	if err != nil {
		return err
	}
	temporary := file.Name()
	defer os.Remove(temporary)
	if err := file.Chmod(0o600); err != nil {
		file.Close()
		return err
	}
	if _, err := file.Write(data); err != nil {
		file.Close()
		return err
	}
	if err := file.Sync(); err != nil {
		file.Close()
		return err
	}
	if err := file.Close(); err != nil {
		return err
	}
	return os.Rename(temporary, path)
}
