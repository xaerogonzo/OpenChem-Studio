"""The merged results window, driven through the panel that owns it.

**LIFECYCLE, NOT MERGING.** `test_merged_results_dialog.py` holds the
window's own behaviour; this file holds the things only the panel can be
wrong about -- which window exists, when it is fed, and what happens when
it closes. An ordinary Qt lifetime bug is exactly the class the merge
being correct cannot catch, and this repository has paid for the
self-capturing-lambda form of it four times.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QEvent

from openchem.chem.engine import ChemistryEngine
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.report import Basis, Fact, FactCategory, ReportResult
from openchem.events.base import EventBus
from openchem.events.events import MoleculeSelected, ReportComputed
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.descriptor_service import DescriptorService
from openchem.ui.widgets.results_view import STALE_MARK, ResultsView
from openchem.ui.panels.property_panel import PropertyPanel
from tests.conftest import dispose


def _fact(label: str) -> Fact:
    return Fact(
        category=FactCategory.IDENTITY,
        label=label,
        value=label,
        display_value=label,
        source="RDKit",
        basis=Basis.DETERMINISTIC,
    )


def _report(report_id: str, name: str, label: str, uuid: str, version: int = 0):
    return ReportResult(
        molecule_uuid=uuid,
        report_id=report_id,
        name=name,
        facts=(_fact(label),),
        structure_version=version,
    )


class _Versions:
    """A stand-in for `StructureCheckService.current_version`.

    A callable rather than the service, which is what the panel takes --
    so a fixture does not have to build a checker to have a version."""

    def __init__(self) -> None:
        self.version = 0

    def __call__(self, _uuid: str) -> int:
        return self.version


@pytest.fixture
def panel(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    versions = _Versions()
    widget = PropertyPanel(
        bus,
        CalculatorRegistry(),
        DescriptorService(bus, engine, calculator_registry=CalculatorRegistry()),
        engine,
        structure_version_of=versions,
    )
    molecule = MoleculeModel()
    engine.set_structure_from_smiles(molecule, "CCO")
    project = ProjectModel(molecules=[molecule])
    widget.set_project(project)
    # THE PERSISTENT READER, attached as the application attaches one. The
    # panel used to build a window on demand; it is handed a reader now, so
    # every test below reads `widget._attached_reader`.
    reader = ResultsView()
    widget.attach_reader(reader)
    bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))
    yield widget, bus, molecule, project, versions
    dispose(reader)
    dispose(widget)


def _land(bus, report):
    bus.publish(ReportComputed(report=report))
    QCoreApplication.processEvents()


def test_one_window_per_molecule_and_asking_twice_reuses_it(panel):
    """**KEYED ON THE UUID, NOT ON OBJECT IDENTITY.** Two windows for one
    molecule is how a reader ends up comparing a result with itself, and
    only one of them would be receiving updates."""
    widget, bus, molecule, _project, _versions = panel
    _land(bus, _report("a", "A", "Formula", molecule.uuid))
    widget._show_in_reader()
    first = widget._attached_reader
    widget._show_in_reader()
    assert widget._attached_reader is first
    first.close()


def test_a_result_arriving_updates_the_OPEN_window(panel):
    """**THE FEATURE, NOT THE MERGE.** Proving a freshly-opened window can
    merge is easy and is not the complaint: the window has to accumulate
    while it is open, which is why it is modeless in the first place."""
    widget, bus, molecule, _project, _versions = panel
    _land(bus, _report("a", "Elemental Analysis", "Formula", molecule.uuid))
    widget._show_in_reader()
    window = widget._attached_reader
    assert [f.label for f in window.merged().facts] == ["Formula"]

    _land(bus, _report("b", "Lewis Sites", "Donor sites", molecule.uuid))
    assert [f.label for f in window.merged().facts] == ["Formula", "Donor sites"]
    window.close()


def test_the_stale_marks_follow_the_structure_in_an_open_window(panel):
    widget, bus, molecule, _project, versions = panel
    _land(bus, _report("a", "Elemental Analysis", "Formula", molecule.uuid, version=0))
    widget._show_in_reader()
    window = widget._attached_reader
    assert STALE_MARK not in window._focus_box.itemText(1)

    versions.version = 3
    _land(bus, _report("b", "Lewis Sites", "Donor sites", molecule.uuid, version=3))
    labels = [window._focus_box.itemText(i) for i in range(window._focus_box.count())]
    assert "Elemental Analysis" + STALE_MARK in labels
    assert "Lewis Sites" in labels
    window.close()


def test_an_alert_derived_report_is_not_born_stale(panel):
    """**FOUND BY DRIVING THE APP, WITH EVERY TEST GREEN.**
    `_CalculationTask` stamps a `ReportResult` on the way out of a
    calculation -- but an `AlertResult` is not one, has no version field to
    carry, and is reconstructed into a report by the panel at arrival. Left
    unstamped it defaults to 0 and reads as stale the moment the structure
    is on any version above that.

    On screen that was `Functional Groups` wearing a stale badge alone,
    from the first molecule, forever -- while every registry calculator
    beside it read current. Every test in this suite passed throughout,
    because they all construct reports with an explicit version.
    """
    from openchem.domain.scientific_result import AlertResult
    from openchem.events.events import AlertComputed

    widget, bus, molecule, _project, versions = panel
    versions.version = 4
    bus.publish(
        AlertComputed(
            alert=AlertResult(
                alert_id="functional_groups",
                name="Functional Groups",
                molecule_uuid=molecule.uuid,
                matched=["Carboxylic acid: 1"],
                category="substructure",
            )
        )
    )
    QCoreApplication.processEvents()

    widget._show_in_reader()
    window = widget._attached_reader
    assert window.merged().stale_report_ids() == (), (
        "a report that has just arrived describes the structure it arrived for"
    )
    window.close()


# --- the auto-descriptors reach the reader -------------------------------
#
# They are `DescriptorValue`s rather than `ScientificResult`s, so before the
# aggregate existed they reached the reader's fact model NOT AT ALL -- the
# single largest thing computed for a molecule that this window could not
# show. See `domain/descriptor_aggregate.py` for why it holds the originals.


def _descriptor(bus, molecule, descriptor_id, **kwargs):
    from openchem.domain.common import CacheState
    from openchem.domain.descriptor import DescriptorValue
    from openchem.events.events import DescriptorComputed

    defaults = dict(
        descriptor_id=descriptor_id,
        name=descriptor_id.replace("_", " ").title(),
        units="",
        category="physicochemical",
        provider="rdkit",
        molecule_uuid=molecule.uuid,
        cache_state=CacheState.COMPLETED,
    )
    defaults.update(kwargs)
    bus.publish(DescriptorComputed(descriptor=DescriptorValue(**defaults)))
    QCoreApplication.processEvents()


def test_the_descriptors_reach_the_results_window_as_one_entry(panel):
    """ONE entry, not forty-one. The window's selector is the surface this
    would otherwise flood."""
    from openchem.domain.descriptor_aggregate import DESCRIPTOR_AGGREGATE_ID

    widget, bus, molecule, _project, _versions = panel
    _descriptor(bus, molecule, "mol_wt", name="Molecular Weight", units="g/mol", value=46.07)
    _descriptor(bus, molecule, "tpsa", name="TPSA", units="A^2", value=20.23)
    widget._show_in_reader()

    merged = widget._attached_reader.merged()
    ids = [r.report_id for r in merged.reports]
    assert ids.count(DESCRIPTOR_AGGREGATE_ID) == 1, f"expected one aggregate, got {ids}"
    labels = {f.label for f in merged.facts}
    assert {"Molecular Weight", "TPSA"} <= labels


def test_a_failed_descriptor_keeps_its_own_state_in_the_window(panel):
    """The reason the aggregate is a container. A molecule drawn flat fails
    the ten shape descriptors while the other thirty-one succeed, and one
    report-level `cache_state` cannot say that."""
    from openchem.domain.common import CacheState
    from openchem.domain.descriptor_aggregate import DESCRIPTOR_AGGREGATE_ID

    widget, bus, molecule, _project, _versions = panel
    _descriptor(bus, molecule, "mol_wt", name="Molecular Weight", units="g/mol", value=46.07)
    _descriptor(
        bus, molecule, "spherocity_index", name="Spherocity Index", category="shape",
        cache_state=CacheState.FAILED,
        error="Needs a real 3D conformer - generate one first",
        error_summary="Needs a 3D conformer",
    )
    widget._show_in_reader()

    aggregate = widget._attached_reader.merged().report_for(DESCRIPTOR_AGGREGATE_ID)
    states = {d.descriptor_id: d.cache_state for d in aggregate.descriptors}
    assert states["mol_wt"] is CacheState.COMPLETED
    assert states["spherocity_index"] is CacheState.FAILED
    assert [d.descriptor_id for d in aggregate.failed()] == ["spherocity_index"]


def test_a_running_placeholder_is_replaced_rather_than_accumulated(panel):
    """Every descriptor arrives TWICE -- `DescriptorService` publishes a
    RUNNING placeholder before `compute()` runs. Keyed by id, so the result
    replaces the placeholder instead of sitting beside it."""
    from openchem.domain.common import CacheState
    from openchem.domain.descriptor_aggregate import DESCRIPTOR_AGGREGATE_ID

    widget, bus, molecule, _project, _versions = panel
    _descriptor(bus, molecule, "mol_wt", cache_state=CacheState.RUNNING)
    _descriptor(bus, molecule, "mol_wt", name="Molecular Weight", value=46.07)
    widget._show_in_reader()

    aggregate = widget._attached_reader.merged().report_for(DESCRIPTOR_AGGREGATE_ID)
    assert len(aggregate.descriptors) == 1
    assert aggregate.descriptors[0].cache_state is CacheState.COMPLETED


def test_switching_molecule_does_not_carry_the_descriptors_over(panel):
    """A leftover set would appear under the new molecule's name with nothing
    saying otherwise -- the same rule the reports and the open window follow."""
    widget, bus, molecule, project, _versions = panel
    _descriptor(bus, molecule, "mol_wt", value=46.07)
    assert widget._descriptor_values

    other = MoleculeModel()
    project.molecules.append(other)
    bus.publish(MoleculeSelected(molecule_uuid=other.uuid))
    QCoreApplication.processEvents()
    assert not widget._descriptor_values


def test_no_aggregate_appears_before_any_descriptor_has_landed(panel):
    """The narrow half. An empty "Molecular Properties" entry would be a
    heading promising values nothing has computed yet."""
    from openchem.domain.descriptor_aggregate import DESCRIPTOR_AGGREGATE_ID

    widget, bus, molecule, _project, _versions = panel
    _land(bus, _report("a", "A", "Formula", molecule.uuid))
    widget._show_in_reader()
    ids = [r.report_id for r in widget._attached_reader.merged().reports]
    assert DESCRIPTOR_AGGREGATE_ID not in ids


def test_the_aggregate_is_shown_above_every_calculator(panel):
    """**THE ONE ENTRY THAT IS ALWAYS THERE MUST NOT BE AT THE BOTTOM.** It
    was appended last, so the 41 always-computed descriptors sat below every
    calculator that happened to have run -- and its 41 descriptors span ten
    categories, so no section is true of it either. It declares the always-on
    band and sorts above the sections.
    """
    from openchem.domain.descriptor_aggregate import DESCRIPTOR_AGGREGATE_ID

    widget, bus, molecule, _project, _versions = panel
    _descriptor(bus, molecule, "mol_wt", name="Molecular Weight", value=46.07)
    assert widget._descriptor_values, "fixture is degenerate: no descriptors landed"
    _land(bus, _report("a", "A", "Formula", molecule.uuid))
    widget._show_in_reader()
    ids = [r.report_id for r in widget._attached_reader.merged().reports]
    assert ids[0] == DESCRIPTOR_AGGREGATE_ID, ids


# --- the ordering the panel is the only thing that can supply -------------


def _definition(calculator_id: str, display_name: str, category: str):
    from openchem.domain.calculator import CalculatorDefinition, RegistryExecution

    return CalculatorDefinition(
        calculator_id=calculator_id,
        display_name=display_name,
        category=category,
        description=f"{display_name}. Runs nothing in this fixture.",
        execution=RegistryExecution(compute=lambda _mol, _uuid, _params: None),
    )


def test_the_reader_orders_by_the_registrys_own_order(qapp):
    """**THE WIRING, END TO END, AND THE FIXTURE HAS TO CONTRADICT THE
    FALLBACK.**

    Somebody has to tell the reader where a calculator sits in its section;
    drop the argument and it still orders -- by NAME -- which is a plausible
    list that silently disagrees with the buttons above it. Measured on the
    shipped registry, that is the arrangement that puts Hansen Solubility
    Parameters ahead of Solubility.

    So the two calculators here are registered in the order that INVERTS
    their names: nothing but the registry position can produce the expected
    list, and the `panel` fixture's empty registry could not have shown it.

    **THE SUPPLIER MOVED WITH THE READER.** The panel used to pass it when
    it built the window; the reader is constructed by whoever owns it now,
    so the window does. That makes this a test of the ORDERING rather than
    of who supplies it -- `tests/test_results_dock.py` holds the other half,
    that the application really does supply it.
    """
    bus = EventBus()
    engine = ChemistryEngine()
    registry = CalculatorRegistry()
    registry.register(_definition("zulu", "Zulu", "solubility"))
    registry.register(_definition("alpha", "Alpha", "solubility"))
    widget = PropertyPanel(
        bus,
        registry,
        DescriptorService(bus, engine, calculator_registry=registry),
        engine,
        structure_version_of=_Versions(),
    )
    molecule = MoleculeModel()
    engine.set_structure_from_smiles(molecule, "CCO")
    widget.set_project(ProjectModel(molecules=[molecule]))
    reader = ResultsView(display_order_of=registry.display_order)
    widget.attach_reader(reader)
    bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))

    assert registry.display_order("zulu") == 0
    assert registry.display_order("alpha") == 1, "the fixture must invert the names"

    _land(bus, _report("alpha", "Alpha", "A", molecule.uuid))
    _land(bus, _report("zulu", "Zulu", "Z", molecule.uuid))
    widget._show_in_reader()
    window = widget._attached_reader
    ids = [
        r.report_id
        for r in window.merged().reports
        if r.report_id in ("zulu", "alpha")
    ]
    assert ids == ["zulu", "alpha"], ids
    dispose(window)
    dispose(widget)


# --- where each molecule's reader was left --------------------------------


def _open(widget, focus: str = ""):
    widget._show_in_reader(focus=focus)
    return widget._attached_reader


def test_reopening_restores_the_report_that_was_being_read(panel):
    """**A WINDOW KEYED ON A MOLECULE IS THROWN AWAY, SO ITS POSITION HAD TO
    BE.** Closing and reopening handed the reader "All results" and an empty
    box, whatever they had been looking at a second earlier."""
    widget, bus, molecule, _project, _versions = panel
    _land(bus, _report("a", "A", "Formula", molecule.uuid))
    _land(bus, _report("b", "B", "Donor sites", molecule.uuid))

    window = _open(widget)
    window.set_focus("b")
    window.close()
    QCoreApplication.processEvents()

    assert _open(widget).focus() == "b"


def test_reopening_restores_the_filter_too(panel):
    """The search text is a reading position as much as the report is."""
    widget, bus, molecule, _project, _versions = panel
    _land(bus, _report("a", "A", "Formula", molecule.uuid))

    window = _open(widget)
    window._view.search_box().setText("form")
    window.close()
    QCoreApplication.processEvents()

    reopened = _open(widget)
    assert reopened._view.filter_state() == ("form", False)


def test_an_explicit_details_press_beats_the_remembered_position(panel):
    """Pressing "Details..." beside a calculator is asking for THAT report.
    A memory that overrode it would make the button do something other than
    what it says."""
    widget, bus, molecule, _project, _versions = panel
    _land(bus, _report("a", "A", "Formula", molecule.uuid))
    _land(bus, _report("b", "B", "Donor sites", molecule.uuid))

    window = _open(widget)
    window.set_focus("b")
    window.close()
    QCoreApplication.processEvents()

    assert _open(widget, focus="a").focus() == "a"


def test_a_stale_report_is_restored_rather_than_jumped_away_from(panel):
    """**THE RULE THIS WIRING EXISTS FOR.** A stale result is a record of what
    was computed, and this project refuses to discard one everywhere else;
    jumping away from a stale selection discards it in the one place somebody
    is looking.

    The memory is never told about staleness -- it restores whatever still
    EXISTS -- so the rule lives in what the panel OFFERS, and this is the
    guard for that. Filtering the offer to current results would silently
    reinstate exactly the behaviour the rule forbids.
    """
    widget, bus, molecule, _project, versions = panel
    _land(bus, _report("bbb_score", "BBB Score", "Score", molecule.uuid, version=1))
    versions.version = 1

    window = _open(widget)
    window.set_focus("bbb_score")
    window.close()
    QCoreApplication.processEvents()

    # The structure moves under it: the report is now stale, and still there.
    versions.version = 2
    reopened = _open(widget)
    assert reopened.merged().stale_report_ids() == ("bbb_score",), (
        "fixture is degenerate: the report must really be stale, or this "
        "guard passes against a memory that only ever restores current ones"
    )
    assert reopened.focus() == "bbb_score"


def test_a_report_that_is_gone_falls_back_and_the_filter_survives(panel):
    """Selecting another molecule clears this one's results, so returning
    finds the remembered report genuinely absent. Falling back to all results
    is right; clearing the search box with it is not -- the filter is about
    what somebody is looking FOR, and the memory is per molecule, so nothing
    inherits another's."""
    widget, bus, molecule, project, _versions = panel
    _land(bus, _report("a", "A", "Formula", molecule.uuid))
    window = _open(widget)
    window.set_focus("a")
    window._view.search_box().setText("form")

    other = MoleculeModel()
    project.molecules.append(other)
    bus.publish(MoleculeSelected(molecule_uuid=other.uuid))
    QCoreApplication.processEvents()
    bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))
    QCoreApplication.processEvents()

    _land(bus, _report("b", "B", "Donor sites", molecule.uuid))
    reopened = _open(widget)
    assert reopened.merged().report_for("a") is None, (
        "fixture is degenerate: the remembered report must really be gone"
    )
    assert reopened.focus() == ""
    assert reopened._view.filter_state() == ("form", False)


