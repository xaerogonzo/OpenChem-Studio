"""Every result kind can reach the reader, and none of them lies on the way.

Measured before this existed, over the real registry on aspirin: of 60
calculators, **30 produce a result `merge_reports` refused** -- 16 per-atom
datasets, 7 structure sets, 5 pH curves, a trajectory and a spectrum. So half
the application's output reached the results reader not at all, and nothing on
screen said it existed.

A summary is a PROJECTION and is held to 0d's rule: deterministically derived
from declared result data, identified as one, and never introducing a new
scientific claim. `len(peaks)` is a projection; a declared total is the
producer's and is carried; a total the reader adds up is the bug the whole
`TOTAL` key exists to refuse.

Guards come in pairs. "It summarises" is satisfied by a projection that
invents numbers, so the refusals are asserted beside the projections.
"""

from __future__ import annotations

import dataclasses

import pytest

from openchem.domain.common import (
    ATOM_BASIS,
    CacheState,
    HEAVY_ATOMS,
    Provenance,
    TOTAL,
    declare_total,
    decline_total,
)
from openchem.domain.merged_results import is_report_shaped, merge_reports
from openchem.domain.report import Basis, FactCategory, ReportResult
from openchem.domain.result_kinds import (
    ALERT,
    PER_ATOM,
    REPORT,
    RESULT_KINDS,
    VIBRATIONAL_SPECTRUM,
    kind_of,
)
from openchem.domain.scientific_result import (
    AlertResult,
    PerAtomDataset,
    PhCurveResult,
    SpectrumResult,
    StructureEntry,
    StructureSetResult,
    TrajectoryResult,
    VibrationalMode,
    VibrationalSpectrumResult,
)
from openchem.ui.result_adapters import (
    ADAPTERS,
    SUMMARY_LIMITATION,
    _no_summary_needed,
    summarise,
)
from openchem.ui.result_summary import ResultSummaryView

MOLECULE = "mol-1"


def _view(result, **overrides):
    defaults = dict(result_id="r", name=getattr(result, "name", "R"), category="topology",
                    structure_version=3)
    defaults.update(overrides)
    return summarise(result, **defaults)


def _per_atom(values, provenance=None, **overrides) -> PerAtomDataset:
    defaults = dict(
        property_id="p", name="P", units="e", method="m",
        molecule_uuid=MOLECULE, values=values,
    )
    defaults.update(overrides)
    if provenance is not None:
        defaults["provenance"] = provenance
    return PerAtomDataset(**defaults)


# --- the registry is total, and its payload names real fields ------------


def test_every_kind_declares_a_summary_and_a_payload():
    assert set(ADAPTERS) == set(RESULT_KINDS)
    for kind, adapter in ADAPTERS.items():
        assert callable(adapter.summary), kind
        assert isinstance(adapter.payload, tuple) and len(adapter.payload) == 2, kind


@pytest.mark.parametrize(
    ("kind", "result_type"),
    [
        (PER_ATOM, PerAtomDataset),
        (VIBRATIONAL_SPECTRUM, VibrationalSpectrumResult),
        ("spectrum", SpectrumResult),
        ("ph_curve", PhCurveResult),
        ("structure_set", StructureSetResult),
        ("trajectory", TrajectoryResult),
    ],
)
def test_the_declared_payload_names_a_real_field(kind, result_type):
    """**DERIVED FROM THE DATACLASS, NEVER A HAND-WRITTEN LIST.** The panel
    used to probe four attribute names in a fixed order, and the guard for
    THAT was a hand-typed tuple of types which omitted
    `VibrationalSpectrumResult` -- the one type the probe got wrong. A
    population somebody maintains by hand excludes the case nobody thought
    of."""
    attribute, noun = ADAPTERS[kind].payload
    fields = {f.name for f in dataclasses.fields(result_type)}
    assert attribute in fields, f"{kind} declares {attribute!r}; {result_type.__name__} has {sorted(fields)}"
    assert noun, f"{kind} declares no noun for its payload"


# --- the defect this stage is named for ----------------------------------


