// Package canonical exposes the repository-owned coding-fleet catalog.
package canonical

import _ "embed"

// catalogJSON is kept private so callers cannot mutate the embedded source.
//
//go:embed catalog.json
var catalogJSON []byte

// Bytes returns a copy of the canonical catalog document.
func Bytes() []byte {
	return append([]byte(nil), catalogJSON...)
}
