"""Generate Conformers can optimize the lowest conformer with any engine that is set up, and the choice travels with the set."""

from __future__ import annotations

import pytest

from openchem.domain.conformer import ConformerModel
from openchem.domain.optimize_choice import OptimizeChoice
from openchem.events.events import ConformersReady
from openchem.ui.dialogs.conformer_options_dialog import ConformerOptionsDialog, OrcaGenerationOffer

import conftest
from tests import test_orca_landing_in_slot as landing
from tests.test_optimize_with_an_engine import _panel


@pytest.fixture(autouse=True)
def _close_landing_windows():
    yield
    while landing._WINDOWS:
        landing._WINDOWS.pop().close()


ORCA = OptimizeChoice("orca", "ORCA", True)
XTB = OptimizeChoice("xtb", "xtb", True)
PSI4 = OptimizeChoice("psi4", "Psi4", False, "Psi4 is not set up.")


def _offer(*engines: OptimizeChoice) -> OrcaGenerationOffer:
    texts = tuple((c.provider_id, f"Runs on {c.name}.") for c in engines if c.available)
    return OrcaGenerationOffer(True, "Runs on ORCA.", engines, texts)


# -- the dialog ----------------------------------------------------------------------------------------------------


def test_with_one_engine_the_window_is_what_it_always_was(qapp):
    dialog = ConformerOptionsDialog(orca_offer=_offer(ORCA, PSI4))
    try:
        assert dialog._engine_combo is None
        assert dialog._orca_check.text() == "Also ORCA-optimize the lowest-energy conformer"
        assert dialog.optimize_provider() == "orca"
    finally:
        conftest.dispose(dialog)


def test_with_two_engines_the_window_offers_a_choice_and_names_what_each_would_run(qapp):
    dialog = ConformerOptionsDialog(orca_offer=_offer(ORCA, XTB, PSI4), optimize_lowest=True)
    try:
        combo = dialog._engine_combo
        assert [combo.itemText(i) for i in range(combo.count())] == ["ORCA", "xtb"]  # Psi4 is not set up: not offered
        assert dialog.optimize_provider() == "orca" and dialog._orca_note.text() == "Runs on ORCA."
        combo.setCurrentIndex(combo.findData("xtb"))
        assert dialog.optimize_provider() == "xtb" and dialog._orca_note.text() == "Runs on xtb."
        assert dialog.optimize_lowest() is True
        assert "with" in dialog._orca_check.text()
    finally:
        conftest.dispose(dialog)


def test_a_greyed_offer_greys_the_choice_too_and_never_takes_it(qapp):
    offer = OrcaGenerationOffer(False, "Nothing is set up.", (ORCA, XTB), (("orca", "a"), ("xtb", "b")))
    dialog = ConformerOptionsDialog(orca_offer=offer, optimize_lowest=True)
    try:
        assert not dialog._engine_combo.isEnabled() and dialog.optimize_lowest() is False
    finally:
        conftest.dispose(dialog)


# -- the event -----------------------------------------------------------------------------------------------------


def test_the_set_carries_the_engine_and_defaults_to_orca():
    assert ConformersReady(molecule_uuid="m", conformers=[]).optimize_provider == "orca"
    assert ConformersReady(molecule_uuid="m", conformers=[], optimize_provider="xtb").optimize_provider == "xtb"


# -- the window ----------------------------------------------------------------------------------------------------


def test_the_window_optimizes_the_lowest_with_the_engine_that_came_with_the_set(qapp, tmp_path):
    window, _services, molecule, _recorder = landing._window_with(qapp, tmp_path)
    asked: list[tuple[str, str, str]] = []
    window._quantum_chemistry_panel.start_optimization = lambda uuid, cid, provider_id="orca": asked.append((uuid, cid, provider_id)) or ""
    generated = [ConformerModel(molblock="x", energy=3.0), ConformerModel(molblock="y", energy=1.0)]
    molecule.conformers[:] = list(generated)
    window._optimize_lowest_generated(molecule, generated, "xtb")
    assert asked == [(molecule.uuid, generated[1].conformer_id, "xtb")]
    assert "xtb is optimizing" in window.statusBar().currentMessage()


def test_a_refusal_names_the_engine_in_the_status_bar(qapp, tmp_path):
    window, _services, molecule, _recorder = landing._window_with(qapp, tmp_path)
    window._quantum_chemistry_panel.start_optimization = lambda uuid, cid, provider_id="orca": "xtb is not set up."
    generated = [ConformerModel(molblock="x", energy=1.0)]
    molecule.conformers[:] = list(generated)
    window._optimize_lowest_generated(molecule, generated, "xtb")
    assert "not xtb-optimized" in window.statusBar().currentMessage()


# -- the panel's description of an engine it is not on ------------------------------------------------------------


def test_the_method_the_offer_names_is_the_one_the_panel_has_after_switching(tmp_path, monkeypatch, qapp):
    """The sentence is computed without switching, by a mirror of the method-box rule; this holds the mirror to the real rule."""
    panel, service, molecule = _panel(tmp_path, monkeypatch, with_xtb=True)
    try:
        for typed in ("B3LYP def2-SVP", "PBE0 def2-TZVP", "GFN2-xTB"):
            for target in ("xtb", "orca"):
                panel.select_engine("orca")
                panel._method_combo.setCurrentText(typed)
                provider = next(p for p in service.engines() if p.provider_id == target)
                predicted = panel._method_for_engine(provider)
                panel.select_engine(target)
                assert panel._method_combo.currentText() == predicted, (typed, target)
        panel.select_engine("orca")
        ok, text = panel.optimization_offer(molecule, "xtb")
        assert ok and "Runs on xtb" in text and "GFN2-xTB" in text
        ok, text = panel.optimization_offer(molecule, "nonsense")
        assert not ok and "not a registered engine" in text
    finally:
        conftest.dispose(panel)


def test_the_service_hands_the_engine_to_the_set_it_generates(qapp):
    from tests.test_orca_optimize_lowest_at_generation import _generate

    assert _generate(qapp, optimize_lowest=True, optimize_provider="xtb").optimize_provider == "xtb"
    assert _generate(qapp, optimize_lowest=True).optimize_provider == "orca"
