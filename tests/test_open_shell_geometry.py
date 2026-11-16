"""The measured geometry table for small open-shell molecules (OS3 of docs/OPEN_SHELL_AND_HYPERVALENT_COVERAGE_DESIGN.md).

Measured before: ETKDG gave triplet O2 `[O][O]` 1.316 A and `O=O` 1.151 A, and NO 1.424 A, against the spectroscopic 1.20752 and 1.15077. The table is checked three ways:
the built distances and angles are read back from the coordinates (not from the table), they are compared with the B3LYP/def2-SVP optima real ORCA 6.1.1 gave on 2026-11-15
(`benchmarks/open_shell/orca_spin_states.py`: a plausibility check of the start, tolerance 0.02 A), and the species the table must NOT take stay on the ordinary path.
"""

from __future__ import annotations

import numpy as np
import pytest
from rdkit import Chem, RDLogger

from openchem.chem.conformer_providers import GenerationOptions, RDKitConformerProvider, search_conformers
from openchem.chem.engine import ChemistryEngine
from openchem.chem.open_shell_geometry import ENTRIES, SPIN_PROP, entry_for
from openchem.domain.conformer import OPEN_SHELL_TABLE
from openchem.domain.molecule import MoleculeModel

RDLogger.DisableLog("rdApp.*")
ENGINE = ChemistryEngine()


def build(smiles: str, spin: int | None = None):
    mol = Chem.MolFromSmiles(smiles)
    if spin is not None:
        mol.SetProp(SPIN_PROP, str(spin))
    outcome = search_conformers(RDKitConformerProvider(random_seed=1), mol, True, GenerationOptions())
    return outcome, outcome.pool[0][0]


def distance(mol, a, b) -> float:
    p = mol.GetConformer().GetPositions()
    return float(np.linalg.norm(p[a] - p[b]))


def angle(mol, a, centre, b) -> float:
    p = mol.GetConformer().GetPositions()
    u, v = p[a] - p[centre], p[b] - p[centre]
    return float(np.degrees(np.arccos(u @ v / (np.linalg.norm(u) * np.linalg.norm(v)))))


@pytest.mark.parametrize(
    "smiles, expected",
    [("[O][O]", 1.20752), ("O=O", 1.20752), ("[N]=O", 1.15077), ("[OH]", 0.96966), ("O=S", 1.481087), ("S=S", 1.8892), ("[Se]=[Se]", 2.1660)],
)
def test_a_diatomic_is_built_at_its_measured_distance(smiles, expected):
    outcome, mol = build(smiles)
    assert outcome.geometry_method == OPEN_SHELL_TABLE and outcome.pool[0][1] is None
    assert distance(mol, 0, 1) == pytest.approx(expected, abs=1e-6)


def test_methyl_is_planar_with_the_listed_lengths_and_angles():
    outcome, mol = build("[CH3]")
    assert outcome.geometry_method == OPEN_SHELL_TABLE and mol.GetNumAtoms() == 4
    assert [distance(mol, 0, i) for i in (1, 2, 3)] == pytest.approx([1.079] * 3, abs=1e-6)
    assert [angle(mol, 1, 0, 2), angle(mol, 1, 0, 3), angle(mol, 2, 0, 3)] == pytest.approx([120.0] * 3, abs=1e-4)
    p = mol.GetConformer().GetPositions()
    assert abs(np.linalg.det(np.stack([p[1] - p[0], p[2] - p[0], p[3] - p[0]]))) < 1e-9  # planar: the three bond vectors are dependent


def test_amino_radical_is_bent():
    _, mol = build("[NH2]")
    assert distance(mol, 0, 1) == pytest.approx(1.024, abs=1e-6) and angle(mol, 1, 0, 2) == pytest.approx(103.4, abs=1e-4)


def test_methylene_takes_the_geometry_of_the_multiplicity_the_drawing_states():
    """RDKit cannot tell the two apart, so the engine carries the drawing's multiplicity on the Mol (OS1)."""
    _, triplet = build("[CH2]", spin=3)
    _, singlet = build("[CH2]", spin=1)
    _, unstated = build("[CH2]")
    assert (distance(triplet, 0, 1), angle(triplet, 1, 0, 2)) == pytest.approx((1.0753, 133.931), abs=1e-3)
    assert (distance(singlet, 0, 1), angle(singlet, 1, 0, 2)) == pytest.approx((1.107, 102.4), abs=1e-3)
    assert angle(unstated, 1, 0, 2) == pytest.approx(133.931, abs=1e-3)  # the high-spin default


def test_a_drawn_singlet_carbene_reaches_the_table_through_the_model():
    block = "\n  t\n\n  1  0  0  0  0  0  0  0  0  0999 V2000\n    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\nM  RAD  1   1   {r}\nM  END\n"
    angles = {}
    for code, label in ((1, "singlet"), (3, "triplet")):
        model = MoleculeModel(display_name=label)
        ENGINE.set_structure_from_molblock(model, block.format(r=code))
        mol = ENGINE.mol_from_model(model, allow_hypervalent=True)
        outcome = search_conformers(RDKitConformerProvider(random_seed=1), mol, True, GenerationOptions())
        angles[label] = angle(outcome.pool[0][0], 1, 0, 2)
    assert angles["singlet"] == pytest.approx(102.4, abs=1e-3) and angles["triplet"] == pytest.approx(133.931, abs=1e-3)


@pytest.mark.parametrize(
    "smiles, measured",
    [("[O][O]", 1.2002), ("[N]=O", 1.1487), ("[CH3]", 1.0911), ("[CH2]", 1.0795)],
)
def test_the_start_is_near_the_b3lyp_optimum_real_orca_gave(smiles, measured):
    """Real ORCA 6.1.1, B3LYP/def2-SVP, 2026-11-15 (the first bond of the optimised geometry). OH (0.9811) is 0.012 A from the table's 0.96966: inside the same tolerance."""
    _, mol = build(smiles, spin=3 if smiles == "[CH2]" else None)
    assert distance(mol, 0, 1) == pytest.approx(measured, abs=0.02)
    _, hydroxyl = build("[OH]")
    assert distance(hydroxyl, 0, 1) == pytest.approx(0.9811, abs=0.02)


@pytest.mark.parametrize("smiles", ["[O][O-]", "C[CH2]", "[CH2]c1ccccc1", "O", "CC", "[O]", "[Se][Se]C"])
def test_anything_else_takes_the_ordinary_path(smiles):
    """A charged species, a substituted radical, closed-shell water and ethane, an atom: none is in the table."""
    assert entry_for(Chem.MolFromSmiles(smiles)) is None
    outcome, _ = build(smiles) if smiles not in ("[O]",) else (None, None)
    if outcome is not None:
        assert outcome.geometry_method != OPEN_SHELL_TABLE


def test_every_entry_names_its_source_and_its_convention():
    assert {e.name for e in ENTRIES} >= {"O2", "NO", "OH", "SO", "S2", "Se2", "CH3", "NH2"}
    assert all(e.source and e.convention for e in ENTRIES)
