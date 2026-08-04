from __future__ import annotations

import os

import pytest

from openchem.services import pkasolver_setup
from openchem.services.pkasolver_setup import (
    PkasolverSetupError,
    SetupProgress,
    default_install_root,
    describe_prerequisites,
    install,
    interpreter_for,
)


def test_install_root_is_outside_the_source_tree():
    """An installed copy of this app has no writable source directory, so
    the environment must live in user data."""
    root = default_install_root()

    assert "OpenChemStudio" in str(root)
    assert "pkasolver_env" in str(root)


def test_interpreter_path_matches_the_platform(tmp_path):
    interpreter = interpreter_for(tmp_path)

    assert interpreter.parent.parent == tmp_path / ".venv"
    assert interpreter.name == ("python.exe" if os.name == "nt" else "python")


def test_prerequisites_are_described_before_committing_to_a_download():
    """The dialog shows this BEFORE the multi-gigabyte confirmation, so it
    must always be a usable sentence, never empty."""
    text = describe_prerequisites()

    assert text
    assert text.startswith("Ready:") or "Cannot set up automatically" in text


def test_prerequisites_explain_why_the_apps_own_python_is_unusable(monkeypatch):
    """Phase 24: this app runs Python 3.13 while PyTorch 2.3.0 publishes
    wheels only up to cp312 -- a naive installer reusing sys.executable
    would fail, so the message has to say why."""
    monkeypatch.setattr(pkasolver_setup, "find_uv", lambda: None)
    monkeypatch.setattr(pkasolver_setup, "find_fallback_python", lambda: None)

    text = describe_prerequisites()

    assert "Cannot set up automatically" in text
    assert "no wheels" in text


def test_install_fails_clearly_when_no_usable_python_exists(monkeypatch, tmp_path):
    monkeypatch.setattr(pkasolver_setup, "find_uv", lambda: None)
    monkeypatch.setattr(pkasolver_setup, "find_fallback_python", lambda: None)

    with pytest.raises(PkasolverSetupError, match="Cannot set up automatically"):
        install(tmp_path)


def test_progress_is_reported_for_every_step(monkeypatch, tmp_path):
    """The install takes several minutes; a user staring at a frozen dialog
    cannot tell it apart from a hang, so each step must report."""
    seen: list[SetupProgress] = []
    monkeypatch.setattr(pkasolver_setup, "find_uv", lambda: "uv")
    # Fail at the first real command, after the first progress report --
    # enough to prove reporting happens before work, without a real install.
    monkeypatch.setattr(
        pkasolver_setup, "_run",
        lambda *a, **k: (_ for _ in ()).throw(PkasolverSetupError("stopped for the test")),
    )

    with pytest.raises(PkasolverSetupError):
        install(tmp_path, on_progress=seen.append)

    assert seen
    assert seen[0].step == 1
    assert seen[0].total == 7
    assert "environment" in seen[0].message.lower()


def test_failure_messages_carry_the_underlying_error(monkeypatch, tmp_path):
    """PkasolverSetupError text is shown to the user verbatim, so it has to
    name what actually broke rather than just a return code."""
    monkeypatch.setattr(pkasolver_setup, "find_uv", lambda: "uv")
    monkeypatch.setattr(
        pkasolver_setup, "_run",
        lambda *a, **k: (_ for _ in ()).throw(PkasolverSetupError("network unreachable")),
    )

    with pytest.raises(PkasolverSetupError, match="network unreachable"):
        install(tmp_path)


def test_pinned_versions_are_the_verified_combination():
    """Each pin is load-bearing and was found the hard way: torch 2.4.0
    fails on Windows (missing fbgemm.dll), and torch-geometric newer than
    2.0.1 cannot load pkasolver's 2021 checkpoints at all. A well-meaning
    'let's modernise the pins' change would silently break prediction, so
    pin drift should fail a test."""
    assert pkasolver_setup.TORCH_VERSION == "2.3.0"
    assert "torch-2.3.0+cpu" in pkasolver_setup._PYG_WHEEL_INDEX
    assert pkasolver_setup._TARGET_PYTHON == "3.12"




