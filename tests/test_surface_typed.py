"""The Molecular Surface Area (3D) calculator carries five of its numbers as numbers, and a derived score reads them only at the settings that make them one thing (`docs/DERIVED_SCORES_DESIGN.md`, section 11).

Until now every line was text (`'361.31'`), which a score must not rest on: it would move with a display setting. The producer holds the numbers, so the producer hands them over: the same `Fact`, its `value` the float and its
`display_value` still the rounded text. Five are typed (the accessible area, its hydrophobic and polar parts, and the van der Waals area and volume); ASA+ and ASA- stay text, because they are the sum of the area of the atoms whose
Gasteiger charge is above or below nothing, and that sign is decided by tiny charges (7% of caffeine's accessible area sits on atoms whose charge is under 0.02 in size).

**THE LINES A PERSON SEES MUST NOT MOVE**, which is what `tests/fixtures/surface_lines.json` is: every line, label, unit, basis and table-cell text of the calculator over `tests/conformer_panel.py`'s molecules and every way
of asking, recorded from the code BEFORE the change. `observe` is the one function that produced the fixture and that reads it back.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest
from rdkit import Chem

from openchem.bootstrap import build_service_container
from openchem.chem.result_reduction import reduce_result
from openchem.domain.calculator import CalculationRefusal
from openchem.domain.score_outputs import APPROVED, approved_output
from tests.conformer_panel import panel

FIXTURE = Path(__file__).parent / "fixtures" / "surface_lines.json"

#: Every way of asking: the defaults, three probes (the label of the first line carries a probe that is not 1.4), the major microspecies with and without another probe, and four decimals.
ASKS = {
    "default": {},
    "probe 1.2": {"solvent_radius": 1.2},
    "probe 0": {"solvent_radius": 0.0},
    "probe 2": {"solvent_radius": 2.0},
    "microspecies": {"major_microspecies": True, "pH": 7.4},
    "microspecies probe 2": {"major_microspecies": True, "pH": 7.4, "solvent_radius": 2.0},
    "four decimals": {"decimal_places": 4},
}


def observe(registry, mol, parameters: dict) -> dict:
    """What the calculator says for one molecule asked one way, through the registry: the lines, the facts without their values and the cells the project table would hold (text only)."""
    try:
        result = registry.compute("surface_analysis", mol, "uuid", dict(parameters))
    except CalculationRefusal as refusal:
        return {"refused": refusal.code}
    return {
        "state": result.cache_state.value,
        "error": result.error,
        "summary": result.error_summary,
        "inapplicable": result.inapplicable,
        "method": result.provenance.method,
        "provenance_keys": sorted(result.provenance.parameters),
        "lines": list(result.matched),
        "facts": [[f.category.value, f.label, f.display_value, f.units, f.source, f.basis.value] for f in result.facts],
        "cells": [[column.column_id, column.units, cell.text] for column, cell in reduce_result(result, "surface_analysis", "Molecular Surface Area (3D)")],
    }


@pytest.fixture(scope="module")
def registry():
    return build_service_container().calculator_registry


@pytest.fixture(scope="module")
def molecules():
    return panel()


@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_the_fixture_covers_every_molecule_asked_every_way(golden, molecules):
    assert set(golden) == {f"{name} | {ask}" for name in molecules for ask in ASKS}


@pytest.mark.parametrize("ask", sorted(ASKS))
def test_no_line_label_unit_or_cell_text_moved(registry, golden, molecules, ask):
    moved = {
        f"{name} | {ask}": seen
        for name, mol in molecules.items()
        if (seen := observe(registry, mol, ASKS[ask])) != golden[f"{name} | {ask}"]
    }
    assert not moved, f"what a person sees moved for: {sorted(moved)}"


# --- five of the seven are numbers, and each is the one its line rounds ----------------------------------------------------------------------------


_PREFIX = "calculator:surface_analysis:"
_ASA, _HYDROPHOBIC, _POLAR = "ASA (solvent accessible)", "ASA_H (hydrophobic)", "ASA_P (polar)"
_VDW_AREA, _VDW_VOLUME = "van der Waals surface area", "van der Waals volume"
_FIVE = [_ASA, _HYDROPHOBIC, _POLAR, _VDW_AREA, _VDW_VOLUME]
_TEXT = ["ASA+ (positively charged atoms)", "ASA- (negatively charged atoms)"]


def _compute(registry, mol, parameters: dict):
    return registry.compute("surface_analysis", mol, "uuid", dict(parameters))


def _typed(result) -> dict:
    return {f.label: f for f in result.facts if isinstance(f.value, float)}


def _facts(result) -> dict:
    return {f.label: f for f in result.facts}


@pytest.mark.parametrize("ask", sorted(ASKS))
def test_exactly_five_numbers_are_typed_and_each_is_the_one_its_line_rounds(registry, molecules, ask):
    places = ASKS[ask].get("decimal_places", 2)
    probe = ASKS[ask].get("solvent_radius", 1.4)
    asa = _ASA if probe == 1.4 else f"ASA (solvent accessible, {probe:g} Å probe)"
    computed = 0
    for name, mol in molecules.items():
        result = _compute(registry, mol, ASKS[ask])
        if result.cache_state.value == "failed":
            assert not _typed(result), f"{name}: a refusal has no number to type"
            continue
        computed += 1
        typed = _typed(result)
        assert sorted(typed) == sorted([asa, _HYDROPHOBIC, _POLAR, _VDW_AREA, _VDW_VOLUME]), name
        for label, fact in typed.items():
            assert math.isfinite(fact.value) and fact.value >= 0 and fact.display_value == f"{fact.value:.{places}f}", (name, label)
            assert fact.units == ("Å³" if label == _VDW_VOLUME else "Å²"), (name, label)
        assert all(isinstance(_facts(result)[label].value, str) for label in _TEXT), f"{name}: ASA+ and ASA- stay text"
        assert result.matched[0] == f"{asa}: {typed[asa].value:.{places}f} Å²", name
    assert computed >= 15


def test_only_the_label_of_the_accessible_area_carries_the_probe(registry, molecules):
    """The measured reason a result made with another probe is declined by what it RECORDS: the labels of the other four numbers do not say which probe made them."""
    labels = {probe: sorted(_facts(_compute(registry, molecules["aspirin"], {"solvent_radius": probe}))) for probe in (1.4, 1.2, 0.0, 2.0)}
    assert labels[1.4] != labels[1.2] != labels[0.0] != labels[2.0]
    for probe in (1.2, 0.0, 2.0):
        assert set(labels[1.4]) - set(labels[probe]) == {_ASA}, probe
    assert all(label in labels[probe] for probe in labels for label in (_HYDROPHOBIC, _POLAR, _VDW_AREA, _VDW_VOLUME, *_TEXT))


def test_the_probe_moves_the_accessible_numbers_and_leaves_the_van_der_waals_ones_alone(registry, molecules):
    """Why the van der Waals area and volume are read from a result made with any probe, and the three accessible areas only from the default one."""
    by_probe = {probe: _compute(registry, molecules["aspirin"], {"solvent_radius": probe}) for probe in (1.2, 1.4, 2.0)}
    assert by_probe[1.4].provenance.parameters["solvent_radius"] == 1.4 and by_probe[1.2].provenance.parameters["solvent_radius"] == 1.2
    for label in (_VDW_AREA, _VDW_VOLUME):
        values = {probe: _typed(result)[label].value for probe, result in by_probe.items()}
        assert values[1.2] == values[1.4] == values[2.0], label
    for label in (_HYDROPHOBIC, _POLAR):
        values = [_typed(by_probe[probe])[label].value for probe in (1.2, 1.4, 2.0)]
        assert values[0] < values[1] < values[2], label
    asa = [next(f.value for f in _typed(by_probe[probe]).values() if f.label.startswith("ASA (")) for probe in (1.2, 1.4, 2.0)]
    assert asa[0] < asa[1] < asa[2]
    assert asa[1] / asa[0] == pytest.approx(361.3 / 334.4, rel=0.01), "aspirin: 7% lower at a 1.2 Å probe"


def test_the_record_says_which_probe_and_whether_it_was_the_major_microspecies(registry, molecules):
    plain = _compute(registry, molecules["glycine"], {}).provenance.parameters
    assert plain["solvent_radius"] == 1.4 and "major_microspecies" not in plain
    species = _compute(registry, molecules["glycine"], {"major_microspecies": True, "pH": 7.4}).provenance.parameters
    assert species["major_microspecies"] is True and species["pH"] == 7.4 and species["solvent_radius"] == 1.4


def test_the_hydrophobic_and_the_polar_area_are_the_whole_accessible_area(registry, molecules):
    for name, mol in molecules.items():
        result = _compute(registry, mol, {})
        if result.cache_state.value == "failed":
            continue
        typed = _typed(result)
        assert typed[_HYDROPHOBIC].value + typed[_POLAR].value == pytest.approx(typed[_ASA].value, rel=1e-9), name


def test_the_project_table_cell_holds_the_exact_number_and_shows_the_rounded_text(registry, molecules):
    result = _compute(registry, molecules["aspirin"], {})
    cells = {c.column_id: (c, k) for c, k in reduce_result(result, "surface_analysis", "Molecular Surface Area (3D)")}
    for label in _FIVE:
        column, cell = cells[_PREFIX + label]
        assert column.numeric and cell.text == f"{cell.value:.2f}" and cell.value == _typed(result)[label].value, label
        assert column.units == ("Å³" if label == _VDW_VOLUME else "Å²"), label
    assert any(cell.value != float(cell.text) for _column, cell in cells.values() if isinstance(cell.value, float)), "the exact number, not the rounded one"


def test_the_five_entries_are_approved_in_their_own_units_and_asa_plus_and_minus_are_not():
    entries = {label: approved_output(_PREFIX + label) for label in _FIVE}
    assert all(entry is not None and entry.input == "geometry" and entry.whole_structure for entry in entries.values())
    assert {label: entry.unit for label, entry in entries.items()} == {_ASA: "Å^2", _HYDROPHOBIC: "Å^2", _POLAR: "Å^2", _VDW_AREA: "Å^2", _VDW_VOLUME: "Å^3"}
    assert {label: entry.run_with for label, entry in entries.items()} == {
        _ASA: "default_probe_as_drawn", _HYDROPHOBIC: "default_probe_as_drawn", _POLAR: "default_probe_as_drawn", _VDW_AREA: "as_drawn", _VDW_VOLUME: "as_drawn",
    }
    assert sorted(e.output_id for e in APPROVED if e.output_id.startswith(_PREFIX)) == sorted(_PREFIX + label for label in _FIVE)


# --- what the numbers are, reproduced by routes that share no code with the producer -------------------------------------------------------------

#: Bondi's van der Waals radii (1964) for the elements of the molecules below, written out here and not read from the producer's table.
_BONDI = {"H": 1.20, "C": 1.70, "N": 1.55, "O": 1.52, "F": 1.47, "Cl": 1.75, "Ne": 1.54}


def _sphere(points: int) -> np.ndarray:
    """`points` points spread evenly over a unit sphere (the golden-angle spiral)."""
    index = np.arange(points) + 0.5
    z = 1 - 2 * index / points
    angle = np.pi * (1 + 5**0.5) * index
    radius = np.sqrt(1 - z * z)
    return np.stack([radius * np.cos(angle), radius * np.sin(angle), z], axis=1)


def _areas(mol, probe: float, points: int = 6000) -> np.ndarray:
    """The accessible area of every atom by Shrake and Rupley's point counting, in numpy: the share of the points on a sphere of the atom's radius plus the probe that no other atom's sphere contains."""
    xyz = mol.GetConformer().GetPositions()
    radii = np.array([_BONDI[atom.GetSymbol()] for atom in mol.GetAtoms()]) + probe
    unit = _sphere(points)
    out = np.zeros(len(xyz))
    for i in range(len(xyz)):
        surface = xyz[i] + radii[i] * unit
        free = np.ones(points, dtype=bool)
        for j in range(len(xyz)):
            if j != i:
                free &= np.linalg.norm(surface - xyz[j], axis=1) >= radii[j]
        out[i] = 4 * np.pi * radii[i] ** 2 * free.mean()
    return out