def test_a_position_is_filed_under_the_window_s_molecule_not_the_panel_s(panel):
    """**THE ORDER `_on_molecule_selected` DOES THINGS IN IS A TRAP.** It sets
    the panel's uuid FIRST and closes the window after, so anything reading
    the PANEL's uuid to record a position would file the old molecule's
    reading position under the new molecule's name.

    The window records under its own `molecule_uuid()`, which cannot be wrong
    about which molecule it was showing. This asserts that rather than trusting
    the ordering to stay as it is.
    """
    widget, bus, molecule, project, _versions = panel
    _land(bus, _report("a", "A", "Formula", molecule.uuid))
    window = _open(widget)
    window.set_focus("a")

    other = MoleculeModel()
    project.molecules.append(other)
    bus.publish(MoleculeSelected(molecule_uuid=other.uuid))
    QCoreApplication.processEvents()

    memory = widget._reader_memory
    assert memory.recall(molecule.uuid, ["a"]).report_id == "a"
    assert memory.recall(other.uuid, ["a"]).report_id == "", (
        "the other molecule inherited a position it never had"
    )


def test_a_new_project_starts_every_reader_fresh(panel):
    widget, bus, molecule, _project, _versions = panel
    _land(bus, _report("a", "A", "Formula", molecule.uuid))
    window = _open(widget)
    window.set_focus("a")
    assert len(widget._reader_memory) == 1

    widget.set_project(ProjectModel(molecules=[]))
    assert len(widget._reader_memory) == 0


