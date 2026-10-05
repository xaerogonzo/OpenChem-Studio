"""A predicted spectrum is a per-atom result, so two methods' shifts compare like two charge models.

The case it exists for: the database lookup's 13C shifts against an ab initio run's, atom by atom.
`compare()` already refuses every way that goes wrong (another molecule, an edit between the runs,
other atoms, other units, one result twice); these tests pin that the spectrum REACHES it, and that
the refusals still hold on the way in, not that they exist.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication

from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import CacheState
from openchem.domain import compare as compare_module
from openchem.domain.compare import (
    ComparedResult,
    Comparison,
    CompareRefusal,
    compare,
    spectrum_as_per_atom,
)
from openchem.domain.molecule import MoleculeModel
from openchem.domain.project import ProjectModel
from openchem.domain.scientific_result import NMRSpectrumResult
from openchem.events.base import EventBus
from openchem.events.events import MoleculeSelected, SpectrumComputed
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.descriptor_service import DescriptorService
from openchem.ui.panels.property_panel import PropertyPanel
from tests.conftest import dispose


def _spectrum(uuid: str, method: str, values: dict[int, float], units: str = "ppm") -> NMRSpectrumResult:
    return NMRSpectrumResult(
        spectrum_type="nmr_13c", name="13C shifts", units=units, method=method, molecule_uuid=uuid,
        values=values, elements={i: "C" for i in values},
    )


def test_the_adapter_changes_the_shape_and_nothing_else():
    spectrum = _spectrum("u", "HOSE lookup", {0: 18.2, 1: 57.9})
    dataset = spectrum_as_per_atom(spectrum)
    assert dataset.values == spectrum.values and dataset.units == "ppm"
    assert dataset.method == "HOSE lookup" and dataset.molecule_uuid == "u"
    assert dataset.property_id == "nmr_13c"


def test_two_methods_on_one_structure_compare_atom_by_atom():
    a = ComparedResult(spectrum_as_per_atom(_spectrum("u", "HOSE lookup", {0: 18.2, 1: 57.9})))
    b = ComparedResult(spectrum_as_per_atom(_spectrum("u", "ORCA PBE0", {0: 17.0, 1: 60.1})))
    outcome = compare([a, b])
    assert isinstance(outcome, Comparison)
    assert [round(row.deltas[0], 1) for row in outcome.rows] == [-1.2, 2.2]


@pytest.mark.parametrize(
    "other, code",
    [
        (_spectrum("v", "ORCA PBE0", {0: 1.0, 1: 2.0}), "DIFFERENT_MOLECULES"),
        (_spectrum("u", "ORCA PBE0", {0: 1.0}), "DIFFERENT_ATOMS"),
        (_spectrum("u", "ORCA PBE0", {0: 1.0, 1: 2.0}, units="ppm (TMS)"), "DIFFERENT_UNITS"),
        (_spectrum("u", "HOSE lookup", {0: 1.0, 1: 2.0}), "SAME_RESULT_TWICE"),
    ],
)
def test_the_refusals_still_hold_for_a_spectrum(other, code):
    base = ComparedResult(spectrum_as_per_atom(_spectrum("u", "HOSE lookup", {0: 18.2, 1: 57.9})))
    outcome = compare([base, ComparedResult(spectrum_as_per_atom(other))])
    assert isinstance(outcome, CompareRefusal)
    assert outcome.code == getattr(compare_module, code)


@pytest.fixture
def panel(qapp):
    bus = EventBus()
    engine = ChemistryEngine()
    registry = CalculatorRegistry()
    widget = PropertyPanel(bus, registry, DescriptorService(bus, engine, calculator_registry=registry), engine)
    molecule = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(molecule, "CCO")
    widget.set_project(ProjectModel(molecules=[molecule]))
    bus.publish(MoleculeSelected(molecule_uuid=molecule.uuid))
    QCoreApplication.processEvents()
    yield widget, bus, molecule
    dispose(widget)


def _publish(bus, spectrum, fingerprint="f", calculation_input="drawing"):
    bus.publish(SpectrumComputed(spectrum=spectrum, input_fingerprint=fingerprint, calculation_input=calculation_input))
    QCoreApplication.processEvents()


def test_a_second_method_makes_the_first_spectrum_comparable(panel):
    widget, bus, molecule = panel
    lookup = _spectrum(molecule.uuid, "HOSE lookup", {0: 18.2, 1: 57.9})
    ab_initio = _spectrum(molecule.uuid, "ORCA PBE0", {0: 17.0, 1: 60.1})
    _publish(bus, lookup)
    anchor, others = widget.comparable_with(lookup)
    assert others == [], "one method alone has nothing to be compared with"
    _publish(bus, ab_initio)
    anchor, others = widget.comparable_with(lookup)
    assert [c.dataset.method for c in others] == ["ORCA PBE0"]
    assert anchor.origin is lookup
    # And it is the REAL comparison that opens, with the spectrum's own element symbols.
    assert widget._symbols_for(widget._project.molecules[0], others[0]) == {0: "C", 1: "C"}


def test_a_refused_or_empty_spectrum_joins_nothing(panel):
    widget, bus, molecule = panel
    _publish(bus, _spectrum(molecule.uuid, "HOSE lookup", {}))
    refused = NMRSpectrumResult(
        spectrum_type="nmr_13c", name="13C shifts", units="ppm", method="ORCA", molecule_uuid=molecule.uuid,
        values={0: 1.0}, cache_state=CacheState.FAILED, error="no index",
    )
    _publish(bus, refused)
    assert widget._compare_pool == {}


def test_a_spectrum_edited_between_runs_is_refused_not_lined_up(panel):
    widget, bus, molecule = panel
    first = _spectrum(molecule.uuid, "HOSE lookup", {0: 18.2, 1: 57.9})
    second = _spectrum(molecule.uuid, "ORCA PBE0", {0: 17.0, 1: 60.1})
    _publish(bus, first, fingerprint="before")
    _publish(bus, second, fingerprint="after")
    _anchor, others = widget.comparable_with(first)
    assert others == [], "different drawings of the molecule must not be offered"


def test_two_runs_with_one_name_are_told_apart_by_what_differs():
    """Two lookups at different settings are both called "13C shifts"; a table of two columns
    with one heading cannot say which is the reference."""
    from dataclasses import replace

    from openchem.domain.common import Provenance
    from openchem.domain.compare import distinguish_labels

    def run(spheres):
        spectrum = _spectrum("u", "HOSE lookup", {0: 1.0})
        return ComparedResult(
            replace(spectrum_as_per_atom(spectrum), provenance=Provenance(
                created_by="core", method="hose", parameters={"spheres": spheres, "decimal_places": 2}))
        )

    a, b = distinguish_labels([run(3), run(2)])
    assert a.label == "13C shifts (spheres=3)" and b.label == "13C shifts (spheres=2)"
    # Unique labels are left exactly alone, and identical twins fall back to their position.
    other = ComparedResult(spectrum_as_per_atom(_spectrum("u", "ORCA", {0: 1.0})))
    named = ComparedResult(replace(spectrum_as_per_atom(_spectrum("u", "ORCA", {0: 1.0})), name="Charges"))
    assert [r.label for r in distinguish_labels([named, run(3)])] == ["Charges", "13C shifts"]
    first, second = distinguish_labels([other, other])
    assert (first.label, second.label) == ("13C shifts (1)", "13C shifts (2)")