def test_a_vibrational_spectrum_summarises_as_modes_not_as_nothing():
    """**MEASURED AT "None found." FOR A SPECTRUM WITH THREE REAL MODES.**

    A vibrational result leaves `values` empty on purpose -- a normal mode is
    not a property of one atom -- and both the panel row and any atom-keyed
    projection read that emptiness as "there is nothing here". It is the
    fourth consumer of one vocabulary read through a different registry,
    after the clipboard, the view factory and the inspector.
    """
    from openchem.ui.panels.property_panel import _summarise

    result = VibrationalSpectrumResult(
        spectrum_type="ir", name="IR Spectrum", units="cm^-1", method="ORCA",
        molecule_uuid=MOLECULE,
        modes=tuple(VibrationalMode(wavenumber_cm1=w) for w in (1650.0, 2900.0, 3400.0)),
    )
    assert _summarise(result) == "3 modes"
    facts = {f.label: f for f in _view(result).facts}
    assert facts["Modes"].display_value == "3"
    assert "1650" in facts["Wavenumbers"].display_value
    assert "3400" in facts["Wavenumbers"].display_value


def test_an_atom_keyed_spectrum_still_summarises_as_signals():
    """The narrow half: keying the vibrational case by mode must not change
    what an NMR spectrum, whose values really are per nucleus, reports."""
    result = SpectrumResult(
        spectrum_type="nmr_13c", name="13C", units="ppm", method="m",
        molecule_uuid=MOLECULE, values={0: 128.5, 1: 21.0},
    )
    facts = {f.label: f for f in _view(result).facts}
    assert facts["Signals"].display_value == "2"
    # **THE UNITS STAY IN THEIR OWN FIELD.** `Fact.units` belongs to `value`
    # and `value_with_units` composes them; folding them into `display_value`
    # is what made `report_adapter`'s 223 facts export "C: 60.00 % %".
    assert facts["Range"].units == "ppm"
    assert "ppm" not in facts["Range"].display_value
    assert facts["Range"].value_with_units == "21.00 to 128.50 ppm"


# --- a projection never invents a total ----------------------------------


def test_the_declared_total_leads_and_is_the_producers_own():
    """It is the number the row was opened for. A LogP contribution summary
    with no LogP in it is true and useless."""
    result = _per_atom(
        {0: 0.1, 1: -0.4},
        provenance=Provenance(
            created_by="core", method="crippen",
            parameters={TOTAL: declare_total(1.31, "LogP (Crippen)", "")},
        ),
    )
    facts = _view(result).facts
    assert facts[0].label == "LogP (Crippen)"
    assert facts[0].value == pytest.approx(1.31)


def test_an_undeclared_total_produces_no_total_row_rather_than_a_sum():
    """**THE `Overall:` BUG, REFUSED IN A NEW PLACE.** Summing per-atom values
    put a net -1.36 e on a neutral molecule, which is why `TOTAL` exists at
    all. The sum of these two is 0.3 and it must appear nowhere."""
    result = _per_atom({0: 0.1, 1: 0.2})
    labels = [f.label for f in _view(result).facts]
    assert "Total" not in labels
    displays = [f.display_value for f in _view(result).facts]
    assert not any("0.3" == d for d in displays), displays


def test_an_explicit_refusal_produces_no_total_either():
    result = _per_atom(
        {0: 1.0},
        provenance=Provenance(
            created_by="core", method="m",
            parameters={TOTAL: decline_total("a per-atom eccentricity has no molecular total")},
        ),
    )
    assert len(_view(result).facts) == 3, "count, range and basis -- no total"


def test_a_categorical_dataset_gets_a_count_and_no_range():
    """A span over oxidation-state category ids is a quantity nobody
    computed."""
    result = _per_atom({0: "sp3", 1: "sp2"})
    labels = [f.label for f in _view(result).facts]
    assert "Atoms" in labels
    assert "Range" not in labels


def test_the_atom_basis_is_carried_because_it_changes_what_the_values_are():
    """A value keyed to explicit hydrogens and one keyed to heavy atoms are
    different data under the same name."""
    result = _per_atom(
        {0: 1.0},
        provenance=Provenance(
            created_by="core", method="m", parameters={ATOM_BASIS: "explicit_h"}
        ),
    )
    facts = {f.label: f for f in _view(result).facts}
    assert "hydrogens included" in facts["Keyed to"].display_value
    plain = {f.label: f for f in _view(_per_atom({0: 1.0})).facts}
    assert HEAVY_ATOMS.replace("_", " ") in plain["Keyed to"].display_value


# --- a pH curve keeps its producer's own scalars -------------------------


