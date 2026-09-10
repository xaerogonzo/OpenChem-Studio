"""One vocabulary of result kinds, and one registry over it.

Three registries used to answer "what kind of result is this" independently --
`result_to_text`, `_RESULT_VIEW_FACTORIES` and `_open_inspector` -- and all
three got the same case wrong in the same way. These guards pin the vocabulary,
the subclass rule, and the closed world in both directions.

**THE POPULATION IS DERIVED, NEVER LISTED.** A hardcoded list of presentable
kinds is the `inapplicable_calculators` rot waiting to happen: it looks correct
and stops being true the moment somebody adds a result type. It comes from the
events the Properties panel subscribes to, which is what "presentable" means
here.
"""

from __future__ import annotations

import ast
import typing
from pathlib import Path

import pytest

from openchem.domain import scientific_result as sr
from openchem.domain.report import ReportResult
from openchem.domain.result_kinds import (
    RESULT_KINDS,
    SPECTRUM,
    VIBRATIONAL_SPECTRUM,
    UnknownResultKind,
    kind_of,
    kind_or_none,
)
from openchem.ui.result_adapters import ADAPTERS, adapter_for, result_to_text

SRC = Path(__file__).resolve().parent.parent / "src" / "openchem"


def _presentable_result_types() -> dict[str, type]:
    """Every result type the Properties panel can be handed, derived.

    Walks the panel's `event_bus.subscribe(XComputed, ...)` calls, then reads
    each event's payload annotation. That is what makes this a measurement
    rather than a list somebody has to remember to update.
    """
    from openchem.events import events as events_module

    panel = (SRC / "ui" / "panels" / "property_panel.py").read_text(encoding="utf-8")
    subscribed = {
        node.args[0].id
        for node in ast.walk(ast.parse(panel))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "subscribe"
        and node.args
        and isinstance(node.args[0], ast.Name)
    }
    found: dict[str, type] = {}
    for name in sorted(subscribed):
        event = getattr(events_module, name, None)
        if event is None:
            continue
        for field, annotation in typing.get_type_hints(event).items():
            if isinstance(annotation, type) and issubclass(annotation, sr.ScientificResult):
                found[f"{name}.{field}"] = annotation
    return found


def test_the_derived_population_is_not_empty():
    """Asserts its own setup. A walk that quietly returned nothing would make
    every coverage guard below vacuously true -- the green-suite-and-a-smaller-
    universe failure this repository records repeatedly."""
    population = _presentable_result_types()
    assert len(population) >= 5, f"the walk found only {population}"


def test_every_presentable_result_type_has_a_kind():
    """The wide half of the closed world."""
    unknown = []
    for where, kind_type in _presentable_result_types().items():
        # `__new__` rather than a constructed instance: `kind_of` reads only
        # `type(result).__mro__`, and the seven payload types have seven
        # different required-argument sets. An uninitialised instance is
        # enough here and is what keeps the population derived rather than
        # hand-built.
        try:
            kind_of(kind_type.__new__(kind_type))
        except UnknownResultKind:
            unknown.append(f"{where} -> {kind_type.__name__}")
    assert not unknown, (
        "result types the panel receives with no registered kind: " + ", ".join(unknown)
    )


def test_every_kind_has_an_adapter():
    """The registry is TOTAL over the vocabulary. A missing entry would raise a
    KeyError deep in a paint path rather than here."""
    assert set(ADAPTERS) == set(RESULT_KINDS)


def test_an_unknown_result_type_is_refused_loudly_by_both_consumers():
    """The other direction of the closed world, and the important one.

    A silent default produces a plausible-looking empty presentation, which a
    caller cannot tell from a result that genuinely had nothing to say. Both
    the kind lookup and the clipboard must refuse the same injected type --
    the same registry exercised both ways.
    """

    class NotOurs:
        cache_state = None
        name = "impostor"

    with pytest.raises(UnknownResultKind):
        kind_of(NotOurs())
    with pytest.raises(UnknownResultKind):
        adapter_for(NotOurs())
    with pytest.raises(UnknownResultKind):
        result_to_text(NotOurs())


def test_kind_or_none_is_the_only_silent_form():
    """Separate from `kind_of` rather than a flag on it, so refusing stays the
    default and a caller wanting silence has to say so."""

    class NotOurs:
        pass

    assert kind_or_none(NotOurs()) is None


# --- the subclass rule ---------------------------------------------------


def test_an_unregistered_subclass_shares_its_base_kind():
    """`NMRSpectrumResult` is not registered and correctly resolves to
    SPECTRUM. Without this, every subclass would need its own entry and the
    first one nobody added would be refused outright."""
    nmr = sr.NMRSpectrumResult(
        spectrum_type="nmr_13c", name="N", units="ppm", method="m", molecule_uuid="u"
    )
    assert kind_of(nmr) == SPECTRUM


def test_a_vibrational_spectrum_is_not_treated_as_an_nmr_one():
    """**THE CASE THAT MOTIVATED THE SPECIALIZATION, AND IT WAS LIVE.**

    `VibrationalSpectrumResult` subclasses `SpectrumResult`, so every
    isinstance-based renderer treated it as NMR. It is not one: its data is
    per NORMAL MODE and it leaves `values`/`elements` deliberately empty,
    because a vibrational peak is not a property of an atom.
    """
    ir = sr.VibrationalSpectrumResult(
        spectrum_type="ir", name="IR", units="cm^-1", method="orca", molecule_uuid="u"
    )
    assert kind_of(ir) == VIBRATIONAL_SPECTRUM
    assert kind_of(ir) != SPECTRUM


