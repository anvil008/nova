#!/usr/bin/env python3
"""Model guide extract and freshness gate.

Scans prompting.md extracts under docs/models/, enforces required provenance
headers, detects upstream drift against normalized digests, and supports
deterministic fixture injection and intentional update mode.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import hashlib
import http.client
import io
import json
import socket
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

# Default network timeout limits to prevent indefinite CI hangs.
DEFAULT_REQUEST_TIMEOUT = 15.0
DEFAULT_MODEL_DEADLINE = 60.0
MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MiB
MAX_REDIRECTS = 5

# Set process socket default timeout so newly created sockets cannot hang indefinitely.
socket.setdefaulttimeout(DEFAULT_REQUEST_TIMEOUT)

# Bumped whenever normalization changes what text a digest covers. Digests are
# only comparable within one extractor version.
EXTRACTOR_VERSION = "1.1.0"

REQUIRED_PROVENANCE_FIELDS = (
    "model",
    "official_source_urls",
    "fetched_date",
    "extractor_version",
    "normalized_source_digests",
)


class ExtractionError(Exception):
    """Raised when extracting normalized content from HTML fails."""


class FetchError(Exception):
    """Raised when fetching upstream content fails."""


class BoundedRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Redirect handler that bounds redirect count and closes bodies to prevent hangs."""

    def __init__(self, max_redirections: int = MAX_REDIRECTS) -> None:
        super().__init__()
        self.max_redirections = max_redirections

    def http_error_302(self, req, fp, code, msg, headers):
        if fp is not None:
            with contextlib.suppress(OSError):
                fp.close()
        return super().http_error_302(req, io.BytesIO(), code, msg, headers)

    http_error_301 = http_error_302
    http_error_303 = http_error_302
    http_error_307 = http_error_302
    http_error_308 = http_error_302


def create_opener(max_redirects: int = MAX_REDIRECTS) -> urllib.request.OpenerDirector:
    """Create a urllib OpenerDirector with bounded redirects."""
    handler = BoundedRedirectHandler(max_redirections=max_redirects)
    return urllib.request.build_opener(handler)


