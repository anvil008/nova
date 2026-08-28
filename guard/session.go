package guard

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"syscall"
)

// sessionsDirectory holds one touch log per harness session. A session routinely
// writes into a repository it is not standing in, so the shell and Stop checks
// need a record of where its edits actually landed.
const sessionsDirectory = "sessions"

// maxTouchedRepositories bounds one session's log. A coding session touches a
// handful of trees; anything beyond this is noise, not evidence.
const maxTouchedRepositories = 64

type touchLog struct {
	Repositories []string `json:"repositories"`
}

func touchLogPath(session string) (string, error) {
	base, err := stateBaseDirectory()
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256([]byte(session))
	return filepath.Join(base, sessionsDirectory, hex.EncodeToString(sum[:])+".json"), nil
}

// recordTouchedRepositories adds sealed repositories to a session's log. Only
// sealed repositories are recorded, so a non-fleet session writes nothing.
func recordTouchedRepositories(session string, repositories []string) error {
	if session == "" || len(repositories) == 0 {
		return nil
	}
	pathname, err := touchLogPath(session)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(pathname), 0o700); err != nil {
		return err
	}
	lock, err := os.OpenFile(pathname+".lock", os.O_CREATE|os.O_RDWR, 0o600)
	if err != nil {
		return err
	}
	defer lock.Close()
	if err := syscall.Flock(int(lock.Fd()), syscall.LOCK_EX); err != nil {
		return err
	}
	defer func() { _ = syscall.Flock(int(lock.Fd()), syscall.LOCK_UN) }()
	existing, err := readJSON[touchLog](pathname)
	if err != nil {
		return err
	}
	merged := map[string]struct{}{}
	if existing != nil {
		for _, repository := range existing.Repositories {
			merged[repository] = struct{}{}
		}
	}
	before := len(merged)
	for _, repository := range repositories {
		if len(merged) >= maxTouchedRepositories {
			break
		}
		merged[repository] = struct{}{}
	}
	if len(merged) == before {
		return nil
	}
	ordered := make([]string, 0, len(merged))
	for repository := range merged {
		ordered = append(ordered, repository)
	}
	sort.Strings(ordered)
	return writeJSON(pathname, touchLog{Repositories: ordered})
}

func touchedRepositories(session string) []string {
	if session == "" {
		return nil
	}
	pathname, err := touchLogPath(session)
	if err != nil {
		return nil
	}
	log, err := readJSON[touchLog](pathname)
	if err != nil || log == nil {
		return nil
	}
	return log.Repositories
}

// anySealExists reports whether any repository on this machine is under seal.
// It is only consulted when the payload could not be read at all: the guard
// then cannot tell which repository the tool would write, so the presence of
// any live seal is what turns the refusal on. With no seal anywhere the fast
// path still leaves every unrelated session untouched.
func anySealExists() (bool, error) {
	base, err := stateBaseDirectory()
	if err != nil {
		return false, err
	}
	entries, err := os.ReadDir(base)
	if errors.Is(err, fs.ErrNotExist) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		if _, err := os.Stat(filepath.Join(base, entry.Name(), sealFileName)); err == nil {
			return true, nil
		}
	}
	return false, nil
}

// repositoryForPath resolves the repository that owns a path a tool would
// write. The path may be relative to the session, absolute, routed through a
// symlink, or not exist yet, so resolution starts from the nearest existing
// ancestor of the resolved target.
func (cache *lookups) repositoryForPath(workingDirectory, candidate string) (string, bool) {
	trimmed := filepath.FromSlash(strings.TrimSpace(candidate))
	if trimmed == "" {
		return "", false
	}
	absolute := absoluteTarget(workingDirectory, trimmed)
	if absolute == "" {
		return "", false
	}
	directory := filepath.Dir(resolveSymlinks(absolute))
	for {
		if info, err := os.Stat(directory); err == nil && info.IsDir() {
			break
		}
		parent := filepath.Dir(directory)
		if parent == directory {
			return "", false
		}
		directory = parent
	}
	if repository, known := cache.repositories[directory]; known {
		return repository, repository != ""
	}
	repository, err := repositoryRoot(directory)
	if err != nil {
		repository = ""
	}
	cache.repositories[directory] = repository
	return repository, repository != ""
}

// lookups memoizes the two resolutions a hook repeats for every written path:
// which repository owns a directory, and what that repository's guard state is.
// A single apply_patch envelope can name a dozen files in one directory.
type lookups struct {
	repositories map[string]string
	states       map[string]*state
}

func newLookups() *lookups {
	return &lookups{repositories: map[string]string{}, states: map[string]*state{}}
}

func (cache *lookups) load(repository string) *state {
	if loaded, known := cache.states[repository]; known {
		return loaded
	}
	loaded, err := loadRepositoryState(repository)
	if err != nil {
		loaded = nil
	}
	cache.states[repository] = loaded
	return loaded
}

// scope is every sealed repository one hook invocation must judge.
type scope struct {
	// repository is the session's own repository, empty when it is not in one.
	repository string
	states     []*state
}

// qualify names the repository whenever a message is not about the one the
// session is standing in, so a Stop refusal is actionable from anywhere.
func (s scope) qualify(loaded *state, message string) string {
	if loaded.repository == s.repository {
		return message
	}
	return loaded.repository + ": " + message
}

func sessionScope(decoded payload, workingDirectory string) scope {
	cache := newLookups()
	resolved := scope{}
	candidates := make([]string, 0, 4)
	if repository, err := repositoryRoot(workingDirectory); err == nil {
		resolved.repository = repository
		candidates = append(candidates, repository)
	}
	candidates = append(candidates, touchedRepositories(decoded.session())...)
	seen := make(map[string]struct{}, len(candidates))
	for _, repository := range candidates {
		if _, duplicate := seen[repository]; duplicate {
			continue
		}
		seen[repository] = struct{}{}
		if loaded := cache.load(repository); loaded != nil && loaded.seal != nil {
			resolved.states = append(resolved.states, loaded)
		}
	}
	return resolved
}