def test_an_ir_spectrum_copies_its_modes_rather_than_an_empty_atom_table():
    """The measurement, as a regression guard.

    Before the specialization, a two-mode IR spectrum copied as exactly two
    lines -- its name and an `Atom / Element / Shift` header -- with both modes
    dropped. The fixture asserts it really has modes and no atom-keyed values,
    so it cannot go vacuous if either field's meaning changes.
    """
    ir = sr.VibrationalSpectrumResult(
        spectrum_type="ir",
        name="IR Spectrum",
        units="cm^-1",
        method="orca",
        molecule_uuid="u",
        modes=(
            sr.VibrationalMode(wavenumber_cm1=1700.0, ir_intensity_km_mol=250.0),
            sr.VibrationalMode(wavenumber_cm1=3000.0, ir_intensity_km_mol=40.0),
        ),
    )
    assert ir.modes and not ir.values, "fixture is degenerate: it must be mode-keyed"

    text = result_to_text(ir)
    assert "1700" in text and "3000" in text, "the modes were dropped"
    assert "250" in text, "the IR intensities were dropped"
    # And NOT the NMR vocabulary, which is what made the old output look
    # plausible rather than obviously empty.
    assert "Shift" not in text
    assert "Element" not in text


def test_an_imaginary_mode_warning_survives_a_copy():
    """An imaginary mode says the geometry is a saddle point and invalidates
    every thermochemistry number from the same job. A copy that dropped it
    would export a spectrum that looks fine."""
    ir = sr.VibrationalSpectrumResult(
        spectrum_type="ir",
        name="IR",
        units="cm^-1",
        method="orca",
        molecule_uuid="u",
        modes=(sr.VibrationalMode(wavenumber_cm1=-120.0),),
        imaginary_warning="1 imaginary mode: this is a saddle point.",
    )
    assert "saddle point" in result_to_text(ir)


def test_the_nmr_rendering_is_unchanged():
    """The narrow half. Giving the vibrational case its own kind must not have
    moved the NMR one, which shares the base adapter."""
    nmr = sr.NMRSpectrumResult(
        spectrum_type="nmr_13c",
        name="13C NMR",
        units="ppm",
        method="hose",
        molecule_uuid="u",
        values={0: 128.5},
        elements={0: "C"},
    )
    text = result_to_text(nmr)
    assert "Atom\tElement\tShift" in text
    assert "128.5" in text


# --- identity, not name --------------------------------------------------


def test_kinds_resolve_by_class_identity_rather_than_by_name():
    """**THIS TREE HAS TWO UNRELATED `CorrelationResult` CLASSES** --
    `chem/analytics.py`'s statistics value and `domain/scientific_result.py`'s
    2D-NMR cross peaks. A registry keyed on `__name__` would resolve one to
    the other's adapter, and both are plausible enough that nothing downstream
    would complain.

    Asserts the setup first: if the two ever merge, this guard is about
    nothing and should say so rather than pass quietly.
    """
    from openchem.chem.analytics import CorrelationResult as StatsCorrelation

    assert StatsCorrelation is not sr.CorrelationResult, (
        "the two CorrelationResult classes merged -- this guard is now vacuous"
    )
    assert StatsCorrelation.__name__ == sr.CorrelationResult.__name__

    # Neither is a presentable kind today; the point is that asking is safe
    # and gives the same answer for both rather than crossing them over.
    assert kind_or_none(StatsCorrelation(pearson_r=0.0, spearman_rho=0.0, n=0, slope=0.0, intercept=0.0)) is None


def test_the_registry_is_keyed_by_class_not_by_string_name():
    """Asserted on the source: a `__name__`-keyed registry would pass every
    behavioural guard above while being one same-named class away from
    resolving to the wrong adapter."""
    source = (SRC / "domain" / "result_kinds.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "__name__":
            raise AssertionError(
                "result_kinds resolves on a class __name__ -- this tree has two "
                "unrelated CorrelationResult classes; key on the class itself"
            )


# --- rich-view targets ---------------------------------------------------


@pytest.mark.parametrize("kind", sorted(RESULT_KINDS))
def test_every_adapter_declares_a_rich_view_or_says_it_has_none(kind):
    """`NO_RICH_VIEW` is a VALUE, so "no viewer" and "nobody filled this in"
    stay different states -- the same reason `decline_total` requires a
    reason."""
    adapter = ADAPTERS[kind]
    assert isinstance(adapter.rich_view, str)
    assert callable(adapter.to_text)


def test_a_report_is_read_in_place_rather_than_in_a_viewer():
    """A report's own surface IS the results reader, so it declares no rich
    view. If this ever gains one, the reader would offer to open a window
    showing what is already on screen."""
    from openchem.ui.result_adapters import NO_RICH_VIEW
    from openchem.domain.result_kinds import REPORT

    assert ADAPTERS[REPORT].rich_view == NO_RICH_VIEW
    assert result_to_text(ReportResult(report_id="r", name="R", molecule_uuid="u")) is not None
