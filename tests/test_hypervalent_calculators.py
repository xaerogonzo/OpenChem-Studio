"""The calculators allowed on a held hypervalent structure, each held to an INDEPENDENT oracle.

`HYPERVALENT_VERIFIED_CALCULATORS` is not "calculators that returned a number". Each one here is checked against
values this file works out itself (IUPAC atomic weights and isotope abundances typed in, oxidation numbers by hand, a
second accessible-surface implementation), on four molecules with different centres and shapes. The calculators
measured to be WRONG on these molecules (geometry analysis:
a meaningless force-field energy; the additive polarizability: 21% low for SF6) stay refused, and a test says so.
"""

from __future__ import annotations

import math
import re

import numpy as np
import pytest
from PySide6.QtCore import QThreadPool

from openchem.bootstrap import build_service_container
from openchem.chem.calculation_input import HYPERVALENT_VERIFIED_CALCULATORS
from openchem.chem.conformer_providers import GenerationOptions, RDKitConformerProvider, search_conformers
from openchem.domain.calculator import CalculationRequest, RegistryExecution
from openchem.domain.molecule import MoleculeModel
from openchem.events.events import PerAtomDataComputed, ReportComputed
from tests.test_chem_engine import _hypervalent_molblock

#: centre, ligand, count -> (Hill formula, centre oxidation number).
MOLECULES = {
    "ClF3": (("Cl", "F", 3), "ClF3", 3),
    "BrF3": (("Br", "F", 3), "BrF3", 3),
    "SF6": (("S", "F", 6), "F6S", 6),
    "PF5": (("P", "F", 5), "F5P", 5),
}
#: IUPAC conventional/abridged standard atomic weights, typed here and used by nothing else.
WEIGHT = {"F": 18.998403, "Cl": 35.45, "Br": 79.904, "S": 32.06, "P": 30.973762}
#: Bondi van der Waals radii, Angstrom.
BONDI = {"F": 1.47, "Cl": 1.75, "Br": 1.85, "S": 1.80, "P": 1.80}


@pytest.fixture(scope="module")
def rig():
    container = build_service_container()
    return container


def _held(rig, name):
    spec = MOLECULES[name][0]
    engine = rig.chemistry_engine
    molecule = MoleculeModel(display_name=name)
    engine.set_structure_from_molblock(molecule, _hypervalent_molblock(*spec), allow_hypervalent=True)
    mol = engine.mol_from_model(molecule, allow_hypervalent=True)
    pool = search_conformers(RDKitConformerProvider(random_seed=1), mol, True, GenerationOptions()).pool
    return molecule, pool[0][0]


def _compute(rig, calculator_id, mol):
    registry = rig.descriptor_service._calculator_registry
    definition = registry.get(calculator_id)
    params = {p.name: p.default for p in definition.parameters}
    return registry.compute(calculator_id, mol, "u", params)


def _facts(result) -> dict[str, list[str]]:
    report = getattr(result, "report", result)
    out: dict[str, list[str]] = {}
    for fact in report.facts:
        out.setdefault(fact.label, []).append(str(fact.display_value))
    return out


def test_every_verified_calculator_is_a_registered_one(rig):
    """Guards a typo or a renamed calculator: an id that matches nothing would silently allow nothing."""
    registry = rig.descriptor_service._calculator_registry
    for calculator_id in HYPERVALENT_VERIFIED_CALCULATORS:
        definition = registry.get(calculator_id)
        assert definition is not None, calculator_id
        assert isinstance(definition.execution, RegistryExecution), calculator_id


@pytest.mark.parametrize("name", MOLECULES)
def test_elemental_analysis_matches_the_atomic_weights(rig, name):
    _, formula, _ = MOLECULES[name]
    _, mol3d = _held(rig, name)
    facts = _facts(_compute(rig, "elemental_analysis", mol3d))
    assert facts["Elemental Analysis"][0] == f"Formula: {formula}"
    symbols = [a.GetSymbol() for a in mol3d.GetAtoms()]
    total = sum(WEIGHT[s] for s in symbols)
    assert float(facts["Mass"][0]) == pytest.approx(total, rel=5e-4)
    assert int(facts["Atom count"][0]) == len(symbols)
    for symbol in set(symbols):
        percent = 100 * sum(WEIGHT[s] for s in symbols if s == symbol) / total
        assert float(facts[symbol][0]) == pytest.approx(percent, abs=0.05), symbol


def _peak_percentages(facts) -> dict[str, float]:
    peaks = {}
    for line in facts["Mass Spectrum"]:
        found = re.match(r"\s*(M(?:\+\d+)?): m/z [\d.]+, ([\d.]+)%", line)
        if found:
            peaks[found.group(1)] = float(found.group(2))
    return peaks


def test_the_chlorine_isotope_pattern_is_three_to_one(rig):
    """Cl-35 75.76 %, Cl-37 24.24 %: M+2 is 24.24/75.76 = 32.00 % of M, and nothing else is present."""
    _, mol3d = _held(rig, "ClF3")
    peaks = _peak_percentages(_facts(_compute(rig, "mass_spectrum", mol3d)))
    assert set(peaks) == {"M", "M+2"}
    assert peaks["M"] == 100.0
    assert peaks["M+2"] == pytest.approx(100 * 24.24 / 75.76, abs=0.3)


def test_the_bromine_isotope_pattern_is_one_to_one(rig):
    """Br-79 50.69 %, Br-81 49.31 %: M+2 is 97.28 % of M."""
    _, mol3d = _held(rig, "BrF3")
    peaks = _peak_percentages(_facts(_compute(rig, "mass_spectrum", mol3d)))
    assert set(peaks) == {"M", "M+2"}
    assert peaks["M+2"] == pytest.approx(100 * 49.31 / 50.69, abs=0.3)


