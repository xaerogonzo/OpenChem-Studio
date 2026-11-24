"""The dipole ORCA prints (H1 part 2 of docs/OPEN_SHELL_AND_HYPERVALENT_COVERAGE_DESIGN.md).

**WHY ORCA'S, AND NOT THE REGISTRY'S.** The `dipole_moment` calculator multiplies partial charges by positions, and the charge model it uses (Gasteiger) is NaN for the centre of ClF3, BrF3 or ClF5 (measured; `domain/finite_guard`
refuses it). A quantum run needs no charge model: ORCA integrates the dipole from the density it has just converged, so a held hypervalent structure gets a dipole through the one path that can compute it.

Measured 2026-11-24 on real ORCA 6.1.1, ClF3 from the VSEPR start, B3LYP/def2-SVP, `opt`: 0.984 D, the vector along the molecule's C2 axis (179.87 degrees from the short equatorial Cl-F bond, 92.8 from each long one). The fixture
is that output trimmed to the lines the parser reads. The frame oracle is the geometry in the same file, which the parser never sees.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.orca_engine import OrcaQuantumEngineProvider, parse_dipole
from openchem.chem.qc_dipole import vector_matches_magnitude

FIXTURE = Path(__file__).parent / "fixtures" / "orca" / "clf3_opt_dipole_excerpt.out"


def _water() -> Chem.Mol:
    water = Chem.AddHs(Chem.MolFromSmiles("O"))
    AllChem.EmbedMolecule(water, randomSeed=1)
    return water


def _descriptors(text: str, calc_type: str = "sp") -> dict:
    found = OrcaQuantumEngineProvider().parse_output(text, _water(), "u", calc_type)[0]
    return {d.descriptor_id: d for d in found}


def _block(x: float, y: float, z: float, debye: float, au: float) -> str:
    return (
        "Total Dipole Moment    :     %.9f      %.9f       %.9f\n                        -----------------------------------------\n"
        "Magnitude (a.u.)       :      %.9f\nMagnitude (Debye)      :      %.9f\n" % (x, y, z, au, debye)
    )


def test_the_clf3_dipole_is_read_and_points_along_the_molecules_own_axis():
    text = FIXTURE.read_text()
    descriptor = _descriptors(text)["orca.dipole_moment"]
    vector = np.array(descriptor.provenance.parameters["vector"])

    assert descriptor.units == "Debye" and abs(descriptor.value - 0.984372464) < 1e-9
    assert vector_matches_magnitude(tuple(float(v) for v in vector), descriptor.value)

    # The oracle is the geometry printed in the same file: ClF3 is C2v, so the dipole lies on the Cl-F bond that is the axis (the short, equatorial one).
    rows = [line.split() for line in text.splitlines() if line.split()[:1] in (["Cl"], ["F"]) and len(line.split()) == 4]
    centre = next(np.array(r[1:], dtype=float) for r in rows if r[0] == "Cl")
    bonds = sorted((np.array(r[1:], dtype=float) - centre for r in rows if r[0] == "F"), key=np.linalg.norm)
    axis = bonds[0]
    cosine = abs(float(vector @ axis / np.linalg.norm(vector) / np.linalg.norm(axis)))
    assert cosine > np.cos(np.radians(1.0)), f"dipole {cosine:.5f} of the way along the C2 axis"
    assert abs(float(vector @ bonds[1]) / np.linalg.norm(vector) / np.linalg.norm(bonds[1])) < np.cos(np.radians(85.0))


def test_windows_line_ends_read_the_same():
    text = FIXTURE.read_text()
    assert parse_dipole(text.replace("\n", "\r\n")) == parse_dipole(text)


def test_the_last_block_is_the_final_geometrys():
    """An optimisation can print the block more than once; the earlier ones are earlier structures."""
    text = _block(0.0, 0.0, 0.787, 2.0, 0.787) + "...\n" + _block(0.0, 0.0, 0.3937, 1.0, 0.3937)
    vector, magnitude = parse_dipole(text)
    assert magnitude == 1.0 and abs(vector[2] - 1.0) < 1e-3


def test_a_job_that_printed_no_dipole_gains_no_descriptor():
    assert parse_dipole("FINAL SINGLE POINT ENERGY   -1.0\n") is None
    assert "orca.dipole_moment" not in _descriptors("FINAL SINGLE POINT ENERGY   -1.0\n")
