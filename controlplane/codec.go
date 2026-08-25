package controlplane

// The control-plane package is intentionally dependency neutral.  Contracts
// are exchanged between the native and foreign harnesses, so decoding must be
// fail closed before a caller gets a chance to interpret a partially valid
// value.

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"reflect"
	"sort"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"
)

const (
	// MaxContractBytes bounds every contract before it is decoded.  A contract
	// is metadata, not an artifact transport, and should remain small.
	MaxContractBytes = 1 << 20
	// MaxContractJSONDepth prevents a malicious document from consuming an
	// unbounded amount of stack while its canonical form is built.
	MaxContractJSONDepth = 64
	// CanonicalDigestPrefix is the stable prefix used for SHA-256 references.
	CanonicalDigestPrefix = "sha256-"
)

var (
	ErrInvalidContract    = errors.New("invalid control-plane contract")
	ErrContractTooLarge   = errors.New("control-plane contract exceeds size bound")
	ErrDuplicateJSONKey   = errors.New("duplicate JSON object key")
	ErrUnknownJSONField   = errors.New("unknown JSON object field")
	ErrInvalidContractVer = errors.New("invalid control-plane contract version")
	ErrInvalidDigest      = errors.New("invalid SHA-256 digest")
)

// CanonicalJSON validates raw JSON and returns a deterministic encoding.  It
// rejects duplicate keys, malformed UTF-8, excessive nesting, and trailing
// values.  Object keys are sorted by their UTF-8 byte sequence; array order is
// preserved.
func CanonicalJSON(raw []byte) ([]byte, error) {
	if len(raw) > MaxContractBytes {
		return nil, fmt.Errorf("%w: %d > %d bytes", ErrContractTooLarge, len(raw), MaxContractBytes)
	}
	if len(bytes.TrimSpace(raw)) == 0 {
		return nil, fmt.Errorf("%w: empty JSON document", ErrInvalidContract)
	}
	if !utf8.Valid(raw) {
		return nil, fmt.Errorf("%w: JSON is not valid UTF-8", ErrInvalidContract)
	}
	if err := validateSurrogateEscapes(raw); err != nil {
		return nil, err
	}

	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	value, err := decodeJSONValue(decoder, 0)
	if err != nil {
		return nil, err
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		if err == nil {
			return nil, fmt.Errorf("%w: trailing JSON value", ErrInvalidContract)
		}
		return nil, fmt.Errorf("%w: trailing JSON data: %v", ErrInvalidContract, err)
	}
	canonical, err := appendCanonicalJSON(nil, value)
	if err != nil {
		return nil, err
	}
	return canonical, nil
}

// CanonicalJSONDigest returns the SHA-256 digest of CanonicalJSON(raw).
func CanonicalJSONDigest(raw []byte) (string, error) {
	canonical, err := CanonicalJSON(raw)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(canonical)
	return CanonicalDigestPrefix + hex.EncodeToString(sum[:]), nil
}

// CanonicalDigest is a short alias used by contract callers.
func CanonicalDigest(raw []byte) (string, error) { return CanonicalJSONDigest(raw) }

// EncodeCanonical marshals a value and canonicalizes the resulting JSON.
func EncodeCanonical(value any) ([]byte, error) {
	if value == nil {
		return nil, fmt.Errorf("%w: nil value", ErrInvalidContract)
	}
	raw, err := json.Marshal(value)
	if err != nil {
		return nil, fmt.Errorf("%w: encode JSON: %v", ErrInvalidContract, err)
	}
	return CanonicalJSON(raw)
}