def test_an_alert_CATALOGUE_reaches_the_reader_like_everything_else(panel):
    """**THE FOUR CATALOGUES REACHED IT NEVER, AND NOTHING NOTICED.**

    `_on_alert_computed` recorded a report only `if not _is_catalog(alert)`,
    so PAINS, BRENK, mutagenicity alerts and hERG risk factors never
    entered `_reports` -- and `_reports` is what the reader is built from.

    FOUR, counted rather than quoted: `is_catalog`'s docstring said "5 of
    25" and had drifted, the fifth being a regulatory screen that now
    publishes a `ReportResult` and never came through this gate at all. Their only rendering
    anywhere was the red row in the Properties panel, which is exactly why
    it looked like a duplication rather than a gap.

    Stage 1a's claim that every result kind reaches the reader was
    therefore not quite true: `summarise` could always project an alert,
    and the panel was withholding one class of them.
    """
    from openchem.domain.common import Provenance
    from openchem.domain.scientific_result import AlertResult, Severity
    from openchem.events.events import AlertComputed

    widget, bus, molecule, _project, _versions = panel
    catalogue = AlertResult(
        alert_id="pains",
        name="PAINS",
        molecule_uuid=molecule.uuid,
        matched=["quinone_A(370)"],
        provenance=Provenance(created_by="core", method="rdkit"),
        category="medicinal_chemistry",
        severity=Severity.WARNING,
    )
    from openchem.chem.report_adapter import is_catalog

    assert is_catalog(catalogue), "setup: this must really be a catalogue"

    bus.publish(AlertComputed(alert=catalogue))
    QCoreApplication.processEvents()

    report = widget._attached_reader.merged().report_for("pains")
    assert report is not None, "a catalogue must reach the reader"
    # ONE FACT PER MATCH, which is more than the red line could carry.
    assert [f.display_value for f in report.facts] == ["quinone_A(370)"]