def test_the_sulfur_isotope_pattern(rig):
    """S-32 94.99, S-33 0.75, S-34 4.25: M+1 is 0.79 % and M+2 4.47 % of M (SF6 has no other polyisotopic element)."""
    _, mol3d = _held(rig, "SF6")
    peaks = _peak_percentages(_facts(_compute(rig, "mass_spectrum", mol3d)))
    assert peaks["M+1"] == pytest.approx(100 * 0.75 / 94.99, abs=0.15)
    assert peaks["M+2"] == pytest.approx(100 * 4.25 / 94.99, abs=0.2)


@pytest.mark.parametrize("name", [*MOLECULES, "XeF4"])
def test_oxidation_states_are_the_ones_worked_out_by_hand(rig, name):
    if name == "XeF4":
        spec, centre_state = ("Xe", "F", 4), 4
    else:
        spec, centre_state = MOLECULES[name][0], MOLECULES[name][2]
    engine = rig.chemistry_engine
    molecule = MoleculeModel(display_name=name)
    engine.set_structure_from_molblock(molecule, _hypervalent_molblock(*spec), allow_hypervalent=True)
    mol = engine.mol_from_model(molecule, allow_hypervalent=True)
    values = _compute(rig, "oxidation_states", mol).values
    # fluorine is -1 (the most electronegative element); the centre balances a neutral molecule
    assert values[0] == centre_state
    assert all(values[i] == -1 for i in range(1, spec[2] + 1))
    assert sum(values.values()) == 0


@pytest.mark.parametrize("name", MOLECULES)
def test_substance_analysis_says_molecule_with_the_right_formula(rig, name):
    _, formula, _ = MOLECULES[name]
    _, mol3d = _held(rig, name)
    facts = _facts(_compute(rig, "substance_analysis", mol3d))
    assert facts["Substance classification"] == ["Molecule"]
    assert facts["Formula"] == [formula]
    assert facts["Components"] == ["1"] and facts["Total charge"] == ["0"]


def _reference_sasa(points: np.ndarray, symbols: list[str], probe: float = 1.4, n: int = 6000) -> list[float]:
    """Shrake-Rupley on a Fibonacci sphere, written here and sharing nothing with the application's `chem.sasa`."""
    indices = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * indices / n)
    theta = math.pi * (1 + 5**0.5) * indices
    sphere = np.stack([np.cos(theta) * np.sin(phi), np.sin(theta) * np.sin(phi), np.cos(phi)], axis=1)
    radii = np.array([BONDI[s] + probe for s in symbols])
    areas = []
    for i, centre in enumerate(points):
        surface = centre + radii[i] * sphere
        buried = np.zeros(n, dtype=bool)
        for j, other in enumerate(points):
            if j != i:
                buried |= np.linalg.norm(surface - other, axis=1) < radii[j]
        areas.append(4 * math.pi * radii[i] ** 2 * (~buried).sum() / n)
    return areas


@pytest.mark.parametrize("name", MOLECULES)
def test_per_atom_accessible_surface_agrees_with_an_independent_implementation(rig, name):
    _, mol3d = _held(rig, name)
    symbols = [a.GetSymbol() for a in mol3d.GetAtoms()]
    conformer = mol3d.GetConformer()
    points = np.array([list(conformer.GetAtomPosition(i)) for i in range(len(symbols))])
    expected = _reference_sasa(points, symbols)
    values = _compute(rig, "atom_sasa", mol3d).values
    for index, area in enumerate(expected):
        assert values[index] == pytest.approx(area, abs=2.5), (name, index, symbols[index])
    assert sum(values.values()) == pytest.approx(sum(expected), rel=0.02)


# --- the ones that are NOT allowed, and the measurement that keeps them out -------------------------------------


def _run_through_the_service(rig, qapp, molecule, calculator_id):
    events = []
    rig.event_bus.subscribe(ReportComputed, events.append)
    rig.event_bus.subscribe(PerAtomDataComputed, events.append)
    rig.descriptor_service.run_calculator(
        molecule,
        CalculationRequest(calculator_id=calculator_id, molecule_uuid=molecule.uuid, parameters={}),
    )
    QThreadPool.globalInstance().waitForDone(8000)
    for _ in range(50):
        qapp.processEvents()
    return events


def test_a_verified_calculator_runs_through_the_service_and_a_measured_wrong_one_is_refused(rig, qapp):
    """On ClF3, which RDKit CANNOT sanitise (so it is HELD): SF6, PF5, XeF4 and SF4 are accepted by RDKit and take the
    ordinary path, boundary or not."""
    molecule, _ = _held(rig, "ClF3")
    assert molecule.canonical_smiles == "FCl(F)F"
    ran = _run_through_the_service(rig, qapp, molecule, "substance_analysis")
    assert any(isinstance(e, ReportComputed) and e.report.report_id == "substance_analysis" for e in ran)

    for calculator_id in ("geometry_analysis", "surface_analysis"):
        refused = _run_through_the_service(rig, qapp, molecule, calculator_id)
        failed = [e for e in refused if isinstance(e, PerAtomDataComputed) and e.dataset.property_id == calculator_id]
        assert failed and "hypervalent" in (failed[-1].dataset.error or ""), calculator_id
        assert not any(isinstance(e, ReportComputed) and e.report.report_id == calculator_id for e in refused)


@pytest.mark.parametrize(
    "calculator_id",
    ["geometry_analysis", "surface_analysis", "polarizability", "regulatory_screen", "logd", "solubility", "dipole_moment"],
)
def test_the_calculators_measured_wrong_or_unsafe_are_not_on_the_list(calculator_id):
    assert calculator_id not in HYPERVALENT_VERIFIED_CALCULATORS