// DecodeStrict performs bounded, duplicate-free, trailing-free JSON decoding
// and rejects unknown struct fields.  Typed contracts add semantic validation
// after calling this helper.
func DecodeStrict(raw []byte, destination any) error {
	if destination == nil {
		return fmt.Errorf("%w: nil decode destination", ErrInvalidContract)
	}
	value := reflect.ValueOf(destination)
	if value.Kind() != reflect.Pointer || value.IsNil() {
		return fmt.Errorf("%w: decode destination must be a non-nil pointer", ErrInvalidContract)
	}
	if _, err := CanonicalJSON(raw); err != nil {
		return err
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(destination); err != nil {
		return fmt.Errorf("%w: decode JSON: %v", ErrInvalidContract, err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		if err == nil {
			return fmt.Errorf("%w: trailing JSON value", ErrInvalidContract)
		}
		return fmt.Errorf("%w: trailing JSON data: %v", ErrInvalidContract, err)
	}
	return nil
}

// ValidDigest reports whether value is a lowercase SHA-256 canonical digest.
func ValidDigest(value string) bool {
	if len(value) != len(CanonicalDigestPrefix)+sha256.Size*2 || !strings.HasPrefix(value, CanonicalDigestPrefix) {
		return false
	}
	if value != strings.ToLower(value) {
		return false
	}
	_, err := hex.DecodeString(strings.TrimPrefix(value, CanonicalDigestPrefix))
	return err == nil
}

// ValidateDigest validates a canonical digest and returns a descriptive error.
func ValidateDigest(value string) error {
	if !ValidDigest(value) {
		return fmt.Errorf("%w: %q", ErrInvalidDigest, value)
	}
	return nil
}

// ValidIdentifier accepts the bounded stable identifiers used for roles,
// envelopes, and graph nodes.  It deliberately excludes whitespace and path
// traversal syntax while allowing the role names already used by Swarm.
func ValidIdentifier(value string) bool {
	if len(value) == 0 || len(value) > 128 || value[0] < 'A' || value[0] > 'z' ||
		(value[0] > 'Z' && value[0] < 'a') {
		return false
	}
	for _, character := range value {
		switch {
		case character >= 'a' && character <= 'z':
		case character >= 'A' && character <= 'Z':
		case character >= '0' && character <= '9':
		case strings.ContainsRune("-_.:/@", character):
		default:
			return false
		}
	}
	return true
}

// ValidateIdentifier validates a stable identifier.
func ValidateIdentifier(value string) error {
	if !ValidIdentifier(value) {
		return fmt.Errorf("%w: invalid identifier %q", ErrInvalidContract, value)
	}
	return nil
}

// ValidateTimestamp accepts RFC3339 timestamps with nanosecond precision.  A
// timestamp must carry an explicit offset and cannot be the zero time.
func ValidateTimestamp(value string) error {
	if value == "" {
		return fmt.Errorf("%w: timestamp is required", ErrInvalidContract)
	}
	timestamp, err := time.Parse(time.RFC3339Nano, value)
	if err != nil || timestamp.IsZero() {
		return fmt.Errorf("%w: invalid timestamp %q", ErrInvalidContract, value)
	}
	return nil
}

// canonicalWithoutField returns the canonical object digest payload after
// removing one top-level field, normally the self-referential "digest" field.
func canonicalWithoutField(value any, field string) ([]byte, error) {
	raw, err := json.Marshal(value)
	if err != nil {
		return nil, fmt.Errorf("%w: encode digest payload: %v", ErrInvalidContract, err)
	}
	if len(raw) > MaxContractBytes {
		return nil, fmt.Errorf("%w: digest payload exceeds size bound", ErrContractTooLarge)
	}
	var object map[string]json.RawMessage
	if err := DecodeStrict(raw, &object); err != nil {
		return nil, err
	}
	if _, ok := object[field]; !ok {
		return nil, fmt.Errorf("%w: digest field %q is absent from payload", ErrInvalidContract, field)
	}
	delete(object, field)
	without, err := json.Marshal(object)
	if err != nil {
		return nil, fmt.Errorf("%w: encode digest payload: %v", ErrInvalidContract, err)
	}
	return CanonicalJSON(without)
}

func digestWithoutField(value any, field string) (string, error) {
	canonical, err := canonicalWithoutField(value, field)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(canonical)
	return CanonicalDigestPrefix + hex.EncodeToString(sum[:]), nil
}

type canonicalJSONObject map[string]any
type canonicalJSONNumber string

func decodeJSONValue(decoder *json.Decoder, depth int) (any, error) {
	if depth > MaxContractJSONDepth {
		return nil, fmt.Errorf("%w: JSON nesting exceeds %d levels", ErrInvalidContract, MaxContractJSONDepth)
	}
	token, err := decoder.Token()
	if err != nil {
		return nil, fmt.Errorf("%w: malformed JSON: %v", ErrInvalidContract, err)
	}
	switch value := token.(type) {
	case json.Delim:
		switch value {
		case '{':
			object := make(canonicalJSONObject)
			for decoder.More() {
				keyToken, err := decoder.Token()
				if err != nil {
					return nil, fmt.Errorf("%w: malformed object key: %v", ErrInvalidContract, err)
				}
				key, ok := keyToken.(string)
				if !ok {
					return nil, fmt.Errorf("%w: object key is not a string", ErrInvalidContract)
				}
				if _, duplicate := object[key]; duplicate {
					return nil, fmt.Errorf("%w %q", ErrDuplicateJSONKey, key)
				}
				child, err := decodeJSONValue(decoder, depth+1)
				if err != nil {
					return nil, err
				}
				object[key] = child
			}
			closing, err := decoder.Token()
			if err != nil || closing != json.Delim('}') {
				return nil, fmt.Errorf("%w: malformed JSON object", ErrInvalidContract)
			}
			return object, nil
		case '[':
			array := make([]any, 0)
			for decoder.More() {
				child, err := decodeJSONValue(decoder, depth+1)
				if err != nil {
					return nil, err
				}
				array = append(array, child)
			}
			closing, err := decoder.Token()
			if err != nil || closing != json.Delim(']') {
				return nil, fmt.Errorf("%w: malformed JSON array", ErrInvalidContract)
			}
			return array, nil
		default:
			return nil, fmt.Errorf("%w: unexpected JSON delimiter %q", ErrInvalidContract, value)
		}
	case json.Number:
		if err := validateJSONNumber(value.String()); err != nil {
			return nil, err
		}
		return canonicalJSONNumber(value), nil
	case string, bool, nil:
		return value, nil
	default:
		return nil, fmt.Errorf("%w: unsupported JSON token", ErrInvalidContract)
	}
}

func validateJSONNumber(value string) error {
	if len(value) == 0 || len(value) > 256 {
		return fmt.Errorf("%w: JSON number has an unsafe size", ErrInvalidContract)
	}
	parsed, err := strconv.ParseFloat(value, 64)
	if err != nil || math.IsNaN(parsed) || math.IsInf(parsed, 0) {
		return fmt.Errorf("%w: JSON number %q is outside the supported range", ErrInvalidContract, value)
	}
	return nil
}

func appendCanonicalJSON(destination []byte, value any) ([]byte, error) {
	switch typed := value.(type) {
	case canonicalJSONObject:
		keys := make([]string, 0, len(typed))
		for key := range typed {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		destination = append(destination, '{')
		for index, key := range keys {
			if index > 0 {
				destination = append(destination, ',')
			}
			var err error
			destination, err = appendCanonicalJSONString(destination, key)
			if err != nil {
				return nil, err
			}
			destination = append(destination, ':')
			destination, err = appendCanonicalJSON(destination, typed[key])
			if err != nil {
				return nil, err
			}
		}
		return append(destination, '}'), nil
	case []any:
		destination = append(destination, '[')
		for index, child := range typed {
			if index > 0 {
				destination = append(destination, ',')
			}
			var err error
			destination, err = appendCanonicalJSON(destination, child)
			if err != nil {
				return nil, err
			}
		}
		return append(destination, ']'), nil
	case string:
		return appendCanonicalJSONString(destination, typed)
	case canonicalJSONNumber:
		return append(destination, string(typed)...), nil
	case bool:
		if typed {
			return append(destination, "true"...), nil
		}
		return append(destination, "false"...), nil
	case nil:
		return append(destination, "null"...), nil
	default:
		return nil, fmt.Errorf("%w: unsupported canonical value", ErrInvalidContract)
	}
}

func appendCanonicalJSONString(destination []byte, value string) ([]byte, error) {
	encoded, err := json.Marshal(value)
	if err != nil {
		return nil, fmt.Errorf("%w: encode JSON string: %v", ErrInvalidContract, err)
	}
	return append(destination, encoded...), nil
}

func validateSurrogateEscapes(raw []byte) error {
	inString := false
	for index := 0; index < len(raw); index++ {
		if !inString {
			if raw[index] == '"' {
				inString = true
			}
			continue
		}
		if raw[index] == '"' {
			inString = false
			continue
		}
		if raw[index] != '\\' || index+1 >= len(raw) {
			continue
		}
		if raw[index+1] != 'u' {
			index++
			continue
		}
		if index+5 >= len(raw) {
			return fmt.Errorf("%w: incomplete Unicode escape", ErrInvalidContract)
		}
		unit, ok := hexUnit(raw[index+2 : index+6])
		if !ok {
			return fmt.Errorf("%w: invalid Unicode escape", ErrInvalidContract)
		}
		switch {
		case unit >= 0xD800 && unit <= 0xDBFF:
			if index+11 >= len(raw) || raw[index+6] != '\\' || raw[index+7] != 'u' {
				return fmt.Errorf("%w: unpaired high surrogate", ErrInvalidContract)
			}
			low, ok := hexUnit(raw[index+8 : index+12])
			if !ok || low < 0xDC00 || low > 0xDFFF {
				return fmt.Errorf("%w: unpaired high surrogate", ErrInvalidContract)
			}
			index += 11
		case unit >= 0xDC00 && unit <= 0xDFFF:
			return fmt.Errorf("%w: unpaired low surrogate", ErrInvalidContract)
		default:
			index += 5
		}
	}
	return nil
}

func hexUnit(raw []byte) (rune, bool) {
	if len(raw) != 4 {
		return 0, false
	}
	var value rune
	for _, character := range raw {
		value <<= 4
		switch {
		case character >= '0' && character <= '9':
			value += rune(character - '0')
		case character >= 'a' && character <= 'f':
			value += rune(character-'a') + 10
		case character >= 'A' && character <= 'F':
			value += rune(character-'A') + 10
		default:
			return 0, false
		}
	}
	return value, true
}
