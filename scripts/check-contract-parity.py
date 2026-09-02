#!/usr/bin/env python3
"""Verify every harness carries the same strict Workcell contracts."""

from __future__ import annotations

import sys

from harness_generation import GenerationError, check_parity

if __name__ == "__main__":
    try:
        sys.exit(check_parity())
    except GenerationError as error:
        print(f"contract-parity: {error}", file=sys.stderr)
        sys.exit(2)