def test_an_informational_alert_still_reaches_it_too(panel):
    """The narrow half. "Record every alert" is the fix; a mutation that
    recorded ONLY catalogues would satisfy the guard above and lose the
    twenty that were working."""
    from openchem.domain.common import Provenance
    from openchem.domain.scientific_result import AlertResult, Severity
    from openchem.events.events import AlertComputed

    widget, bus, molecule, _project, _versions = panel
    info = AlertResult(
        alert_id="functional_groups",
        name="Functional Groups",
        molecule_uuid=molecule.uuid,
        matched=["carboxylic acid"],
        provenance=Provenance(created_by="core", method="rdkit"),
        category="substructure",
        severity=Severity.INFO,
    )
    bus.publish(AlertComputed(alert=info))
    QCoreApplication.processEvents()
    assert widget._attached_reader.merged().report_for("functional_groups") is not None


# --- what the alert ROWS used to say, now the panel has none -------------
#
# Stage 2c took the Properties panel's alert row out. Every claim below was
# asserted against `panel._alert_labels[...]` until then, and each one is
# re-asserted here against the surface that renders it now. They are wiring
# tests deliberately: the rule lives in the reader, but an alert reaching the
# reader AT ALL is something only the panel can be wrong about, and it was
# wrong about it for four whole catalogues.


