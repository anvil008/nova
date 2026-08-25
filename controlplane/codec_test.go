package controlplane

import (
	"errors"
	"testing"
)

func TestCodecRejectsDuplicateUnknownAndTrailingData(t *testing.T) {
	if _, err := CanonicalJSON([]byte(`{"a":1,"a":2}`)); !errors.Is(err, ErrDuplicateJSONKey) {
		t.Fatalf("duplicate key error = %v", err)
	}
	type closed struct {
		Value string `json:"value"`
	}
	var destination closed
	if err := DecodeStrict([]byte(`{"value":"ok","extra":true}`), &destination); err == nil {
		t.Fatal("unknown field accepted")
	}
	if err := DecodeStrict([]byte(`{"value":"ok"} {}`), &destination); err == nil {
		t.Fatal("trailing value accepted")
	}
}

func TestCodecCanonicalDigestIsOrderIndependent(t *testing.T) {
	left, err := CanonicalJSONDigest([]byte(`{"z":[2,1],"a":true}`))
	if err != nil {
		t.Fatal(err)
	}
	right, err := CanonicalJSONDigest([]byte(` { "a" : true, "z" : [2,1] } `))
	if err != nil {
		t.Fatal(err)
	}
	if left != right {
		t.Fatalf("canonical digests differ: %s != %s", left, right)
	}
}
