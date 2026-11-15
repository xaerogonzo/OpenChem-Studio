"""WP3 of docs/HYPERVALENT_COVERAGE_DESIGN.md: DREIDING does not type a centre that has more neighbours than its type allows.

Measured before the fix (explicit hydrogens, ETKDG start): SF6 typed `S_3` came out at 708 kcal/mol, PF5 as `P_3` at 163, SF4 at 394,
IF5 as a one-bond halogen at 1053, a perchlorate chlorine at 404, PhSF5 at 623, PIDA at 256: numbers that mean nothing, shown by
Geometry as an energy. Ordinary molecules keep their types, and an onium or borate centre keeps its four.
"""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.dreiding import UntypedAtomError, assign_types, dreiding_energy
from openchem.chem.geometry_analysis import force_field_energies

OVER_COORDINATED = {
    "SF6": "FS(F)(F)(F)(F)F", "SF4": "FS(F)(F)F", "PF5": "FP(F)(F)(F)F", "PCl5": "ClP(Cl)(Cl)(Cl)Cl", "IF5": "FI(F)(F)(F)F",
    "PhSF5": "FS(F)(F)(F)(F)c1ccccc1", "PIDA": "CC(=O)OI(OC(C)=O)c1ccccc1", "CH3PF4": "CP(F)(F)(F)F",
    "perchlorate": "[O-]Cl(=O)(=O)=O",
}
#: smiles -> {element: type} for the centres that matter.
TYPED = {
    "ethanol": ("CCO", {"C": "C_3", "O": "O_3"}),
    "chloromethane": ("CCl", {"Cl": "Cl"}),
    "iodobenzene": ("Ic1ccccc1", {"I": "I_", "C": "C_R"}),
    "phosphine": ("CP(C)C", {"P": "P_3"}),
    "PPh3": ("c1ccccc1P(c1ccccc1)c1ccccc1", {"P": "P_3"}),
    "ammonium": ("C[N+](C)(C)C", {"N": "N_3"}),
    "phosphonium": ("C[P+](C)(C)C", {"P": "P_3"}),
    "sulfonium": ("C[S+](C)C", {"S": "S_3"}),
    "thioether": ("CSC", {"S": "S_3"}),
    "thiol": ("CS", {"S": "S_3"}),
    "tetrahydroborate": ("[BH4-]", {"B": "B_3"}),
    "silane": ("C[SiH3]", {"Si": "Si3"}),
    "benzene": ("c1ccccc1", {"C": "C_R"}),
    "amide": ("CC(=O)N", {"N": "N_R"}),
}


def _explicit(smiles: str) -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=1)
    return mol


@pytest.mark.parametrize("name", OVER_COORDINATED)
def test_an_over_coordinated_centre_is_not_typed(name):
    mol = _explicit(OVER_COORDINATED[name])
    with pytest.raises(UntypedAtomError) as caught:
        assign_types(mol)
    assert "neighbours" in str(caught.value)
    with pytest.raises(UntypedAtomError):
        dreiding_energy(mol)


@pytest.mark.parametrize("name", TYPED)
def test_ordinary_and_onium_centres_keep_their_types(name):
    smiles, expected = TYPED[name]
    mol = _explicit(smiles)
    types = assign_types(mol)
    for atom, t in zip(mol.GetAtoms(), types):
        if atom.GetSymbol() in expected:
            assert t == expected[atom.GetSymbol()], (name, atom.GetSymbol(), t)
    assert dreiding_energy(mol).total == dreiding_energy(mol).total  # finite, a number


def test_geometry_analysis_leaves_the_dreiding_energy_empty_for_a_hypervalent_molecule():
    energies = force_field_energies(_explicit("FS(F)(F)(F)(F)F"))
    assert energies["dreiding"] is None
    assert force_field_energies(_explicit("CCO"))["dreiding"] is not None
