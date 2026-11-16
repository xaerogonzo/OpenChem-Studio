"""Geometry analysis on a HELD hypervalent structure (H1 of docs/OPEN_SHELL_AND_HYPERVALENT_COVERAGE_DESIGN.md), held to an independent implementation.

The radii and the shadow are arithmetic on the atoms and the van der Waals table, so they need no valence model and are allowed on a structure RDKit refuses
(ClF3, BrF3, ClF5). The oracle below shares nothing with `chem.projection_geometry`: a raster of the union of discs over 300 sampled viewing directions
(Fibonacci hemisphere), a Nelder-Mead minimum enclosing circle, and the extent along the sampled direction. Measured before it was written (prototype, same
code): areas within 0.2% of the application's exact-union search, circle radii within 0.2%, extents within 0.4%. The force fields cannot represent these
structures, so they are not computed, and the options that need one are refused.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from PySide6.QtCore import QThreadPool
from scipy.optimize import minimize

from openchem.bootstrap import build_service_container
from openchem.chem.calculation_input import HYPERVALENT_VERIFIED_CALCULATORS
from openchem.chem.conformer_providers import GenerationOptions, RDKitConformerProvider, search_conformers
from openchem.chem.geometry_analysis import compute_geometry_analysis
from openchem.domain.calculator import CalculationRefusal, CalculationRequest
from openchem.domain.molecule import MoleculeModel
from openchem.domain.refusal_kinds import HYPERVALENT_UNSUPPORTED
from openchem.events.events import ReportComputed
from tests.test_chem_engine import _hypervalent_molblock

#: centre, ligand, count. All three are refused by RDKit, so they are held.
HELD = {"ClF3": ("Cl", "F", 3), "BrF3": ("Br", "F", 3), "ClF5": ("Cl", "F", 5)}
#: Bondi van der Waals radii, Angstrom, typed here and used by nothing else.
BONDI = {"F": 1.47, "Cl": 1.75, "Br": 1.85}


@pytest.fixture(scope="module")
def rig():
    return build_service_container()


def _held(rig, name):
    engine = rig.chemistry_engine
    molecule = MoleculeModel(display_name=name)
    engine.set_structure_from_molblock(molecule, _hypervalent_molblock(*HELD[name]), allow_hypervalent=True)
    mol = engine.mol_from_model(molecule, allow_hypervalent=True)
    return molecule, search_conformers(RDKitConformerProvider(random_seed=1), mol, True, GenerationOptions()).pool[0][0]


def _values(mol3d) -> dict[str, float]:
    return {f.label: float(f.value) for f in compute_geometry_analysis(mol3d, "u", {}).facts if f.value is not None}


def _basis(d):
    a = np.array([1.0, 0, 0]) if abs(d[0]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(d, a)
    u /= np.linalg.norm(u)
    return u, np.cross(d, u)


def _area(points, radii, d, h=0.025):
    u, v = _basis(d)
    xy = np.stack([points @ u, points @ v], axis=1)
    low, high = (xy - radii[:, None]).min(0) - 0.1, (xy + radii[:, None]).max(0) + 0.1
    gx, gy = np.meshgrid(np.arange(low[0], high[0], h) + h / 2, np.arange(low[1], high[1], h) + h / 2)
    covered = np.zeros(gx.shape, dtype=bool)
    for (cx, cy), r in zip(xy, radii):
        covered |= (gx - cx) ** 2 + (gy - cy) ** 2 <= r * r
    return covered.sum() * h * h


def _enclosing_circle(points, radii, d):
    u, v = _basis(d)
    xy = np.stack([points @ u, points @ v], axis=1)

    def furthest(c):
        return max(np.linalg.norm(xy - c, axis=1) + radii)

    return min(minimize(furthest, x0, method="Nelder-Mead", options={"xatol": 1e-6, "fatol": 1e-8}).fun for x0 in (xy.mean(0), xy[0], xy[1]))


def _extent(points, radii, d):
    p = points @ d
    return (p + radii).max() - (p - radii).min()


@pytest.mark.parametrize("name", HELD)
def test_the_radii_are_the_centroid_distances(rig, name):
    _, mol3d = _held(rig, name)
    points = mol3d.GetConformer().GetPositions()
    distances = np.linalg.norm(points - points.mean(axis=0), axis=1)
    values = _values(mol3d)
    assert values["Max radius (from centroid)"] == pytest.approx(distances.max(), abs=0.005)
    assert values["Min radius (from centroid)"] == pytest.approx(distances.min(), abs=0.005)
    assert values["Mean radius (from centroid)"] == pytest.approx(distances.mean(), abs=0.005)


@pytest.mark.parametrize("name", HELD)
def test_the_shadow_agrees_with_an_independent_raster(rig, name):
    _, mol3d = _held(rig, name)
    points = mol3d.GetConformer().GetPositions()
    radii = np.array([BONDI[a.GetSymbol()] for a in mol3d.GetAtoms()])
    n = 300
    i = np.arange(n) + 0.5
    phi, theta = np.arccos(1 - i / n), math.pi * (1 + 5**0.5) * i
    directions = np.stack([np.cos(theta) * np.sin(phi), np.sin(theta) * np.sin(phi), np.cos(phi)], axis=1)
    areas = np.array([_area(points, radii, d) for d in directions])
    low, high = directions[areas.argmin()], directions[areas.argmax()]
    values = _values(mol3d)
    assert values["Min projection area"] == pytest.approx(areas.min(), rel=0.015)
    assert values["Max projection area"] == pytest.approx(areas.max(), rel=0.015)
    assert values["Min projection radius"] == pytest.approx(_enclosing_circle(points, radii, low), rel=0.01)
    assert values["Max projection radius"] == pytest.approx(_enclosing_circle(points, radii, high), rel=0.01)
    assert values["Size perpendicular to the min projection"] == pytest.approx(_extent(points, radii, low), rel=0.015)
    assert values["Size perpendicular to the max projection"] == pytest.approx(_extent(points, radii, high), rel=0.015)


@pytest.mark.parametrize("name", HELD)
def test_no_force_field_energy_is_published_for_a_held_structure(rig, name):
    """Measured before WP3 and still true of the force fields: Dreiding typed ClF3 as a one-bond halogen with three bonds (216 kcal/mol)."""
    _, mol3d = _held(rig, name)
    facts = {f.label: f for f in compute_geometry_analysis(mol3d, "u", {}).facts}
    assert not any("energy" in label.lower() and fact.value is not None for label, fact in facts.items())
    assert "no force field can represent this hypervalent structure" in facts["Force field energy"].display_value


@pytest.mark.parametrize("options", [{"conformer_policy": "always"}, {"conformer_policy": "if_2d"}, {"optimise_mmff": True}, {"optimise_projection": True}])
def test_the_options_that_need_a_force_field_are_refused_with_the_limit(rig, options):
    _, mol3d = _held(rig, "ClF3")
    with pytest.raises(CalculationRefusal) as caught:
        compute_geometry_analysis(mol3d, "u", options)
    assert caught.value.code == HYPERVALENT_UNSUPPORTED


def test_an_ordinary_molecule_still_gets_its_force_field_energies(rig):
    """The control: ethanol is not held and keeps MMFF94, UFF and Dreiding. (SF6, which RDKit accepts, has none of the three: UFF has no S(VI) type and Dreiding refuses it, WP3.)"""
    from rdkit import Chem

    ethanol = search_conformers(RDKitConformerProvider(random_seed=1), Chem.MolFromSmiles("CCO"), True, GenerationOptions()).pool[0][0]
    assert {"MMFF94 energy", "UFF energy", "Dreiding energy"} <= {f.label for f in compute_geometry_analysis(ethanol, "u", {}).facts}


def test_geometry_analysis_is_on_the_verified_list_and_runs_through_the_service(rig, qapp):
    from rdkit import Chem

    from openchem.domain.conformer import ConformerModel

    assert "geometry_analysis" in HYPERVALENT_VERIFIED_CALCULATORS
    molecule, mol3d = _held(rig, "ClF3")
    molecule.conformers.append(ConformerModel(molblock=Chem.MolToMolBlock(mol3d), method="vsepr_template"))
    events = []
    rig.event_bus.subscribe(ReportComputed, events.append)
    rig.descriptor_service.run_calculator(molecule, CalculationRequest(calculator_id="geometry_analysis", molecule_uuid=molecule.uuid, parameters={}))
    QThreadPool.globalInstance().waitForDone(8000)
    for _ in range(50):
        qapp.processEvents()
    reports = [e.report for e in events if e.report.report_id == "geometry_analysis"]
    assert reports and reports[-1].error is None
    assert any(f.label == "Max projection area" for f in reports[-1].facts)