def _is_polar(mol, atom) -> bool:
    return atom.GetSymbol() in ("N", "O", "F") or (atom.GetSymbol() == "H" and any(n.GetSymbol() in ("N", "O", "F") for n in atom.GetNeighbors()))


def _volume(mol, spacing: float = 0.1) -> float:
    """The volume of the union of the van der Waals spheres by counting the points of a grid that lie in one of them."""
    xyz = mol.GetConformer().GetPositions()
    radii = np.array([_BONDI[atom.GetSymbol()] for atom in mol.GetAtoms()])
    low, high = (xyz - radii[:, None]).min(axis=0) - spacing, (xyz + radii[:, None]).max(axis=0) + spacing
    axes = [np.arange(low[k], high[k], spacing) + spacing / 2 for k in range(3)]
    grid = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
    inside = np.zeros(len(grid), dtype=bool)
    for centre, radius in zip(xyz, radii):
        near = np.abs(grid - centre).max(axis=1) <= radius
        inside[near] |= np.linalg.norm(grid[near] - centre, axis=1) <= radius
    return float(inside.sum() * spacing**3)


@pytest.mark.parametrize("name", ["water", "ethanol", "acetone", "benzene", "phenol", "aspirin", "caffeine", "chloroform", "glycine", "acetate"])
def test_the_accessible_area_and_its_polar_part_are_what_point_counting_gives(registry, molecules, name):
    mol = molecules[name]
    typed = _typed(_compute(registry, mol, {}))
    areas = _areas(mol, 1.4)
    polar = sum(area for area, atom in zip(areas, mol.GetAtoms()) if _is_polar(mol, atom))
    assert typed[_ASA].value == pytest.approx(areas.sum(), rel=0.02)
    assert typed[_POLAR].value == pytest.approx(polar, rel=0.03, abs=1.0)
    assert typed[_HYDROPHOBIC].value == pytest.approx(areas.sum() - polar, rel=0.03, abs=1.0)


