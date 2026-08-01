"""Pre-flight checks for the STOUT sidecar.

Both of these exist because the same mistake was made twice: a
requirement that is only discovered at the FIRST PREDICTION, after ~600
MB of TensorFlow has already been installed. Java was the first
(`find_java`); STOUT's model weights disappearing upstream was the
second. The tests below are about the checks happening EARLY, not just
happening.
"""

from __future__ import annotations

import pytest

from openchem.services import stout_setup

#: Captured at import, which happens BEFORE conftest's autouse fixture
#: replaces the module attribute. `.__wrapped__` also steps past the
#: lru_cache, so each probe below really runs.
_REAL_PROBE = stout_setup.weights_available.__wrapped__




# --- Upstream weights went away (July 2026) -------------------------------


def test_dead_weights_are_reported_before_anything_is_downloaded(tmp_path, monkeypatch):
    """The real failure Alex hit: setup completed, ~600 MB of TensorFlow
    landed on disk, and the FIRST prediction died with a pystow stack
    trace about a 404. Checking costs one request."""
    monkeypatch.setattr(stout_setup, "weights_available", lambda: False)
    # Java is present on this machine now, so the weights check has to be
    # what stops it -- otherwise this would pass for the wrong reason.
    monkeypatch.setattr(stout_setup, "find_java", lambda: "C:/fake/java")

    with pytest.raises(stout_setup.StoutSetupError) as caught:
        stout_setup.install(tmp_path / "stout_env")

    message = str(caught.value)
    assert "no longer published" in message
    assert stout_setup.MODEL_WEIGHTS_URL in message, "name the dead address, don't paraphrase it"
    assert "PubChem" in message, "say what still works"
    assert not (tmp_path / "stout_env" / ".venv").exists(), "nothing may be created first"


def test_being_offline_is_not_reported_as_upstream_being_gone(monkeypatch):
    """A machine with no network must not be told a third party has shut
    down -- that is a different problem with a different fix."""
    monkeypatch.setattr(
        stout_setup, "weights_available", lambda: None
    )
    monkeypatch.setattr(stout_setup, "find_java", lambda: None)

    # Falls through to the next real check rather than claiming the
    # weights are gone.
    assert "no longer published" not in stout_setup.describe_prerequisites()


def test_a_404_is_definite_but_a_network_error_is_not(monkeypatch):
    """The three-valued return is the whole point of `weights_available`."""
    import urllib.error

    from openchem.services import stout_setup as module

    def raising(exc):
        def _open(*args, **kwargs):
            raise exc

        return _open

    monkeypatch.setattr(
        "openchem.net.open_url",
        raising(urllib.error.HTTPError(module.MODEL_WEIGHTS_URL, 404, "Not Found", {}, None)),
    )
    assert _REAL_PROBE() is False

    monkeypatch.setattr(
        "openchem.net.open_url", raising(urllib.error.URLError("getaddrinfo failed"))
    )
    assert _REAL_PROBE() is None, "offline is unknown, not gone"

    # A server having a bad day is not the same claim as "withdrawn".
    monkeypatch.setattr(
        "openchem.net.open_url",
        raising(urllib.error.HTTPError(module.MODEL_WEIGHTS_URL, 503, "Unavailable", {}, None)),
    )
    assert _REAL_PROBE() is not False, "a 5xx must not be reported as gone"


def test_the_weights_url_matches_what_stout_actually_fetches():
    """If this drifts from STOUT's own hardcoded constant, the pre-flight
    check silently starts testing an address nothing uses."""
    assert stout_setup.MODEL_WEIGHTS_URL == (
        "https://storage.googleapis.com/decimer_weights/models.zip"
    )
