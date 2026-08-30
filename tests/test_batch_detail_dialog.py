"""Batch renders like Properties, and the inspectors are capped.

The reported complaint was that a calculator which is one coherent result
on the left became N unrelated numeric columns on the right, with no
Details view and no inspector. These are the guards that it does not go
back.
"""

from __future__ import annotations

import pytest

from openchem.domain.batch import BatchResultStore, ResultKey
from openchem.domain.molecule import MoleculeModel
from openchem.domain.report import Basis, Fact, FactCategory, ReportResult
from openchem.ui.dialogs import calculator_inspector_dialog as inspector_module
from openchem.ui.dialogs.batch_detail_dialog import BatchDetailDialog
from openchem.ui.widgets.fact_view import FactView

import conftest


class _Tracked:
    """Weak-referenceable stand-in for an open inspector.

    The budget is a count of LIVE DIALOGS, so it can be exercised without
    eight `QWebEngineView`s -- which would be eight Chromium processes
    inside the test suite, measured at exactly one each. The registration
    itself is asserted separately, once, against the real dialog.
    """


@pytest.fixture
def store():
    store = BatchResultStore()
    store.put(
        ResultKey(molecule_uuid="m1", calculator_id="topology"),
        ReportResult(
            report_id="topology",
            name="Topology Analysis",
            molecule_uuid="m1",
            facts=(
                Fact(
                    label="Wiener index",
                    value=42,
                    display_value="42",
                    category=FactCategory.STRUCTURE,
                    source="topology",
                    basis=list(Basis)[0],
                ),
                Fact(
                    label="Randic index",
                    value=9.52,
                    display_value="9.52",
                    category=FactCategory.STRUCTURE,
                    source="topology",
                    basis=list(Basis)[0],
                ),
            ),
        ),
    )
    return store


@pytest.fixture
def molecule(services):
    model = MoleculeModel(uuid="m1", display_name="aspirin")
    services.chemistry_engine.set_structure_from_smiles(model, "CC(=O)Oc1ccccc1C(=O)O")
    return model


def _dialog(services, molecule, store, widgets):
    dialog = BatchDetailDialog(services.chemistry_engine, molecule, store)
    widgets.append(dialog)
    return dialog


# --- the renderer is the Properties one -------------------------------------


def test_the_detail_view_is_the_properties_renderer(qapp, services, molecule, store, widgets):
    """**NOT A SECOND RENDERER.** `FactView` takes anything with `facts`,
    `by_category()` and `find()` -- its docstring says so -- and is already
    the Properties panel's "Details..." for sixteen calculators. Building
    another for the same facts is the divergence this change exists to
    end."""
    dialog = _dialog(services, molecule, store, widgets)
    views = dialog.findChildren(FactView)
    assert len(views) == 1
    assert [fact.label for fact in views[0].report().facts] == [
        "Wiener index",
        "Randic index",
    ]


def test_one_calculators_many_numbers_stay_one_result(qapp, services, molecule, store, widgets):
    """The complaint, precisely: Topology Analysis is ONE button and one
    Details view in Properties, and had become a Wiener column and a Randic
    column with nothing tying them together."""
    dialog = _dialog(services, molecule, store, widgets)
    report = dialog.findChildren(FactView)[0].report()
    assert len({fact.source for fact in report.facts}) == 1


def test_nothing_computed_is_not_an_empty_fact_view(qapp, services, widgets):
    """"Nothing has been computed" and "everything ran and had nothing to
    say" are different statements, and an empty report says the second."""
    empty = MoleculeModel(uuid="nobody", display_name="untouched")
    dialog = BatchDetailDialog(services.chemistry_engine, empty, BatchResultStore())
    widgets.append(dialog)

    assert not dialog.findChildren(FactView)
    assert "Nothing has been computed" in _all_text(dialog)


def test_a_result_with_its_own_view_is_offered_rather_than_flattened(
    qapp, services, molecule, store, widgets
):
    """A per-atom dataset has no facts to merge. It gets a button, not an
    em dash."""

    from PySide6.QtWidgets import QPushButton

    class _Spectrum:
        name = "NMR Spectrum"

    store.put(ResultKey(molecule_uuid="m1", calculator_id="nmr"), _Spectrum())
    dialog = _dialog(services, molecule, store, widgets)

    assert "NMR Spectrum" in _all_text(dialog), "the result is not even named"
    inspect_buttons = [
        button
        for button in dialog.findChildren(QPushButton)
        if button.text().startswith("Inspect")
    ]
    assert len(inspect_buttons) == 1
    # It has to know WHICH result it opens, or one button would serve them
    # all and open whichever was last added.
    assert inspect_buttons[0].property("openchem_calculator_id") == "nmr"