@pytest.mark.parametrize("name", ["water", "ethanol", "benzene", "aspirin", "caffeine", "chloroform"])
def test_the_van_der_waals_area_and_volume_are_those_of_the_fused_spheres(registry, molecules, name):
    mol = molecules[name]
    typed = _typed(_compute(registry, mol, {}))
    assert typed[_VDW_AREA].value == pytest.approx(_areas(mol, 0.0).sum(), rel=0.02)
    assert typed[_VDW_VOLUME].value == pytest.approx(_volume(mol), rel=0.015)


def _two_atoms(symbol: str, bond: float) -> Chem.Mol:
    """Two atoms `bond` Å apart on the x axis, with no hydrogens: a diatomic whose spheres can be worked out by hand."""
    mol = Chem.RWMol()
    for _ in range(2):
        mol.AddAtom(Chem.Atom(symbol))
    mol.AddBond(0, 1, Chem.BondType.TRIPLE if symbol == "N" else Chem.BondType.SINGLE)
    conformer = Chem.Conformer(2)
    conformer.SetAtomPosition(0, (0.0, 0.0, 0.0))
    conformer.SetAtomPosition(1, (bond, 0.0, 0.0))
    mol.AddConformer(conformer)
    Chem.SanitizeMol(mol)
    return mol.GetMol()


