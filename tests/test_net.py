"""Every outbound request identifies this app.

This is one line of code guarding a failure that cost a real user a
working feature: Adoptium answers `Python-urllib/3.13` with HTTP 403 and
a body of `error code: 1010`, which names neither the header nor the fix.
The tests below assert the header is really on the wire, including after
a redirect, rather than asserting that some function was called.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from openchem.net import USER_AGENT, open_url


class _Handler(BaseHTTPRequestHandler):
    """Echoes the User-Agent back, and redirects once from /redirect."""

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler's own naming
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/echo")
            self.end_headers()
            return
        body = json.dumps({"agent": self.headers.get("User-Agent")}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def echo_server():
    """A real HTTP server, because the whole point is what reaches the
    far end -- mocking urlopen would assert our own argument back."""
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


def test_the_user_agent_actually_reaches_the_server(echo_server):
    with open_url(f"{echo_server}/echo", timeout=10) as response:
        assert json.load(response)["agent"] == USER_AGENT


def test_it_survives_a_redirect(echo_server):
    """Adoptium redirects to GitHub's release-asset host, so an agent
    that were dropped on the hop would fail exactly where it matters."""
    with open_url(f"{echo_server}/redirect", timeout=10) as response:
        assert json.load(response)["agent"] == USER_AGENT


def test_extra_headers_are_added_without_losing_the_agent(echo_server):
    """The GitHub releases call needs an Accept header too."""
    with open_url(
        f"{echo_server}/echo", timeout=10, headers={"Accept": "application/vnd.github+json"}
    ) as response:
        assert json.load(response)["agent"] == USER_AGENT


def test_the_agent_is_not_pythons_default():
    """The specific string Cloudflare rejects."""
    assert "Python-urllib" not in USER_AGENT
    assert USER_AGENT.startswith("OpenChemStudio/")


def test_no_download_bypasses_the_shared_helper():
    """A future bare `urlopen` would reintroduce this exact bug in a
    module nobody thinks to re-test."""
    from pathlib import Path

    source_root = Path(__file__).resolve().parent.parent / "src" / "openchem"
    offenders = []
    for path in source_root.rglob("*.py"):
        if path.name == "net.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "urlopen(" in text or "urlretrieve(" in text:
            offenders.append(path.relative_to(source_root).as_posix())

    assert offenders == [], (
        f"These open URLs directly instead of via openchem.net.open_url: {offenders}. "
        "A default User-Agent gets a 403 from Cloudflare-fronted hosts (Adoptium)."
    )