def _all_text(widget) -> str:
    from PySide6.QtWidgets import QAbstractButton, QGroupBox, QLabel

    parts = []
    for kind in (QLabel, QAbstractButton, QGroupBox):
        parts.extend(child.text() if hasattr(child, "text") else child.title()
                     for child in widget.findChildren(kind))
    return "\n".join(str(p) for p in parts)


# --- the cap ------------------------------------------------------------------


def test_the_shipped_cap_is_a_number_a_person_could_reach():
    """The cap's MAGNITUDE, asserted directly and cheaply.

    **AND THE TEST BELOW DELIBERATELY DOES NOT DO THIS.** The first
    version of it built `range(MAX_OPEN_INSPECTORS)` stand-ins, so it
    scaled its own work by the constant under test -- and a mutation
    setting the cap to `1 << 30` made it allocate a billion objects and
    hang the mutation pass twice before the cause was spotted. A guard
    must not do work proportional to the thing it is guarding.

    The upper bound is the readability argument the constant records; the
    lower bound is that a cap of zero would disable the feature entirely
    while every behavioural test below still passed.
    """
    assert 1 <= inspector_module.MAX_OPEN_INSPECTORS <= 16


def test_the_budget_refuses_past_the_cap_and_says_how_many(monkeypatch):
    """**THE REFUSAL IS THE FEATURE**, and it must be reachable.

    Opening up to the cap and asserting nothing is a test of the happy
    path; the one that matters opens one past it.

    The cap is monkeypatched to a small number so this costs two objects
    whatever the shipped value is -- the shipped value's own sanity is
    `test_the_shipped_cap_is_a_number_a_person_could_reach` above.
    """
    monkeypatch.setattr(inspector_module, "MAX_OPEN_INSPECTORS", 2)
    live = [_Tracked(), _Tracked()]
    tracked = inspector_module._OPEN_INSPECTORS
    for item in live:
        tracked.add(item)
    try:
        assert inspector_module.open_inspector_count() >= 2
        message = inspector_module.inspector_budget_message()
        assert message is not None
        assert "2" in message
        assert "Close one" in message
    finally:
        for item in live:
            tracked.discard(item)


def test_the_budget_allows_the_ordinary_case():
    """A cap is worth what its ability to say YES is worth. With nothing
    open the answer must be None, or the feature is simply off."""
    assert inspector_module.inspector_budget_message() is None


def test_the_cap_counts_dialogs_and_not_chromium_processes():
    """Process topology JUSTIFIES the number and is not the contract -- a
    cap expressed in `QtWebEngineProcess.exe` counts would change meaning
    under a Qt upgrade, and is not something a user can reason about."""
    import inspect

    source = inspect.getsource(inspector_module.inspector_budget_message)
    assert "QtWebEngineProcess" not in source
    assert "open_inspector_count()" in source


def test_a_real_inspector_registers_itself(qapp, services, widgets):
    """The narrow half. The budget above is exercised with stand-ins, so
    something has to assert that a real dialog joins the population it is
    counting -- otherwise the cap counts an empty set forever."""
    from rdkit import Chem

    from openchem.ui.dialogs.calculator_inspector_dialog import CalculatorInspectorDialog

    definition = services.calculator_registry.get("crippen_logp_contrib")
    molecule = MoleculeModel(display_name="aspirin")
    services.chemistry_engine.set_structure_from_smiles(molecule, "CC(=O)Oc1ccccc1C(=O)O")
    result = services.calculator_registry.compute(
        "crippen_logp_contrib",
        Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O"),
        molecule.uuid,
        {p.name: p.default for p in definition.parameters},
    )

    before = inspector_module.open_inspector_count()
    dialog = CalculatorInspectorDialog(services.chemistry_engine, molecule, result, None)
    widgets.append(dialog)
    assert inspector_module.open_inspector_count() == before + 1


def test_the_population_is_held_weakly(qapp, services, widgets):
    """A strong container here would be the leak the cap exists to
    prevent, wearing the cap's clothes."""
    import weakref

    assert isinstance(inspector_module._OPEN_INSPECTORS, weakref.WeakSet)

    item = _Tracked()
    inspector_module._OPEN_INSPECTORS.add(item)
    before = inspector_module.open_inspector_count()
    del item
    assert inspector_module.open_inspector_count() == before - 1


@pytest.fixture
def widgets():
    """Destroyed deterministically, per widget.

    Never the global `sendPostedEvents(None, DeferredDelete)`: that drains
    every pending deferred delete in the process, including ones other test
    files left queued, which `tests/conftest.py` documents as a double-free.
    """
    built = []
    yield built
    for widget in built:
        widget.close()
        conftest.dispose(widget)


@pytest.fixture
def services():
    from openchem.bootstrap import build_service_container

    return build_service_container()
