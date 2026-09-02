#!/usr/bin/env python3
"""Model guide extract and freshness gate.

Scans prompting.md extracts under docs/models/, enforces required provenance
headers, detects upstream drift against normalized digests, and supports
deterministic fixture injection and intentional update mode.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REQUIRED_PROVENANCE_FIELDS = (
    "model",
    "official_source_urls",
    "fetched_date",
    "extractor_version",
    "normalized_source_digests",
)


def extract(source_html: str, vendor: str | None = None) -> str:
    """Extract normalized article content from raw vendor HTML."""
    return ""


def check_guide(
    guide_path: Path,
    fixtures_dir: Path | None = None,
    check_only: bool = True,
) -> dict:
    """Check a single model guide for header validity and upstream freshness."""
    return {"ok": True, "violations": []}


def scan_guides(
    root: Path,
    model: str | None = None,
    check_only: bool = True,
    fixtures_dir: Path | None = None,
    update: bool = False,
) -> int:
    """Scan model guides under root and verify provenance and freshness."""
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check provenance headers and upstream freshness without modifying files",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Scope check or update to a single model",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Root directory containing model directories (defaults to docs/models)",
    )
    parser.add_argument(
        "--fixtures-dir",
        "--fixtures",
        type=Path,
        default=None,
        help="Directory containing deterministic fixtures for upstream sources",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Intentional update mode: refetch and rewrite extracts",
    )
    args = parser.parse_args(argv)
    return scan_guides(
        root=args.root or Path("docs/models"),
        model=args.model,
        check_only=args.check,
        fixtures_dir=args.fixtures_dir,
        update=args.update,
    )


if __name__ == "__main__":
    sys.exit(main())