class ArticleExtractor(HTMLParser):
    """HTML parser to extract text from article/main content containers."""

    def __init__(self, vendor: str | None = None) -> None:
        super().__init__()
        self.vendor = vendor
        self.found_container = False
        self.container_tag: str | None = None
        self.container_depth = 0
        self.ignored_tags = {"script", "style", "noscript", "svg", "head"}
        self.current_ignored_depth = 0
        self.skipped_tag: str | None = None
        self.skipped_depth = 0
        self.text_chunks: list[str] = []

    def _is_consent_chrome(self, attrs: list[tuple[str, str | None]]) -> bool:
        """Detect a cookie/consent banner subtree.

        Vendors render these banners server-side and condition them on the
        requester's IP country, so a banner caught by the container selector
        would make the normalized digest depend on where the checker runs.
        The banner is site chrome, never guidance, so it is dropped outright.
        """
        haystack = " ".join(
            (v or "").lower()
            for k, v in attrs
            if k.lower() in ("class", "id", "data-testid")
        )
        return any(
            marker in haystack
            for marker in (
                "consent-banner",
                "consentbanner",
                "cookie-banner",
                "cookiebanner",
                "cookie-consent",
                "cookieconsent",
                "onetrust",
            )
        )

    def _is_container_start(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> bool:
        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        if tag in ("article", "main", "devsite-content", "devsite-article-body"):
            return True
        if attr_dict.get("role") == "main":
            return True
        class_val = attr_dict.get("class", "").lower()
        if self.vendor == "openai" and "docs-content" in class_val:
            return True
        if self.vendor == "anthropic" and "content" in class_val:
            return True
        return bool(self.vendor == "google" and "devsite" in class_val)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self.ignored_tags:
            self.current_ignored_depth += 1
            return

        if self.skipped_tag is not None:
            if tag == self.skipped_tag:
                self.skipped_depth += 1
            return

        if self._is_consent_chrome(attrs):
            self.skipped_tag = tag
            self.skipped_depth = 1
            return

        if not self.found_container:
            if self._is_container_start(tag, attrs):
                self.found_container = True
                self.container_tag = tag
                self.container_depth = 1
        elif self.found_container:
            if tag == self.container_tag:
                self.container_depth += 1
            if (
                tag
                in (
                    "p",
                    "h1",
                    "h2",
                    "h3",
                    "h4",
                    "h5",
                    "h6",
                    "div",
                    "li",
                    "blockquote",
                    "br",
                    "section",
                )
                and self.text_chunks
                and not self.text_chunks[-1].endswith("\n")
            ):
                self.text_chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.ignored_tags:
            if self.current_ignored_depth > 0:
                self.current_ignored_depth -= 1
            return

        if self.skipped_tag is not None:
            if tag == self.skipped_tag:
                self.skipped_depth -= 1
                if self.skipped_depth <= 0:
                    self.skipped_tag = None
                    self.skipped_depth = 0
            return

        if self.found_container:
            if (
                tag
                in (
                    "p",
                    "h1",
                    "h2",
                    "h3",
                    "h4",
                    "h5",
                    "h6",
                    "div",
                    "li",
                    "blockquote",
                    "section",
                )
                and self.text_chunks
                and not self.text_chunks[-1].endswith("\n")
            ):
                self.text_chunks.append("\n")
            if tag == self.container_tag:
                self.container_depth -= 1

    def handle_data(self, data: str) -> None:
        if (
            self.found_container
            and self.container_depth > 0
            and self.current_ignored_depth == 0
            and self.skipped_tag is None
        ):
            self.text_chunks.append(data)

    def get_text(self) -> str:
        raw = "".join(self.text_chunks)
        lines = [line.strip() for line in raw.splitlines()]
        result_lines: list[str] = []
        for line in lines:
            if line:
                result_lines.append(line)
            elif result_lines and result_lines[-1] != "":
                result_lines.append("")
        return "\n".join(result_lines).strip()


def detect_vendor(url: str, model: str | None = None) -> str:
    url_lower = url.lower()
    model_lower = (model or "").lower()
    if "openai.com" in url_lower or "gpt" in model_lower:
        return "openai"
    if "anthropic.com" in url_lower or "claude" in model_lower:
        return "anthropic"
    if (
        "google.com" in url_lower
        or "google.dev" in url_lower
        or "gemini" in model_lower
    ):
        return "google"
    return "generic"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract(source_html: str, vendor: str | None = None) -> str:
    """Extract normalized article content from raw vendor HTML."""
    if not source_html or not isinstance(source_html, str):
        raise ExtractionError("Empty or invalid source HTML")

    parser = ArticleExtractor(vendor=vendor)
    parser.feed(source_html)
    if not parser.found_container:
        raise ExtractionError(
            "Missing article selector: no article or main content container found in HTML"
        )
    text = parser.get_text()
    if not text:
        raise ExtractionError(
            "Extraction failure: article content is empty after extraction"
        )
    return text


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML-style frontmatter from markdown file."""
    if not content.startswith("---"):
        raise ValueError("Missing frontmatter opening '---'")

    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError("Missing frontmatter closing '---'")

    fm_text = parts[1]
    body = parts[2].removeprefix("\n")

    fields: dict = {}
    lines = fm_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        if ":" in stripped:
            key, val = stripped.split(":", 1)
            key = key.strip()
            val = val.strip()

            if val != "":
                if (val.startswith('"') and val.endswith('"')) or (
                    val.startswith("'") and val.endswith("'")
                ):
                    val = val[1:-1]
                fields[key] = val
                i += 1
            else:
                i += 1
                items_list: list[str] = []
                items_dict: dict[str, str] = {}
                is_list = False
                is_dict = False
                while i < len(lines):
                    sub_line = lines[i]
                    if not sub_line.strip():
                        i += 1
                        continue
                    if not sub_line.startswith(("  ", "\t")):
                        break
                    sub_stripped = sub_line.strip()
                    if sub_stripped.startswith("- "):
                        is_list = True
                        item_val = sub_stripped[2:].strip()
                        if (item_val.startswith('"') and item_val.endswith('"')) or (
                            item_val.startswith("'") and item_val.endswith("'")
                        ):
                            item_val = item_val[1:-1]
                        items_list.append(item_val)
                    elif ":" in sub_stripped:
                        is_dict = True
                        sub_k, sub_v = sub_stripped.rsplit(":", 1)
                        sub_k = sub_k.strip()
                        sub_v = sub_v.strip()
                        if (sub_v.startswith('"') and sub_v.endswith('"')) or (
                            sub_v.startswith("'") and sub_v.endswith("'")
                        ):
                            sub_v = sub_v[1:-1]
                        items_dict[sub_k] = sub_v
                    i += 1

                if is_list:
                    fields[key] = items_list
                elif is_dict:
                    fields[key] = items_dict
                else:
                    fields[key] = ""
        else:
            i += 1

    return fields, body


def render_frontmatter(fields: dict) -> str:
    """Render fields dict into YAML frontmatter."""
    lines = ["---"]
    for key, val in fields.items():
        if isinstance(val, list):
            lines.append(f"{key}:")
            for item in val:
                lines.append(f"  - {item}")
        elif isinstance(val, dict):
            lines.append(f"{key}:")
            for k, v in val.items():
                lines.append(f"  {k}: {v}")
        else:
            lines.append(f"{key}: {val}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def extract_passages(markdown_body: str) -> list[str]:
    """Extract blockquote passages from markdown body."""
    passages: list[str] = []
    current_lines: list[str] = []
    for line in markdown_body.splitlines():
        stripped = line.strip()
        if stripped.startswith(">"):
            text = stripped.lstrip(">").strip()
            if text:
                current_lines.append(text)
        else:
            if current_lines:
                passages.append(" ".join(current_lines))
                current_lines = []
    if current_lines:
        passages.append(" ".join(current_lines))
    return passages


def fetch_upstream(
    url: str,
    fixtures_dir: Path | None = None,
    timeout: float = DEFAULT_REQUEST_TIMEOUT,
    deadline: float | None = None,
    max_bytes: int = MAX_RESPONSE_BYTES,
    opener: urllib.request.OpenerDirector | None = None,
) -> str:
    """Fetch content from deterministic fixtures or live network."""
    if fixtures_dir is not None:
        fixtures_file = fixtures_dir / "fixtures.json"
        if not fixtures_file.exists():
            raise FetchError(f"Fixtures file not found: {fixtures_file}")
        try:
            fixtures = json.loads(fixtures_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            raise FetchError(f"Failed to read fixtures JSON: {e}") from e

        if url not in fixtures:
            raise FetchError(f"URL '{url}' not found in fixtures at {fixtures_file}")

        entry = fixtures[url]
        if entry.get("error"):
            raise FetchError(f"Timeout/fetch error: {entry['error']}")

        status = entry.get("status", 200)
        if status != 200:
            raise FetchError(f"HTTP status {status} fetch error for URL '{url}'")

        content = entry.get("content", "")
        if len(content.encode("utf-8")) > max_bytes:
            raise FetchError(
                f"Response size exceeded limit ({max_bytes} bytes) for URL '{url}'"
            )
        return content

    now = time.monotonic()
    if deadline is not None and now >= deadline:
        raise FetchError(
            f"Timeout fetching URL '{url}': overall deadline exceeded before request start"
        )

    effective_timeout = timeout
    if deadline is not None:
        remaining = deadline - now
        if remaining <= 0:
            raise FetchError(f"Timeout fetching URL '{url}': overall deadline exceeded")
        effective_timeout = min(timeout, remaining)

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "NovaGuideChecker/1.0 (+https://github.com/anvil008/nova)"
        },
    )

    actual_opener = opener or create_opener()

    try:
        with actual_opener.open(req, timeout=effective_timeout) as resp:
            status = getattr(resp, "status", None) or getattr(resp, "code", 200)
            if status != 200:
                raise FetchError(f"HTTP status {status} fetch error for URL '{url}'")

            chunks: list[bytes] = []
            total_bytes = 0
            chunk_size = 64 * 1024

            while True:
                current_time = time.monotonic()
                if deadline is not None:
                    rem = deadline - current_time
                    if rem <= 0:
                        raise FetchError(
                            f"Timeout fetching URL '{url}': overall deadline exceeded during read"
                        )
                    with contextlib.suppress(AttributeError, OSError):
                        sock = getattr(resp, "fp", None)
                        if (
                            sock
                            and hasattr(sock, "raw")
                            and hasattr(sock.raw, "_sock")
                            and sock.raw._sock
                        ):
                            sock.raw._sock.settimeout(min(effective_timeout, rem))

                read_fn = getattr(resp, "read1", resp.read)
                chunk = read_fn(chunk_size)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise FetchError(
                        f"Response size ({total_bytes} bytes) exceeded limit ({max_bytes} bytes) for URL '{url}'"
                    )
                chunks.append(chunk)

            return b"".join(chunks).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raise FetchError(
            f"HTTP status {e.code} fetch error for URL '{url}': {e.reason}"
        ) from e
    except urllib.error.URLError as e:
        raise FetchError(
            f"Network error/timeout fetching URL '{url}': {e.reason}"
        ) from e
    except TimeoutError as e:
        raise FetchError(f"Timeout fetching URL '{url}': {e}") from e
    except (http.client.HTTPException, OSError) as e:
        raise FetchError(f"Failed to fetch URL '{url}': {e}") from e


def check_guide(
    guide_path: Path,
    fixtures_dir: Path | None = None,
    check_only: bool = True,
    timeout: float = DEFAULT_REQUEST_TIMEOUT,
    model_deadline: float = DEFAULT_MODEL_DEADLINE,
    max_bytes: int = MAX_RESPONSE_BYTES,
    opener: urllib.request.OpenerDirector | None = None,
) -> dict:
    """Check a single model guide for header validity and upstream freshness."""
    violations: list[str] = []

    if not guide_path.exists():
        return {
            "ok": False,
            "violations": [f"File not found: {guide_path}"],
            "file": str(guide_path),
        }

    try:
        content = guide_path.read_text(encoding="utf-8")
        fields, body = parse_frontmatter(content)
    except (ValueError, OSError) as e:
        return {
            "ok": False,
            "violations": [
                f"Error in {guide_path.name} ({guide_path}): invalid frontmatter: {e}"
            ],
            "file": str(guide_path),
        }

    # 1. Check required provenance fields
    for field in REQUIRED_PROVENANCE_FIELDS:
        if field not in fields:
            violations.append(
                f"Error in {guide_path.name} ({guide_path}): missing required provenance field '{field}'"
            )

    if violations:
        return {
            "ok": False,
            "violations": violations,
            "file": str(guide_path),
        }

    model = fields.get("model", "")
    urls = fields.get("official_source_urls", [])
    if isinstance(urls, str):
        urls = [urls]

    stored_digests = fields.get("normalized_source_digests", {})
    if not isinstance(stored_digests, dict):
        stored_digests = {}

    start_time = time.monotonic()
    deadline = start_time + model_deadline
    extracted_articles: dict[str, str] = {}

    # 2. Fetch and extract each upstream URL
    for url in urls:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            violations.append(
                f"Fetch failure for model '{model}', URL '{url}': "
                f"model deadline ({model_deadline}s) exceeded"
            )
            continue

        vendor = detect_vendor(url, model)
        try:
            raw_html = fetch_upstream(
                url,
                fixtures_dir=fixtures_dir,
                timeout=min(timeout, remaining),
                deadline=deadline,
                max_bytes=max_bytes,
                opener=opener,
            )
        except FetchError as fe:
            violations.append(f"Fetch failure for model '{model}', URL '{url}': {fe}")
            continue

        try:
            article_text = extract(raw_html, vendor=vendor)
            extracted_articles[url] = article_text
        except ExtractionError as ee:
            violations.append(
                f"Extraction failure for model '{model}', URL '{url}': {ee}"
            )
            continue

        # 3. Check digest freshness
        current_digest = sha256_text(article_text)
        stored_digest = stored_digests.get(url)
        if stored_digest != current_digest:
            violations.append(
                f"Upstream content drift detected for model '{model}', URL '{url}': "
                f"normalized source digest mismatch (stored: {stored_digest}, current: {current_digest})"
            )

    has_fetch_or_extraction_failure = any(
        v.startswith(
            (
                f"Fetch failure for model '{model}'",
                f"Extraction failure for model '{model}'",
            )
        )
        for v in violations
    )
    if has_fetch_or_extraction_failure:
        return {
            "ok": False,
            "violations": violations,
            "file": str(guide_path),
        }

    # 4. Check selected passages against upstream extracted content
    passages = extract_passages(body)
    all_extracted_text = " ".join(extracted_articles.values())
    normalized_corpus = " ".join(all_extracted_text.split())

    for passage in passages:
        norm_passage = " ".join(passage.split())
        if norm_passage not in normalized_corpus:
            url_names = ", ".join(urls)
            violations.append(
                f"Selected passage drift detected for model '{model}', URL '{url_names}': "
                f'passage not found in upstream content: "{passage}"'
            )

    return {
        "ok": len(violations) == 0,
        "violations": violations,
        "file": str(guide_path),
    }


def update_guide(
    guide_path: Path,
    fixtures_dir: Path | None = None,
    timeout: float = DEFAULT_REQUEST_TIMEOUT,
    model_deadline: float = DEFAULT_MODEL_DEADLINE,
    max_bytes: int = MAX_RESPONSE_BYTES,
    opener: urllib.request.OpenerDirector | None = None,
) -> dict:
    """Update a model guide by refetching sources and updating provenance digests."""
    content = guide_path.read_text(encoding="utf-8")
    fields, body = parse_frontmatter(content)
    model = fields.get("model", "")
    urls = fields.get("official_source_urls", [])
    if isinstance(urls, str):
        urls = [urls]

    start_time = time.monotonic()
    deadline = start_time + model_deadline
    new_digests: dict[str, str] = {}
    for url in urls:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise FetchError(
                f"Timeout fetching URL '{url}': model deadline ({model_deadline}s) exceeded"
            )
        vendor = detect_vendor(url, model)
        raw_html = fetch_upstream(
            url,
            fixtures_dir=fixtures_dir,
            timeout=min(timeout, remaining),
            deadline=deadline,
            max_bytes=max_bytes,
            opener=opener,
        )
        article_text = extract(raw_html, vendor=vendor)
        new_digests[url] = sha256_text(article_text)

    fields["fetched_date"] = (
        datetime.datetime.now(tz=datetime.timezone.utc).date().isoformat()
    )
    fields["extractor_version"] = EXTRACTOR_VERSION
    fields["normalized_source_digests"] = new_digests

    updated_content = render_frontmatter(fields) + body
    guide_path.write_text(updated_content, encoding="utf-8")
    return {"ok": True, "file": str(guide_path)}


def scan_guides(
    root: Path,
    model: str | None = None,
    check_only: bool = True,
    fixtures_dir: Path | None = None,
    update: bool = False,
    timeout: float = DEFAULT_REQUEST_TIMEOUT,
    model_deadline: float = DEFAULT_MODEL_DEADLINE,
    max_bytes: int = MAX_RESPONSE_BYTES,
    opener: urllib.request.OpenerDirector | None = None,
) -> int:
    """Scan model guides under root and verify provenance and freshness."""
    if not root.exists():
        print(f"Error: root path '{root}' does not exist", file=sys.stderr)
        return 1

    if model:
        guide_paths = [root / model / "prompting.md"]
        if not guide_paths[0].exists():
            if (root / "prompting.md").exists():
                guide_paths = [root / "prompting.md"]
            else:
                print(
                    f"Error: prompting.md not found for model '{model}' under {root}",
                    file=sys.stderr,
                )
                return 1
    else:
        if (root / "prompting.md").exists():
            guide_paths = [root / "prompting.md"]
        else:
            guide_paths = sorted(root.glob("*/prompting.md"))
            if not guide_paths:
                guide_paths = sorted(root.rglob("prompting.md"))

    if not guide_paths:
        print(f"No prompting.md guides found under {root}")
        return 0

    has_failures = False
    for guide_path in guide_paths:
        if update:
            try:
                update_guide(
                    guide_path,
                    fixtures_dir=fixtures_dir,
                    timeout=timeout,
                    model_deadline=model_deadline,
                    max_bytes=max_bytes,
                    opener=opener,
                )
                print(f"Updated {guide_path}")
            except (FetchError, ExtractionError, ValueError, OSError) as e:
                has_failures = True
                print(f"Update error for {guide_path}: {e}", file=sys.stderr)
        else:
            result = check_guide(
                guide_path,
                fixtures_dir=fixtures_dir,
                check_only=check_only,
                timeout=timeout,
                model_deadline=model_deadline,
                max_bytes=max_bytes,
                opener=opener,
            )
            if not result["ok"]:
                has_failures = True
                for v in result["violations"]:
                    print(v, file=sys.stderr)

    if has_failures:
        return 1

    if not update:
        print(
            f"Checked {len(guide_paths)} model guide(s): all guides are fresh and valid."
        )
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
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_REQUEST_TIMEOUT,
        help=f"Per-request network timeout in seconds (default: {DEFAULT_REQUEST_TIMEOUT})",
    )
    parser.add_argument(
        "--deadline",
        type=float,
        default=DEFAULT_MODEL_DEADLINE,
        help=f"Overall deadline per model in seconds (default: {DEFAULT_MODEL_DEADLINE})",
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=MAX_RESPONSE_BYTES,
        help=f"Maximum allowed response body size in bytes (default: {MAX_RESPONSE_BYTES})",
    )
    args = parser.parse_args(argv)
    return scan_guides(
        root=args.root or Path("docs/models"),
        model=args.model,
        check_only=args.check,
        fixtures_dir=args.fixtures_dir,
        update=args.update,
        timeout=args.timeout,
        model_deadline=args.deadline,
        max_bytes=args.max_bytes,
    )


if __name__ == "__main__":
    sys.exit(main())
