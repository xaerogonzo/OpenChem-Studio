"""Tautomer traces inside the NMR viewer (P5, step 4): wired to the viewer's own nucleus choice, never to its signals."""

from __future__ import annotations

import sys
from pathlib import Path

import conftest
from rdkit import Chem

sys.path.insert(0, str(Path(__file__).parent))
from test_nmr_view_widget import _make_view  # noqa: E402
from test_tautomer_nmr_average import _build  # noqa: E402


def _view(qapp):
    view, _backend, _molecule, _spectrum = _make_view(qapp, "O=C1CCCCC1")
    return view


def test_attaching_a_result_shows_the_controls_and_draws_the_traces_for_the_chosen_nucleus(qapp):
    view = _view(qapp)
    nmr, distribution, _ = _build()
    assert view.tautomer_controls().isHidden()
    overlay = view.set_tautomer_nmr(nmr, distribution)
    assert not view.tautomer_controls().isHidden() and view.current_tautomer_overlay() is overlay
    spectrum = view._spectrum_widget
    assert len(spectrum.tautomer_traces()) == 3  # two tautomers and the average
    assert nmr.method_basis in view.tautomer_controls()._title.text()
    conftest.dispose(view)


def test_the_nucleus_choice_moves_the_traces_with_it(qapp):
    view = _view(qapp)
    nmr, distribution, _ = _build()
    view.set_tautomer_nmr(nmr, distribution)
    combo = view._element_combo
    elements = [combo.itemData(i) for i in range(combo.count())]
    assert "H" in elements
    spectrum = view._spectrum_widget
    combo.setCurrentIndex(combo.findData("H"))
    assert spectrum._trace_element == "H"
    if "C" in elements:
        combo.setCurrentIndex(combo.findData("C"))
        assert spectrum._trace_element == "C"
    conftest.dispose(view)


def test_a_checkbox_hides_and_shows_its_trace(qapp):
    view = _view(qapp)
    nmr, distribution, _ = _build()
    overlay = view.set_tautomer_nmr(nmr, distribution)
    key = overlay.traces[0].key
    check = view.tautomer_controls().checkbox_for(key)
    check.setChecked(False)
    assert not view._spectrum_widget.is_tautomer_trace_visible(key)
    check.setChecked(True)
    assert view._spectrum_widget.is_tautomer_trace_visible(key)
    conftest.dispose(view)


def test_the_overlay_never_touches_the_molecules_own_signals_or_reset_settings(qapp):
    view = _view(qapp)
    before = [(s.shift, s.integration, s.multiplicity) for s in view.signals()]
    nmr, distribution, _ = _build()
    view.set_tautomer_nmr(nmr, distribution)
    assert [(s.shift, s.integration, s.multiplicity) for s in view.signals()] == before
    view.reset_settings()  # a viewer SETTING reset leaves the attached result, as it does a measured reference
    assert view.current_tautomer_overlay() is not None
    conftest.dispose(view)


def test_clearing_removes_the_traces_and_hides_the_controls(qapp):
    view = _view(qapp)
    nmr, distribution, _ = _build()
    view.set_tautomer_nmr(nmr, distribution)
    view.clear_tautomer_nmr()
    assert view.current_tautomer_overlay() is None and view._spectrum_widget.tautomer_traces() == []
    assert view.tautomer_controls().isHidden()
    conftest.dispose(view)


def test_without_an_average_the_row_is_listed_disabled_with_the_reason(qapp):
    view = _view(qapp)
    nmr, distribution, _ = _build(branch="unvalidated")
    view.set_tautomer_nmr(nmr, distribution)
    controls = view.tautomer_controls()
    assert "not validated" in controls.note_text()
    unavailable = [c for c in controls.findChildren(type(controls.checkbox_for(nmr.entries[0].tautomer_fingerprint)))
                   if "not available" in c.text()]
    assert len(unavailable) == 1 and not unavailable[0].isEnabled() and "not validated" in unavailable[0].toolTip()
    conftest.dispose(view)


def test_the_left_out_list_names_atoms_one_based_and_the_reason(qapp):
    view = _view(qapp)
    nmr, distribution, _ = _build()
    view.set_tautomer_nmr(nmr, distribution)
    text = view.tautomer_controls().left_out_text()
    assert text.startswith("Left out of the average:")
    assert "hydrogen count changes" in text and "exchanges with solvent" in text
    # Atom numbers are the app's one-based display numbers: no "atom 0".
    import re

    assert all(int(n) >= 1 for line in text.splitlines()[1:] for n in re.findall(r"atoms? ([\d, ]+):", line)[0].split(", "))
    conftest.dispose(view)
