package runplane

import (
	"regexp"
	"strings"
)

var sensitiveValuePatterns = []*regexp.Regexp{
	regexp.MustCompile(`(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+`),
	regexp.MustCompile(`\b(?:sk|key|token)-[A-Za-z0-9_-]{8,}`),
	regexp.MustCompile(`(?i)(api[_-]?key|password|secret|token)\s*[=:]\s*[^\s,;]+`),
}

func redactValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		out := make(map[string]any, len(typed))
		for key, item := range typed {
			lower := strings.ToLower(key)
			if strings.Contains(lower, "token") || strings.Contains(lower, "secret") || strings.Contains(lower, "password") || strings.Contains(lower, "api_key") || strings.Contains(lower, "apikey") || strings.Contains(lower, "authorization") {
				out[key] = "[REDACTED]"
			} else {
				out[key] = redactValue(item)
			}
		}
		return out
	case []any:
		out := make([]any, len(typed))
		for index, item := range typed {
			out[index] = redactValue(item)
		}
		return out
	case string:
		if len(typed) > 16<<10 {
			typed = typed[:16<<10] + "[TRUNCATED]"
		}
		for _, pattern := range sensitiveValuePatterns {
			typed = pattern.ReplaceAllString(typed, "[REDACTED]")
		}
		return typed
	default:
		return value
	}
}