def _alert(molecule_uuid, **overrides):
    from openchem.domain.common import Provenance
    from openchem.domain.scientific_result import AlertResult

    defaults = dict(
        alert_id="pains", name="PAINS", molecule_uuid=molecule_uuid, matched=[],
        category="medicinal_chemistry",
        provenance=Provenance(created_by="core", method="rdkit"),
    )
    defaults.update(overrides)
    return AlertResult(**defaults)


def _land_alert(bus, alert):
    from openchem.events.events import AlertComputed

    bus.publish(AlertComputed(alert=alert))
    QCoreApplication.processEvents()


def test_a_clean_CATALOGUE_says_it_checked_and_flagged_nothing(panel):
    """A verdict, and only a catalog is entitled to give one.

    **THE VERDICT USED TO STOP AT THE PANEL.** `report_from_alert` dropped
    `severity`, so measured before it was carried, a clean PAINS and an
    elemental analysis with no lines arrived at the reader BYTE-IDENTICAL --
    no facts, no severity, no limitations -- and the reader said the same
    neutral sentence over both. That is exactly the confusion
    `AlertResult.severity` was introduced to end one layer along: its own
    docstring says the field exists so a renderer can tell "contains a PAINS
    substructure" from "weighs 43.025". Once Properties stopped painting
    alerts, the reader WAS that renderer.
    """
    from openchem.domain.scientific_result import Severity

    widget, bus, molecule, _project, _versions = panel
    _land_alert(bus, _alert(molecule.uuid, matched=[], severity=Severity.WARNING))

    reader = widget._attached_reader
    report = reader.merged().report_for("pains")
    assert report is not None
    assert reader._summary_for(report) == "Checked, nothing flagged."