def test_a_ph_curves_declared_facts_pass_through_first_and_unchanged():
    """`PhCurveResult.facts` is where the pI and the LogP live -- scalars a
    producer COMPUTED, which used to be interpolated into the display name
    because there was nowhere to put them. A projection may not restate or
    reorder them."""
    from openchem.domain.report import Fact, FactCategory

    declared = Fact(
        category=FactCategory.ELECTRONIC, label="Isoelectric point (pI)",
        value=5.97, display_value="5.97", source="pkasolver", basis=Basis.HEURISTIC,
    )
    result = PhCurveResult(
        curve_id="c", name="Charge vs pH", method="m", molecule_uuid=MOLECULE,
        ph_values=[1.0, 7.0, 14.0], series={"net charge": [1.0, 0.0, -1.0]},
        facts=(declared,),
    )
    facts = _view(result).facts
    assert facts[0] is declared, "the producer's own fact, not a copy"
    assert [f.label for f in facts[1:]] == ["Series", "pH range"]


def test_a_ph_curve_projects_its_chart_through_the_one_existing_adapter():
    """`ph_curve_widget.annotation_for` is what the pH dialog draws from, so
    the reader and that dialog cannot disagree about the picture. A second
    pairing of the grid with the series is exactly where a double transform
    would hide."""
    from openchem.ui.widgets.ph_curve_widget import annotation_for

    result = PhCurveResult(
        curve_id="c", name="C", method="m", molecule_uuid=MOLECULE,
        ph_values=[1.0, 7.0], series={"a": [0.0, 1.0]},
    )
    charts = _view(result).charts
    assert len(charts) == 1
    assert charts[0] == annotation_for(result)


def test_a_ph_curve_with_no_data_projects_no_chart():
    result = PhCurveResult(curve_id="c", name="C", method="m", molecule_uuid=MOLECULE)
    assert _view(result).charts == ()


# --- counts, not contents ------------------------------------------------


def test_a_structure_set_reports_counts_and_never_a_smiles_list():
    """A hundred structures rendered as facts is the wall the reader exists
    to avoid, and the set already has an inspector that draws them."""
    result = StructureSetResult(
        set_id="s", name="Tautomers", method="m", molecule_uuid=MOLECULE,
        entries=[StructureEntry(molblock="") for _ in range(12)],
        total_available=100, truncated=True,
    )
    facts = {f.label: f for f in _view(result).facts}
    assert facts["Structures"].display_value == "12"
    assert facts["Available"].display_value == "100"
    assert "first 12" in facts["Showing"].display_value
    assert not any("molblock" in f.display_value for f in _view(result).facts)


def test_an_untruncated_set_says_neither_available_nor_showing():
    """The narrow half: a set that is showing everything must not carry a
    caveat about what it is hiding."""
    result = StructureSetResult(
        set_id="s", name="S", method="m", molecule_uuid=MOLECULE,
        entries=[StructureEntry(molblock="")], total_available=1,
    )
    labels = [f.label for f in _view(result).facts]
    assert labels == ["Structures"]


def test_a_trajectorys_final_energy_appears_only_if_there_are_energies():
    """Reporting `0.0` for a trajectory with no energy series would be a
    number nobody computed sitting where a real energy goes."""
    with_energy = TrajectoryResult(
        trajectory_id="t", name="MD", method="m", molecule_uuid=MOLECULE,
        frames=["", ""], times=[0.0, 1.0], energies=[5.0, 3.0], temperature=300.0,
    )
    facts = {f.label: f for f in _view(with_energy).facts}
    assert facts["Final energy"].value == pytest.approx(3.0)
    assert facts["Temperature"].display_value == "300"

    without = TrajectoryResult(
        trajectory_id="t", name="MD", method="m", molecule_uuid=MOLECULE,
        frames=["", ""], times=[0.0, 1.0],
    )
    assert "Final energy" not in {f.label for f in _view(without).facts}


# --- a summary says it is one, and carries the producer's status ---------


def test_every_summary_says_it_is_a_summary():
    """0d's rule, rendered: a presentation projection must be IDENTIFIED as
    one, or a reader cannot tell a derived count from a declared value."""
    view = _view(_per_atom({0: 1.0}))
    assert view.limitations[0] == SUMMARY_LIMITATION


def test_a_producers_own_caveats_come_after_the_summarys():
    """A reader meeting the producer's caveats under a summary would have no
    way to tell which half it was reading."""
    result = PhCurveResult(
        curve_id="c", name="C", method="m", molecule_uuid=MOLECULE,
        ph_values=[1.0], series={"a": [0.0]},
    )
    object.__setattr__(result, "limitations", ("pkasolver predicts per-site values",))
    view = _view(result)
    assert view.limitations[0] == SUMMARY_LIMITATION
    assert "per-site" in view.limitations[1]


