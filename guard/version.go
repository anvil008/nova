package guard

// Version is the semver single source of truth for the tdd-guard release, kept
// in step with plugins/claude/.claude-plugin/plugin.json and the release tag.
// It lives in Go source rather than only in ldflags so that a plain
// `go build ./...` still produces a binary that tells the truth about itself.
const Version = "0.6.0"

// BuildMetadata is optionally stamped at link time with
// -ldflags "-X github.com/anvil008/workcell/guard.BuildMetadata=<commit>".
var BuildMetadata string

// VersionString renders the release as Version plus any build metadata. The
// metadata appends and never replaces, so an unstamped build degrades to a
// correct "0.6.0" rather than to "dev" or the empty string.
func VersionString() string {
	if BuildMetadata == "" {
		return Version
	}
	return Version + "+" + BuildMetadata
}
