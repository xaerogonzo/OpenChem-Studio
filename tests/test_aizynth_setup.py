"""Automatic setup of the AiZynthFinder sidecar (`openchem.services.aizynth_setup`).

The tab used to be locate-only: a person had to build a Python 3.10-3.12
environment, pin pyarrow, and run download_public_data themselves. That is
the same shape as pkasolver and ADMET, so setup now does it, after an
ask-first confirmation. Nothing here hits the network: every command is
replaced, and the last step that would run a real search is stubbed.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from openchem.services import aizynth_setup
from openchem.services.aizynth_setup import (
    AizynthSetupError,
    PLANNER_PACKAGE,
    PYARROW_PIN,
    SetupProgress,
    default_install_root,
    describe_prerequisites,
    install,
    interpreter_for,
)


def test_install_root_is_outside_the_source_tree():
    root = default_install_root()

    assert "OpenChemStudio" in str(root)
    assert "aizynthfinder_env" in str(root)


def test_interpreter_path_matches_the_platform(tmp_path):
    interpreter = interpreter_for(tmp_path)

    assert interpreter.parent.parent == tmp_path / ".venv"
    assert interpreter.name == ("python.exe" if os.name == "nt" else "python")


def test_prerequisites_are_described_before_committing_to_a_download():
    text = describe_prerequisites()

    assert text
    assert text.startswith("Ready:") or "Cannot set up automatically" in text


def test_prerequisites_explain_why_the_apps_own_python_is_unusable(monkeypatch):
    monkeypatch.setattr(aizynth_setup, "find_uv", lambda: None)
    monkeypatch.setattr(aizynth_setup, "find_fallback_python", lambda: None)

    text = describe_prerequisites()

    assert "Cannot set up automatically" in text
    assert "3.10" in text and "3.12" in text


def test_install_fails_clearly_when_no_usable_python_exists(monkeypatch, tmp_path):
    monkeypatch.setattr(aizynth_setup, "find_uv", lambda: None)
    monkeypatch.setattr(aizynth_setup, "find_fallback_python", lambda: None)

    with pytest.raises(AizynthSetupError, match="Cannot set up automatically"):
        install(tmp_path)


def test_the_verified_pins_are_what_setup_installs():
    """aizynthfinder 4.4.1 is the quality-benchmark environment; pyarrow
    below 21 is the pin without which a fresh pip install does not import
    (`docs/SYNTHESIS_HELPER_DESIGN.md` 0b)."""
    assert aizynth_setup._TARGET_PYTHON == "3.12"
    assert PLANNER_PACKAGE == "aizynthfinder==4.4.1"
    assert PYARROW_PIN == "pyarrow<21"


def test_progress_is_reported_for_every_step(monkeypatch, tmp_path):
    seen: list[SetupProgress] = []
    monkeypatch.setattr(aizynth_setup, "find_uv", lambda: "uv")
    monkeypatch.setattr(
        aizynth_setup,
        "_run",
        lambda *a, **k: (_ for _ in ()).throw(AizynthSetupError("stopped for the test")),
    )

    with pytest.raises(AizynthSetupError):
        install(tmp_path, on_progress=seen.append)

    assert seen
    assert seen[0].step == 1
    assert seen[0].total == 4
    assert "environment" in seen[0].message.lower()


def _fake_run(tmp_path: Path, commands: list):
    def run(command, step, timeout=3600):
        commands.append(list(command))
        python = interpreter_for(tmp_path)
        if "venv" in command:
            python.parent.mkdir(parents=True, exist_ok=True)
            python.write_text("x", encoding="utf-8")
            downloader = python.parent / ("download_public_data.exe" if os.name == "nt" else "download_public_data")
            downloader.write_text("x", encoding="utf-8")
        if any("download_public_data" in str(part) for part in command):
            data = tmp_path / "data"
            data.mkdir(parents=True, exist_ok=True)
            (data / "config.yml").write_text("stock: {}\n", encoding="utf-8")
            (data / "zinc_stock.hdf5").write_bytes(b"x")

    return run


def test_install_builds_the_environment_fetches_public_data_and_returns_both_paths(monkeypatch, tmp_path):
    commands: list[list] = []
    monkeypatch.setattr(aizynth_setup, "find_uv", lambda: "uv")
    monkeypatch.setattr(aizynth_setup, "_run", _fake_run(tmp_path, commands))
    monkeypatch.setattr(aizynth_setup, "_verify", lambda python, config: None)

    python, config = install(tmp_path)

    assert python == interpreter_for(tmp_path) and config == tmp_path / "data" / "config.yml"
    pip_line = next(c for c in commands if "pip" in c)
    assert PLANNER_PACKAGE in pip_line and PYARROW_PIN in pip_line
    assert any("download_public_data" in str(part) for c in commands for part in c)


def test_a_re_run_reuses_the_venv_and_skips_a_data_folder_that_is_already_there(monkeypatch, tmp_path):
    python = interpreter_for(tmp_path)
    python.parent.mkdir(parents=True)
    python.write_text("x", encoding="utf-8")
    data = tmp_path / "data"
    data.mkdir()
    (data / "config.yml").write_text("stock: {}\n", encoding="utf-8")
    (data / "uspto_model.onnx").write_bytes(b"x")
    (data / "uspto_templates.csv.gz").write_bytes(b"x")
    (data / "zinc_stock.hdf5").write_bytes(b"x")
    commands: list[list] = []
    monkeypatch.setattr(aizynth_setup, "find_uv", lambda: "uv")
    monkeypatch.setattr(aizynth_setup, "_run", _fake_run(tmp_path, commands))
    monkeypatch.setattr(aizynth_setup, "_verify", lambda python, config: None)

    result_python, result_config = install(tmp_path)

    assert result_python == python and result_config == data / "config.yml"
    assert not any("venv" in c for c in commands)
    assert not any("download_public_data" in str(part) for c in commands for part in c)
    assert any("pip" in c for c in commands)


def test_failure_messages_carry_the_underlying_error(monkeypatch, tmp_path):
    monkeypatch.setattr(aizynth_setup, "find_uv", lambda: "uv")
    monkeypatch.setattr(
        aizynth_setup,
        "_run",
        lambda *a, **k: (_ for _ in ()).throw(AizynthSetupError("network unreachable")),
    )

    with pytest.raises(AizynthSetupError, match="network unreachable"):
        install(tmp_path)