def test_a_REPORT_with_nothing_to_say_does_not_borrow_that_verdict(panel):
    """The other side of the verdict rule, and the half a single-direction
    fix would lose. An elemental analysis that produced no lines has checked
    nothing and cleared nothing, so it must not read as a clean catalog."""
    from openchem.domain.scientific_result import Severity

    widget, bus, molecule, _project, _versions = panel
    _land_alert(bus, _alert(
        molecule.uuid, alert_id="elemental_analysis", name="Elemental Analysis",
        matched=[], category="identity", severity=Severity.INFO,
    ))

    reader = widget._attached_reader
    report = reader.merged().report_for("elemental_analysis")
    summary = reader._summary_for(report)
    assert "flagged" not in summary and "Clean" not in summary, summary
    assert summary == "This ran and produced no values."


def test_a_flagged_CATALOGUE_still_reads_as_a_catalog_and_not_as_facts(panel):
    """PAINS is what `AlertResult` was written for, and a match there really
    is something to look at.

    The matches themselves render as facts below the summary, so the summary
    COUNTS them rather than restating them -- a third copy of one answer is
    what the panel's rows were removed for.
    """
    from openchem.domain.scientific_result import Severity

    widget, bus, molecule, _project, _versions = panel
    _land_alert(bus, _alert(
        molecule.uuid, matched=["rhod_sat_A(33)"], severity=Severity.WARNING,
    ))

    reader = widget._attached_reader
    report = reader.merged().report_for("pains")
    assert reader._summary_for(report) == "1 alert(s) matched."
    assert [f.display_value for f in report.facts] == ["rhod_sat_A(33)"]


def test_an_informational_result_is_not_dressed_up_as_alerts(panel):
    """20 of the 25 `alert_id`s in this codebase are reports, not catalogs --
    elemental analysis, topology indices, Huckel energies, the IUPAC name.
    All of them once rendered as "8 alert(s): Formula: CHNO, ..." in alert
    red, and red is reserved for failed, dangerous or invalid."""
    from openchem.domain.scientific_result import Severity

    widget, bus, molecule, _project, _versions = panel
    _land_alert(bus, _alert(
        molecule.uuid, alert_id="elemental_analysis", name="Elemental Analysis",
        matched=["Formula: CHNO", "Mass: 43.025", "C: 27.92%"],
        category="identity", severity=Severity.INFO,
    ))

    reader = widget._attached_reader
    report = reader.merged().report_for("elemental_analysis")
    assert "alert(s)" not in reader._summary_for(report)
    rendered = " ".join(f.label + f.display_value for f in report.facts)
    assert "Formula" in rendered, rendered


def test_a_FAILED_alert_carries_its_reason_rather_than_a_verdict(panel):
    """A FAILED result has an empty `matched`, and empty used to mean
    "Clean" -- in green, with the real message discarded. Geometry is the
    case: no 3D conformer, so the calculator returns FAILED carrying "This
    calculation needs a 3D conformer" and the panel reported success.

    A failure is not a verdict about the molecule, so the catalog line stays
    silent even for a catalog and the status line says what happened.
    """
    from openchem.domain.common import CacheState
    from openchem.domain.scientific_result import Severity

    widget, bus, molecule, _project, _versions = panel
    _land_alert(bus, _alert(
        molecule.uuid, alert_id="geometry_analysis", name="Geometry",
        matched=[], category="geometry", severity=Severity.WARNING,
        cache_state=CacheState.FAILED,
        error="This calculation needs a 3D conformer.",
    ))

    reader = widget._attached_reader
    summary = reader._summary_for(reader.merged().report_for("geometry_analysis"))
    assert "3D conformer" in summary
    assert "flagged" not in summary and "Clean" not in summary, summary