def test_a_refused_result_carries_its_refusal_rather_than_reading_as_empty():
    """**A REFUSED CALCULATOR HAS FEWER FACTS TO PROJECT**, so it is exactly
    the one a summary would otherwise render as a producer that ran and had
    nothing to say -- the statement `merge_reports` stopped making when it
    stopped gating on facts."""
    result = PhCurveResult(
        curve_id="c", name="Solubility vs pH", method="m", molecule_uuid=MOLECULE,
        cache_state=CacheState.FAILED,
        error="pkasolver is not configured -- set it in Tools > External Tools",
        error_summary="pkasolver not configured",
    )
    view = _view(result)
    assert view.cache_state is CacheState.FAILED
    assert view.error_summary == "pkasolver not configured"
    assert "External Tools" in view.error


def test_a_summary_is_stamped_with_the_structure_it_describes():
    """**NONE OF THESE KINDS CARRIES A `structure_version`** -- only
    `StructureReport` does -- so an unstamped summary reads as stale the
    moment the structure moves past 0, which is exactly what alert-derived
    reports used to do."""
    assert _view(_per_atom({0: 1.0}), structure_version=7).structure_version == 7


# --- the two kinds that need no projection -------------------------------


def test_a_report_passes_through_whole():
    """Wrapping it would flatten its provenance into a view."""
    report = ReportResult(molecule_uuid=MOLECULE, report_id="r", name="R")
    assert summarise(report, result_id="r", name="R") is report


def test_an_alert_goes_through_the_one_bridge_that_keeps_its_status():
    """A view built from an alert's facts alone would render a refused
    catalog as one that ran and found nothing."""
    alert = AlertResult(
        alert_id="pains", name="PAINS", molecule_uuid=MOLECULE, matched=[],
        cache_state=CacheState.FAILED, error="needs a 3D conformer",
    )
    bridged = summarise(alert, result_id="pains", name="PAINS")
    assert isinstance(bridged, ReportResult)
    assert bridged.cache_state is CacheState.FAILED
    assert bridged.error == "needs a 3D conformer"


@pytest.mark.parametrize("kind", [REPORT, ALERT])
def test_the_already_readable_kinds_refuse_to_be_projected(kind):
    """It RAISES rather than returning `()`, because an empty projection is
    indistinguishable from a result that genuinely had nothing to say -- and
    for these two the answer is not a projection at all."""
    from openchem.domain.report import FactCategory

    assert ADAPTERS[kind].summary is _no_summary_needed
    with pytest.raises(TypeError, match="already report-shaped"):
        _no_summary_needed(object(), FactCategory.IDENTITY)


# --- the population it has to work over ----------------------------------


@pytest.mark.parametrize("smiles", ["CC(=O)Oc1ccccc1C(=O)O"])
def test_every_calculator_the_registry_runs_becomes_a_reader_entry(smiles):
    """**THE MEASUREMENT THIS STAGE EXISTS FOR.** Before it, 30 of 60
    calculators produced a result `merge_reports` refused, so half the
    application's output reached the reader not at all.

    Runs the REAL registry rather than a fixture, for the reason
    `test_batch_service` gives: the thing worth testing is that every
    registered calculator survives being summarised in one pass, which is
    precisely what a mock cannot tell you.
    """
    from rdkit import Chem

    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
    from openchem.domain.calculator import RegistryExecution

    id_fields = ("report_id", "alert_id", "property_id", "curve_id", "set_id",
                 "trajectory_id", "spectrum_type")
    mol = Chem.MolFromSmiles(smiles)
    entries = []
    for definition in CALCULATOR_DEFINITIONS:
        if not isinstance(definition.execution, RegistryExecution):
            continue
        try:
            result = definition.execution.compute(
                mol, MOLECULE, {p.name: p.default for p in definition.parameters}
            )
        except Exception:  # noqa: BLE001 - a calculator that raises is not the subject
            continue
        result_id = next(
            (getattr(result, f) for f in id_fields if getattr(result, f, None)),
            definition.calculator_id,
        )
        entries.append(
            summarise(
                result, result_id=result_id, name=result.name,
                category=definition.category, structure_version=1,
            )
        )

    assert len(entries) >= 50, f"fixture is degenerate: only {len(entries)} ran"
    unreadable = [e for e in entries if not is_report_shaped(e)]
    assert not unreadable, [type(e).__name__ for e in unreadable]
    merged = merge_reports(entries, structure_version=1)
    assert len(merged.reports) == len(entries), "the merge admitted every one"


