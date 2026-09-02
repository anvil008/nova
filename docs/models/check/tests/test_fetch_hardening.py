"""Acceptance and unit tests for guide fetch hardening (#147).

Proves that:
1. Connect / read stall past timeout exits non-zero naming the model and URL
   as a fetch failure within the deadline (never drift, never fresh).
2. Drip-feed / slow stream past deadline exits non-zero naming model and URL.
3. Oversized response bodies are rejected.
4. Redirect loops are bounded and exit non-zero.
5. The happy path is unchanged.
"""

from __future__ import annotations

import hashlib
import http.server
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
CHECK_GUIDES = ROOT / "docs" / "models" / "check" / "check_guides.py"

sys.path.insert(0, str(CHECK_GUIDES.parent))
import check_guides


def run_check(*args: str, **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(CHECK_GUIDES), *args],
        text=True,
        capture_output=True,
        check=False,
        **kwargs,
    )


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def render_frontmatter(fields: dict) -> str:
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


class HardeningServerHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/stall-read":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", "5000")
            self.end_headers()
            self.wfile.write(b"<html><body><article>Beginning text")
            self.wfile.flush()
            time.sleep(2.0)
        elif self.path == "/drip":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            for _ in range(40):
                try:
                    self.wfile.write(b"x")
                    self.wfile.flush()
                    time.sleep(0.05)
                except OSError:
                    break
        elif self.path == "/oversized":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><article>" + (b"A" * 15000) + b"</article></body></html>")
        elif self.path == "/redirect-loop":
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/redirect-loop")
            self.end_headers()
        elif self.path == "/happy":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><article>Focus on clear, modular agent tools.</article></body></html>"
            )
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


class FetchHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), HardeningServerHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.port = cls.server.server_port
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=2.0)

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.models_dir = self.root / "models"
        self.models_dir.mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def _write_guide(
        self,
        model: str,
        url: str,
        digest: str = "deadbeef",
        body: str = "# Guidance\n\n> Focus on clear, modular agent tools.\n",
    ) -> Path:
        guide_dir = self.models_dir / model
        guide_dir.mkdir(parents=True, exist_ok=True)
        guide_file = guide_dir / "prompting.md"
        fields = {
            "model": model,
            "official_source_urls": [url],
            "fetched_date": "2026-09-02",
            "extractor_version": check_guides.EXTRACTOR_VERSION,
            "normalized_source_digests": {url: digest},
        }
        content = render_frontmatter(fields) + body
        guide_file.write_text(content, encoding="utf-8")
        return guide_file

    def test_read_stall_exits_nonzero_within_deadline(self) -> None:
        model = "test-model-stall"
        url = f"{self.base_url}/stall-read"
        self._write_guide(model, url)

        start = time.monotonic()
        res = run_check(
            "--check",
            "--root",
            str(self.models_dir),
            "--timeout",
            "0.3",
            "--deadline",
            "1.5",
        )
        elapsed = time.monotonic() - start

        self.assertLess(elapsed, 2.0, f"Stall check took too long: {elapsed:.2f}s")
        self.assertNotEqual(res.returncode, 0, f"Expected non-zero exit on stall, got 0:\n{res.stdout}")
        output = res.stdout + res.stderr
        self.assertIn(model, output)
        self.assertIn(url, output)
        self.assertTrue(
            any(w in output.lower() for w in ("fetch failure", "timeout", "network error")),
            f"Expected output to describe fetch failure, got:\n{output}",
        )
        self.assertNotIn("is fresh", output.lower())
        self.assertNotIn("guides fresh", output.lower())
        self.assertNotIn("drift", output.lower())

    def test_drip_feed_exceeds_deadline(self) -> None:
        model = "test-model-drip"
        url = f"{self.base_url}/drip"
        self._write_guide(model, url)

        start = time.monotonic()
        res = run_check(
            "--check",
            "--root",
            str(self.models_dir),
            "--timeout",
            "1.0",
            "--deadline",
            "0.3",
        )
        elapsed = time.monotonic() - start

        self.assertLess(elapsed, 2.0, f"Drip check took too long: {elapsed:.2f}s")
        self.assertNotEqual(res.returncode, 0, f"Expected non-zero exit on deadline exceed, got 0:\n{res.stdout}")
        output = res.stdout + res.stderr
        self.assertIn(model, output)
        self.assertIn(url, output)
        self.assertTrue(
            any(w in output.lower() for w in ("fetch failure", "timeout", "deadline")),
            f"Expected output to describe fetch failure, got:\n{output}",
        )
        self.assertNotIn("is fresh", output.lower())
        self.assertNotIn("guides fresh", output.lower())
        self.assertNotIn("drift", output.lower())

    def test_oversized_body_is_rejected(self) -> None:
        model = "test-model-oversized"
        url = f"{self.base_url}/oversized"
        self._write_guide(model, url)

        res = run_check(
            "--check",
            "--root",
            str(self.models_dir),
            "--max-bytes",
            "1000",
        )
        self.assertNotEqual(res.returncode, 0, f"Expected non-zero exit on oversized body, got 0:\n{res.stdout}")
        output = res.stdout + res.stderr
        self.assertIn(model, output)
        self.assertIn(url, output)
        self.assertTrue(
            any(w in output.lower() for w in ("fetch failure", "exceeded", "limit")),
            f"Expected output to describe size failure, got:\n{output}",
        )
        self.assertNotIn("is fresh", output.lower())
        self.assertNotIn("guides fresh", output.lower())
        self.assertNotIn("drift", output.lower())

    def test_redirect_loop_is_bounded(self) -> None:
        model = "test-model-redirect-loop"
        url = f"{self.base_url}/redirect-loop"
        self._write_guide(model, url)

        start = time.monotonic()
        res = run_check(
            "--check",
            "--root",
            str(self.models_dir),
            "--timeout",
            "0.5",
        )
        elapsed = time.monotonic() - start

        self.assertLess(elapsed, 3.0, f"Redirect loop check took too long: {elapsed:.2f}s")
        self.assertNotEqual(res.returncode, 0, f"Expected non-zero exit on redirect loop, got 0:\n{res.stdout}")
        output = res.stdout + res.stderr
        self.assertIn(model, output)
        self.assertIn(url, output)
        self.assertTrue(
            any(w in output.lower() for w in ("fetch failure", "redirect", "error")),
            f"Expected output to describe redirect failure, got:\n{output}",
        )
        self.assertNotIn("is fresh", output.lower())
        self.assertNotIn("guides fresh", output.lower())
        self.assertNotIn("drift", output.lower())

    def test_happy_path_is_unchanged(self) -> None:
        model = "test-model-happy"
        url = f"{self.base_url}/happy"
        expected_text = "Focus on clear, modular agent tools."
        expected_digest = sha256_text(expected_text)
        self._write_guide(model, url, digest=expected_digest)

        res = run_check(
            "--check",
            "--root",
            str(self.models_dir),
        )
        self.assertEqual(
            res.returncode,
            0,
            f"Expected exit 0 for happy path, got {res.returncode}:\nstdout: {res.stdout}\nstderr: {res.stderr}",
        )
        output = res.stdout + res.stderr
        self.assertIn("all guides are fresh and valid", output)


if __name__ == "__main__":
    unittest.main()