@pytest.mark.parametrize(
    ("alert_id", "name", "category"),
    [
        ("brenk", "BRENK (Reactive/Unstable Groups)", "admet"),
        ("mutagenicity_alerts", "Mutagenicity Alerts", "admet"),
        ("herg_risk_factors", "hERG Risk Factors", "admet"),
    ],
)
def test_an_alert_reaches_the_reader_under_the_category_ITS_PRODUCER_NAMED(
    panel, alert_id, name, category
):
    """Routing, which used to mean "which panel section drew the row".

    It still matters and it is still the producer's declaration -- BRENK's
    toxicity-relevant alerts belong under admet rather than medicinal
    chemistry -- but the consumer is the reader's grouped selector now. A
    category invented by the consumer is the blocklist failure this
    repository has already paid for; `alert.category` travels through
    `report_from_alert` untouched, and this is what says so.
    """
    widget, bus, molecule, _project, _versions = panel
    _land_alert(bus, _alert(
        molecule.uuid, alert_id=alert_id, name=name,
        matched=["something"], category=category,
    ))

    report = widget._attached_reader.merged().report_for(alert_id)
    assert report is not None, f"{alert_id} did not reach the reader at all"
    assert report.category == category


def test_the_pains_default_category_has_not_silently_changed(panel):
    """**THE DEFAULT, WHICH THE PARAMETRISED CASE ABOVE CANNOT SEE.**

    `AlertResult.category` defaults to `medicinal_chemistry` because PAINS
    was its only caller before a second catalog existed. Every other test
    here passes a category explicitly, so all of them would keep passing if
    that default changed underneath PAINS -- which is the one result it
    would silently move.
    """
    widget, bus, molecule, _project, _versions = panel
    from openchem.domain.common import Provenance
    from openchem.domain.scientific_result import AlertResult

    bare = AlertResult(
        alert_id="pains", name="PAINS", molecule_uuid=molecule.uuid,
        matched=["quinone_A(370)"],
        provenance=Provenance(created_by="core", method="rdkit"),
    )
    _land_alert(bus, bare)

    report = widget._attached_reader.merged().report_for("pains")
    assert report.category == "medicinal_chemistry"


def test_the_functional_groups_alert_arrives_under_the_section_ITS_PRODUCER_names(panel):
    """**THE PRODUCER'S OWN ALERT, NOT A HAND-BUILT ONE.**

    This used to construct its own `AlertResult` with `category="admet"` and
    was named for that section, so it asserted the routing and could say
    nothing about where the REAL result goes -- which is how
    `functional_groups` came to declare `admet` here while its registered
    calculator declared `substructure`, putting the BUTTON in one section
    and the always-on row in another.

    Running the shipped producer is what closes that: the category is read
    off the result rather than typed, so the two cannot drift again through
    this test. The row it used to land in is gone; the reader entry it lands
    in now is read the same way, and the reason for using the real producer
    is unchanged by the move.
    """
    from rdkit import Chem

    from openchem.chem.descriptor_providers import compute_fragment_group_alert

    widget, bus, molecule, _project, _versions = panel
    alert = compute_fragment_group_alert(
        Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O"), molecule.uuid
    )
    assert alert.matched, "fixture is degenerate: no groups matched"
    assert alert.category == "substructure", (
        "a fragment count is not an ADMET property, and its calculator "
        "already says so"
    )
    _land_alert(bus, alert)

    report = widget._attached_reader.merged().report_for("functional_groups")
    assert report is not None
    assert report.category == alert.category
    rendered = " ".join(f"{f.label}: {f.display_value}" for f in report.facts)
    assert "Ester" in rendered, rendered


# --- three more claims the rows were carrying ----------------------------


def test_a_batch_result_reaches_the_reader_without_anything_being_opened(panel):
    """"I can hit run on several things, and nothing noticeable happens."

    `_on_run_selected` deliberately does not set `_pending_calculator_id`
    (six stacked inspectors is not a saving), and every per-atom handler
    used to return early without it -- so a batch-run result was computed,
    published, and then rendered nowhere at all.

    The row that fixed it is gone, and the requirement is not: a result
    nobody explicitly asked for still has to ARRIVE somewhere a reader can
    find it, without a dialog opening itself. That place is the reader, fed
    whether or not it is the surface currently on screen.
    """
    from openchem.domain.common import Provenance
    from openchem.domain.scientific_result import PerAtomDataset
    from openchem.events.events import PerAtomDataComputed

    widget, bus, molecule, _project, _versions = panel
    bus.publish(
        PerAtomDataComputed(
            dataset=PerAtomDataset(
                property_id="gasteiger_charge",
                name="Partial Charge (Gasteiger)",
                units="e",
                method="rdkit",
                molecule_uuid=molecule.uuid,
                values={0: -0.4, 1: 0.1, 2: 0.3},
                provenance=Provenance(created_by="core", method="rdkit"),
            )
        )
    )
    QCoreApplication.processEvents()

    report = widget._attached_reader.merged().report_for("gasteiger_charge")
    assert report is not None, "a batch result left no trace anywhere"
    labelled = {fact.label: fact.display_value for fact in report.facts}
    assert labelled.get("Atoms") == "3", labelled
    assert widget._pending_calculator_id is None, (
        "a batch run must not leave a request behind for a later result to "
        "answer"
    )