def test_a_summary_is_a_view_and_not_a_report():
    """The name's job, holding for the per-kind summaries too: persisting one
    would attribute presentation-DERIVED facts to a producer that never
    declared them."""
    view = _view(_per_atom({0: 1.0}))
    assert isinstance(view, ResultSummaryView)
    assert not isinstance(view, ReportResult)
    assert kind_of(_per_atom({0: 1.0})) == PER_ATOM


# --- the three the mutation pass found, and none was an equivalent -------
#
# A9, A10 and A13 below each SURVIVED the first pass against 213 green tests.
# All three were claims made in a docstring and enforced by nothing, which is
# this project's most-repeated failure: a comment asserting an intention is
# believed, and then quoted.


def test_a_projected_fact_carries_the_PRODUCERS_source_and_never_the_view():
    """**THE VIEW SAYS IT PROJECTED; `Fact.source` SAYS WHERE THE SCIENCE CAME
    FROM.**

    Stamping "summary" there would destroy real provenance in order to record
    a different kind of it -- exactly the distinction `Fact.origin` was added
    for rather than reusing `source`. It is also SEARCHABLE: `find_facts`
    matches source, so a view naming itself there makes one word match every
    projected row in the reader.

    What says "this was projected" is the entry's limitation, which is a
    statement about the whole entry rather than a claim about one value.
    """
    result = _per_atom({0: 0.1, 1: 0.2}, method="crippen")
    facts = _view(result).facts
    assert facts, "the fixture must produce rows for this to say anything"
    for fact in facts:
        assert fact.source == "crippen", fact.label


def test_a_producer_with_no_method_falls_back_to_core_and_not_to_the_view():
    """The narrow half. "Never `summary`" is satisfied by a fallback that
    names the view under another word; the fallback is the same `"core"` every
    other producer-less fact in the application uses."""
    result = _per_atom({0: 0.1}, method="")
    for fact in _view(result).facts:
        assert fact.source == "core", fact.label


def test_the_declared_total_understates_its_basis_rather_than_claiming_certainty():
    """**ERR TOWARD UNDERSTATING, AND THE DECLARATION'S OWN `basis` IS NOT
    THIS ONE.**

    `declare_total(..., basis=HEAVY_ATOMS)` says WHICH ATOMS the total is
    over -- reading it as a scientific `Basis` raises, which is how that was
    found rather than shipped. The producer declares no scientific basis, so
    none may be invented, and claiming a fitted Crippen total as
    DETERMINISTIC -- "right, or the periodic table is wrong" -- is the
    overstatement this vocabulary exists to refuse.
    """
    result = _per_atom(
        {0: 0.1, 1: -0.4},
        provenance=Provenance(
            created_by="core", method="crippen",
            parameters={TOTAL: declare_total(1.31, "LogP (Crippen)", "")},
        ),
    )
    facts = _view(result).facts
    assert facts[0].label == "LogP (Crippen)"
    assert facts[0].basis is Basis.HEURISTIC


def test_a_counted_projection_stays_deterministic():
    """The narrow half, and it is load-bearing: marking every projected fact
    HEURISTIC satisfies the guard above and understates a COUNT, which is
    arithmetic over what arrived and cannot be a judgement."""
    result = _per_atom({0: 0.1, 1: 0.2})
    atoms = next(f for f in _view(result).facts if f.label == "Atoms")
    assert atoms.basis is Basis.DETERMINISTIC


def test_the_section_comes_from_the_caller_because_the_result_carries_none():
    """**A SUMMARY THAT READ ITS SECTION OFF THE RESULT WOULD FILE TWENTY
    READER ENTRIES UNDER "Other".**

    Measured over every non-report result the registry produces for aspirin:
    `PerAtomDataset.category` is empty for all twelve of them, and
    `PhCurveResult`, `StructureSetResult`, `TrajectoryResult` and
    `NMRSpectrumResult` have no such field at all. That is the section
    miscategorisation 0h exists to remove, arriving through a different door
    -- and it would be invisible, because "Other" is a real section.

    Both halves are asserted, because they are read by different things: the
    string is what `result_ordering` groups by, and the `FactCategory` is what
    `FactView` sections the values by.
    """
    result = _per_atom({0: 1.0})
    assert getattr(result, "category", "") == "", (
        "the fixture must be as bare as the real ones, or this passes vacuously"
    )
    view = _view(result, category="topology")
    assert view.category == "topology"
    assert view.facts
    for fact in view.facts:
        assert fact.category is FactCategory.TOPOLOGY, fact.label
