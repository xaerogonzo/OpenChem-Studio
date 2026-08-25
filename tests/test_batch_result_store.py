"""The canonical store, and why the table is not it.

Batch used to reduce every result to numbers and drop the result. That is
the divergence this file guards against coming back: `reduce_result` is a
PROJECTION, and a detail view, an inspector or a comparison reading from it
rather than from the store is the same loss happening again.
"""

from __future__ import annotations

import pytest

from openchem.domain.batch import (
    CELL_KINDS,
    FAILED,
    NON_SCALAR,
    SCALAR,
    BatchCell,
    BatchResultStore,
    BatchTable,
    ResultKey,
)
from openchem.domain.common import CacheState
from openchem.domain.report import Basis, Fact, FactCategory, ReportResult
from openchem.services.result_cache import parameters_key


def _fact(label: str, value: float) -> Fact:
    return Fact(
        label=label,
        value=value,
        display_value=str(value),
        category=FactCategory.IDENTITY,
        source="test",
        basis=list(Basis)[0],
    )


def _report(molecule: str, report_id: str, *labels: str) -> ReportResult:
    return ReportResult(
        report_id=report_id,
        name=report_id,
        molecule_uuid=molecule,
        facts=tuple(_fact(label, index) for index, label in enumerate(labels)),
    )


def _store(version: int = 1) -> BatchResultStore:
    store = BatchResultStore()
    store.put(
        ResultKey(molecule_uuid="m1", calculator_id="topology", structure_version=version),
        _report("m1", "topology", "Wiener index", "Randic index"),
    )
    store.put(
        ResultKey(molecule_uuid="m1", calculator_id="logp", structure_version=version),
        _report("m1", "logp", "LogP"),
    )
    return store


# --- the direction of the relationship --------------------------------------


def test_a_molecules_results_merge_into_one_report():
    """One report per molecule, not one per calculator -- which is how the
    Properties panel already presents the same calculators, and why
    `FactView` can render it with no new code."""
    report = _store().merged_report("m1", 1)
    assert [fact.label for fact in report.facts] == [
        "Wiener index",
        "Randic index",
        "LogP",
    ]


def test_the_merged_report_satisfies_the_renderer_contract():
    """`FactView` takes anything with `facts`, `by_category()` and
    `find()`. Asserted rather than assumed, because the whole claim of this
    change is that no second renderer is needed."""
    report = _store().merged_report("m1", 1)
    assert report.by_category()
    assert [fact.label for fact in report.find("Wiener")] == ["Wiener index"]


def test_nothing_computed_is_not_an_empty_report():
    """None, not a report with no facts. A caller must be able to say "not
    computed yet" -- an empty report renders as a molecule that was asked
    and had nothing to say, which is a different statement."""
    assert _store().merged_report("nobody", 1) is None


def test_a_result_with_no_facts_is_offered_through_its_inspector():
    """A per-atom dataset, a spectrum or a structure set has nothing to
    merge. It is separated rather than dropped, because the row action is
    how the real thing is reached."""
    store = _store()
    store.put(ResultKey(molecule_uuid="m1", calculator_id="nmr", structure_version=1), object())

    assert list(store.non_scalar_results("m1", 1)) == ["nmr"]
    assert "nmr" not in {f.label for f in store.merged_report("m1", 1).facts}


def test_the_store_survives_discarding_the_table():
    """**THE STORE IS CANONICAL AND THE TABLE IS DERIVED**, asserted in
    that direction: everything a detail view needs is reachable with no
    `BatchTable` in existence at all. If this ever fails, the projection
    has become the storage again."""
    store = _store()
    table = BatchTable()  # built, then thrown away
    table.add_row("m1", "aspirin")
    del table

    assert store.merged_report("m1", 1) is not None
    assert store.for_molecule("m1", 1).keys() == {"topology", "logp"}


# --- identity, and staleness ------------------------------------------------


def test_editing_a_molecule_makes_its_results_stale_rather_than_wrong():
    """`structure_version` is `StructureCheckService.current_version()`,
    the counter `StructureReport` is already built on. A key that omitted
    it would serve benzene's numbers for toluene -- which is exactly the
    failure `ResultCache`'s docstring records for a uuid-only key."""
    store = _store(version=1)
    assert store.merged_report("m1", 1) is not None

    # the user edits the structure; the checker's counter moves
    assert store.merged_report("m1", 2) is None, "a stale result was served"
    assert [k.calculator_id for k in store.stale_for("m1", 2)] == ["topology", "logp"]


def test_a_stale_result_is_reported_and_not_deleted():
    """Reported rather than dropped. A stale result is still a record of
    what was computed; silently serving it and silently blanking it are
    the two ways this goes wrong, and they look identical from outside."""
    store = _store(version=1)
    assert len(store) == 2
    store.stale_for("m1", 2)
    assert len(store) == 2, "asking which are stale must not delete them"


def test_the_same_parameters_give_the_same_key_in_any_order():
    """One recipe, `result_cache.key_for`. A second serialisation at the
    call site -- `str(sorted(parameters.items()))` is the obvious one --
    drifts from this and turns two identical requests into two keys."""
    assert parameters_key({"ph": 7.4, "mode": "fast"}) == parameters_key(
        {"mode": "fast", "ph": 7.4}
    )
    assert parameters_key({"ph": 7.4}) != parameters_key({"ph": 1.2})
    assert parameters_key({}) == parameters_key(None)
    assert parameters_key({}), "an empty parameter set still has a key"


def test_a_rerun_with_different_parameters_is_a_different_result():
    """Not an overwrite. Two pH values are two answers, and a key that
    omitted the parameters would keep only whichever ran last."""
    store = BatchResultStore()
    for ph in (1.2, 7.4):
        store.put(
            ResultKey(
                molecule_uuid="m1",
                calculator_id="charge",
                parameters_key=parameters_key({"ph": ph}),
                structure_version=1,
            ),
            _report("m1", "charge", f"charge at pH {ph}"),
        )
    assert len(store) == 2


# --- what a cell IS -----------------------------------------------------------


def test_a_non_scalar_cell_is_not_a_failure():
    """**THE EM DASH USED TO MEAN BOTH.** "This calculation failed" and
    "this result has no scalar form" are opposite statements, and a view
    testing only `failed` renders them alike -- telling the reader nothing
    was computed when something was."""
    failure = BatchCell(text="", cache_state=CacheState.FAILED, error="no conformer", kind=FAILED)
    spectrum = BatchCell(text="12 peaks", kind=NON_SCALAR)

    assert failure.failed and not failure.non_scalar
    assert spectrum.non_scalar and not spectrum.failed


def test_a_cell_is_a_scalar_unless_its_producer_says_otherwise():
    """The default keeps every existing producer's meaning: saying
    NON_SCALAR is an opt-in somebody had to mean, the same shape
    `applies_to` and `calculation_input` already use."""
    assert BatchCell(value=1.0, text="1.00").kind == SCALAR


@pytest.mark.parametrize("kind", sorted(CELL_KINDS))
def test_every_declared_kind_is_a_real_member(kind: str):
    assert BatchCell(kind=kind).kind in CELL_KINDS