def test_an_explicitly_run_calculator_is_FOCUSED_in_the_reader(panel):
    """The ADMET complaint: "the calculator produces nothing".

    It produced everything -- the sidecar ran, the model returned its
    endpoints, and the row rendered correctly about 900 px down a panel
    whose viewport is 372 px, inside a section collapsed by default near the
    bottom of twenty-odd others. Four of the six result shapes already
    answered a button press unmissably by opening their viewer; the two that
    rendered INLINE did not, so the more a result had to say, the better it
    was hidden.

    There is no row to scroll to now, so the request is answered where the
    result actually is. `set_focus` also records the position, so a reader
    opened afterwards is already on what was just run.
    """
    widget, bus, molecule, _project, _versions = panel
    _land(bus, _report("a", "Elemental Analysis", "Formula", molecule.uuid))
    widget._attached_reader.set_focus("")
    assert widget._attached_reader._focus == ""

    widget._pending_calculator_id = "admet_ml"
    _land_alert(bus, _alert(
        molecule.uuid, alert_id="admet_ml", name="ADMET (ADMET-AI)",
        category="admet", matched=["hERG blockade: 0.82"],
    ))

    assert widget._attached_reader._focus == "admet_ml", (
        "the result the user asked for is not what the reader is showing"
    )
    assert widget._pending_calculator_id is None, "the request was not consumed"


def test_a_result_nobody_asked_for_does_not_move_the_reader(panel):
    """The narrow half, and the one that makes the guard above mean
    something. "Always focus the newest result" satisfies it and is the
    defect this project already fixed once under another name: a reader that
    follows whichever calculation finished first cannot be read, because a
    batch run moves it out from under you."""
    widget, bus, molecule, _project, _versions = panel
    _land(bus, _report("a", "Elemental Analysis", "Formula", molecule.uuid))
    widget._attached_reader.set_focus("a")

    assert widget._pending_calculator_id is None, "setup: nothing was requested"
    _land_alert(bus, _alert(
        molecule.uuid, alert_id="pains", name="PAINS", matched=["quinone_A(370)"],
    ))

    assert widget._attached_reader._focus == "a"


def test_the_reader_keeps_the_WHOLE_reason_while_a_SUMMARY_takes_the_short_form(panel):
    """A READING SURFACE IS NOT A CELL, and treating them alike loses text.

    `describe_failure` owns both forms, and which one is right depends on
    how much room the surface has. The reader's summary line sits above a
    report and has room for a sentence: the pkasolver message is 344
    characters of install guidance and is the whole point of showing it. A
    single-line cell is the one that is short of room, and only it takes the
    short form.

    Both halves are asserted together because each alone is satisfiable by
    the wrong rule -- "always use the summary" passes one, "never use it"
    passes the other -- and this repository's own lesson is that reusing a
    mechanism whose invariants do not apply is not reuse.

    **BOTH HALVES ARE IN THE READER NOW.** The short half was the Properties
    panel's descriptor cell until 2c removed it; a descriptor's short form
    is `Fact.display_value` and its long form is `Fact.limitations`, so the
    asymmetry survived the move into a single object -- which is why the
    export had to be taught to carry the second, and had not been.
    """
    from openchem.domain.common import CacheState
    from openchem.domain.descriptor import DescriptorValue
    from openchem.domain.descriptor_aggregate import DESCRIPTOR_AGGREGATE_ID
    from openchem.events.events import DescriptorComputed

    reason = (
        "No pkasolver environment configured. Set the interpreter path "
        "under Tools > External Tools."
    )
    summary = "pkasolver not configured"

    widget, bus, molecule, _project, _versions = panel
    _land_alert(bus, _alert(
        molecule.uuid, alert_id="pka", name="pKa", matched=[], category="pka",
        cache_state=CacheState.FAILED, error=reason, error_summary=summary,
    ))
    bus.publish(
        DescriptorComputed(
            descriptor=DescriptorValue(
                descriptor_id="pbf",
                name="Plane of Best Fit",
                value=None,
                units="",
                provider="rdkit",
                molecule_uuid=molecule.uuid,
                category="shape",
                cache_state=CacheState.FAILED,
                error=reason,
                error_summary=summary,
            )
        )
    )
    QCoreApplication.processEvents()

    reader = widget._attached_reader
    # The roomy surface keeps every word of it...
    line = reader._summary_for(reader.merged().report_for("pka"))
    assert reason in line, line
    assert line != summary

    # ...and the one-line value takes the short form, with the sentence
    # travelling beside it rather than being discarded.
    fact = next(
        f for f in reader.merged().report_for(DESCRIPTOR_AGGREGATE_ID).facts
        if f.label == "Plane of Best Fit"
    )
    assert fact.display_value == summary
    assert fact.limitations == (reason,)