def test_a_lone_atom_is_a_sphere_whose_volume_and_areas_are_the_formulas_of_a_sphere(registry):
    mol = Chem.AddHs(Chem.MolFromSmiles("[Ne]"), addCoords=False)
    conformer = Chem.Conformer(1)
    conformer.SetAtomPosition(0, (0.0, 0.0, 0.0))
    mol.AddConformer(conformer)
    typed = _typed(_compute(registry, mol, {}))
    radius = _BONDI["Ne"]
    assert typed[_VDW_VOLUME].value == pytest.approx(4 / 3 * math.pi * radius**3, rel=1e-3)
    assert typed[_VDW_AREA].value == pytest.approx(4 * math.pi * radius**2, rel=1e-3)
    assert typed[_ASA].value == pytest.approx(4 * math.pi * (radius + 1.4) ** 2, rel=1e-3)


def test_two_fused_spheres_have_the_volume_and_areas_the_cap_formulas_give(registry):
    """Dinitrogen, two spheres of Bondi's 1.55 Å whose centres are 1.098 Å apart: the lens they share and the two caps it removes are closed formulas of the radius and the distance. RDKit's own table gives 1.60
    for nitrogen, which would move these by 3% (the accessible area) to 10% (the volume)."""
    bond, r = 1.098, _BONDI["N"]
    typed = _typed(_compute(registry, _two_atoms("N", bond), {}))

    def fused_area(radius: float) -> float:
        return 8 * math.pi * radius**2 - 4 * math.pi * radius * (radius - bond / 2)

    lens = math.pi * (2 * r - bond) ** 2 * (bond + 4 * r) / 12
    assert typed[_VDW_VOLUME].value == pytest.approx(2 * 4 / 3 * math.pi * r**3 - lens, rel=0.01)
    assert typed[_VDW_AREA].value == pytest.approx(fused_area(r), rel=0.01)
    assert typed[_ASA].value == pytest.approx(fused_area(r + 1.4), rel=0.01)
    assert typed[_POLAR].value == pytest.approx(typed[_ASA].value, rel=1e-9) and typed[_HYDROPHOBIC].value == pytest.approx(0.0, abs=1e-9), "nitrogen is polar, both atoms"
