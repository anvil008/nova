#!/usr/bin/env python3
"""Generate or verify all harness-owned skill families."""

from __future__ import annotations

import argparse
import sys

from harness_generation import GenerationError, sync


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="report drift, write nothing"
    )
    parser.add_argument(
        "--diff", action="store_true", help="with --check, explain drift"
    )
    args = parser.parse_args()
    return sync("skills", check=args.check, diff=args.diff)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except GenerationError as error:
        print(f"sync-skills: {error}", file=sys.stderr)
        sys.exit(2)
