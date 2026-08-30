"""Vina and ORCA, brought up to the other tools' level of management.

They were the first two external tools and predate the descriptor system,
so they were hand-built: no Locate, no Test, no Remove, and in ORCA's case
no status line at all. These pin what changed and, more importantly, the
one thing that must NOT be smoothed over -- this app can fetch Vina and
cannot fetch ORCA.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from openchem.app.settings import Settings
from openchem.events.base import EventBus
from openchem.services import tool_download_service as tools
from openchem.ui.dialogs.external_tool_catalog import orca, vina
from openchem.ui.dialogs.external_tools_dialog import ExternalToolsDialog

import conftest


def _dispose(widget) -> None:
    conftest.dispose(widget)


@pytest.fixture
def dialog(qapp):
    widget = ExternalToolsDialog(Settings(EventBus()))
    yield widget
    _dispose(widget)


# --- the gap that prompted this ---------------------------------------------


def test_orca_finally_has_a_status_line(dialog):
    """Vina always had one and ORCA never did -- the most visible of the
    inconsistencies, and the one you can see in a screenshot."""
    tab = dialog._tab_for("orca")

    assert tab.status_label.text()
    assert tab.status_label.text() != "Checking..."


def test_both_tools_have_locate_and_test(dialog):
    """The two controls every managed tool has and these two lacked."""
    for key in ("vina", "orca"):
        tab = dialog._tab_for(key)
        assert tab.locate_button is not None, key
        assert tab.test_button is not None, key


# --- the difference that must survive ---------------------------------------


def test_orca_offers_no_set_up_button_because_it_cannot_be_downloaded():
    """**ORCA's licence forbids automated downloads.** A "Set Up
    Automatically" here could only open a browser and apologise, which is
    worse than an honest link, so the tab shows vendor links instead."""
    descriptor = orca()

    assert descriptor.obtainable is False
    assert descriptor.vendor_links
    assert any("FACCTS" in label for label, _url in descriptor.vendor_links)


def test_orca_offers_no_remove_because_this_app_never_installed_it():
    """Removing would delete the user's own FACCTS install. Vina's
    download is this app's to remove; ORCA's install is not."""
    assert orca().removable is False
    assert vina().removable is True


def test_the_orca_tab_hides_the_buttons_it_cannot_honour(dialog):
    tab = dialog._tab_for("orca")

    assert not tab.setup_button.isVisibleTo(tab)
    assert not tab.remove_button.isVisibleTo(tab)


def test_the_vina_tab_shows_both(dialog):
    tab = dialog._tab_for("vina")

    assert tab.setup_button.isVisibleTo(tab)
    assert tab.remove_button.isVisibleTo(tab)


# --- locating, and the impostor that made verification mandatory ------------



def _program(directory: Path, stem: str) -> Path:
    """A file named the way the real tool is named ON THIS PLATFORM.

    ORCA ships as `orca.exe` on Windows and a bare `orca` elsewhere, and
    `locate_executable` filters candidates by that shape. Hardcoding
    `.exe` therefore does not merely fail off Windows -- it made
    `test_locating_runs_each_candidate_rather_than_trusting_its_name`
    PASS on Linux for the wrong reason, since the file was skipped for
    its suffix before `validate` was ever called, and the test asserting
    "the impostor was rejected" was asserting that nothing was looked at.
    """
    return directory / (f"{stem}.exe" if os.name == "nt" else stem)


def test_locating_runs_each_candidate_rather_than_trusting_its_name(tmp_path):
    """**This is not hypothetical.** Searching a real machine for "orca"
    found

        C:\\Windows\\Installer\\{62A84A8B-...}\\Orca.exe

    before the real one -- an unrelated program in an MSI cache.
    Configuring that would give a quantum-chemistry tool that fails
    naming neither the cause nor the fix, which is exactly the name
    confusion the ORCA tab warns about in prose.

    So `validate` is a required argument, and a candidate that fails it
    is skipped rather than returned.
    """
    impostor = _program(tmp_path, "orca")
    impostor.write_text("not really orca", encoding="utf-8")

    found = tools.locate_executable(
        ("orca",),
        validate=lambda _candidate: False,
        search_roots=(tmp_path,),
    )

    assert found is None


def test_locating_returns_a_candidate_that_passes(tmp_path):
    real = _program(tmp_path, "orca")
    real.write_text("pretend", encoding="utf-8")

    found = tools.locate_executable(
        ("orca",),
        validate=lambda _candidate: True,
        search_roots=(tmp_path,),
    )

    assert found is not None
    assert found.name.lower().startswith("orca")


# --- status, which must not run anything ------------------------------------


def test_orca_status_reads_the_path_without_running_orca(tmp_path):
    """A status line is read on every visit to the tab, and ORCA has no
    `--version` -- the cheapest real check is a whole calculation. That
    belongs behind the Test button, pressed on purpose."""
    assert tools.describe_orca_status("") == "Not configured"
    assert "no file at" in tools.describe_orca_status(str(tmp_path / "absent.exe"))

    present = tmp_path / "orca.exe"
    present.write_text("x", encoding="utf-8")
    assert "Configured" in tools.describe_orca_status(str(present))


def test_verifying_orca_refuses_a_path_with_no_file():
    with pytest.raises(tools.ToolVerificationError, match="No ORCA executable"):
        tools.verify_orca(str(Path("nowhere") / "orca.exe"))


def test_verifying_vina_refuses_an_unconfigured_path():
    with pytest.raises(tools.ToolVerificationError, match="No Vina executable"):
        tools.verify_vina("")


# --- both are now ordinary tabs ---------------------------------------------


def test_they_go_through_the_same_registration_as_every_other_tool(dialog):
    """Which is what gives them refresh-after-removal and a Storage entry
    for free, rather than each needing its own wiring."""
    keys = [tab.descriptor.key for tab in dialog._tool_tabs]

    assert "vina" in keys and "orca" in keys


def test_the_old_widget_names_still_resolve(dialog):
    """`_vina_path_edit` and `_orca_path_edit` are what the existing suite
    reaches for. Keeping them is what let that suite stay untouched across
    this rewrite, which is the only real check that behaviour is
    unchanged."""
    assert dialog._vina_path_edit is dialog._tab_for("vina").path_row.edit
    assert dialog._orca_path_edit is dialog._tab_for("orca").path_row.edit
