"""HOSE-style environment codes.

These tests are the whole warranty on the code generator, because there
is no reference implementation available here to diff against (CDK is
Java, and there is no JVM on this machine). So they check the PROPERTIES
that make a lookup correct rather than any particular string, and they
use molecules whose symmetry is not in doubt.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.hose_codes import hose_code, hose_codes, hose_codes_for_element


def _carbon_codes(smiles: str, spheres: int) -> dict[int, str]:
    mol = Chem.MolFromSmiles(smiles)
    return {
        atom.GetIdx(): hose_code(mol, atom.GetIdx(), spheres)
        for atom in mol.GetAtoms()
        if atom.GetSymbol() == "C"
    }


def test_equivalent_atoms_share_a_code():
    """Benzene's six carbons are one environment. If they produced six
    codes, every benzene ring in the database would be six separate
    lookups with a sixth of the evidence each."""
    codes = _carbon_codes("c1ccccc1", 3)

    assert len(set(codes.values())) == 1


def test_toluene_resolves_exactly_its_five_environments():
    """Methyl, ipso, ortho, meta, para -- no more, no fewer. Too few means
    the code cannot tell shifts apart; too many means it splits evidence
    that should have been pooled."""
    codes = _carbon_codes("Cc1ccccc1", 4)

    groups: dict[str, list[int]] = {}
    for index, code in codes.items():
        groups.setdefault(code, []).append(index)

    assert len(groups) == 5
    assert sorted(sorted(v) for v in groups.values()) == [[0], [1], [2, 6], [3, 5], [4]]


def test_a_code_does_not_depend_on_how_the_molecule_was_numbered():
    """The property most easily lost. Ordering branches by a
    whole-molecule canonical rank would pass every other test here and
    still break lookups between molecules."""
    forwards = Chem.MolFromSmiles("CCO")
    backwards = Chem.MolFromSmiles("OCC")

    assert sorted(hose_code(forwards, i, 4) for i in range(forwards.GetNumAtoms())) == sorted(
        hose_code(backwards, i, 4) for i in range(backwards.GetNumAtoms())
    )


def test_the_same_environment_in_different_molecules_gets_the_same_code():
    """The point of the whole exercise: a lookup only works if an
    environment recognises itself across molecules. The methyl of ethanol
    and the methyl of propan-1-ol share their first two spheres."""
    ethanol = Chem.MolFromSmiles("CCO")
    propanol = Chem.MolFromSmiles("CCCO")

    # Sphere 2 from the terminal CH3: itself, its CH2, and that CH2's
    # substituents -- identical in both.
    assert hose_code(ethanol, 0, 1) == hose_code(propanol, 0, 1)


def test_different_environments_get_different_codes():
    codes = _carbon_codes("CCO", 3)

    assert codes[0] != codes[1]


def test_a_ring_closure_is_marked_rather_than_followed():
    """Without the marker a ring and a chain of the same length would be
    indistinguishable -- and following it would not terminate."""
    code = hose_code(Chem.MolFromSmiles("C1CC1"), 0, 3)  # cyclopropane, 3 spheres

    assert "&" in code


def test_a_ring_and_an_open_chain_are_told_apart():
    ring = hose_code(Chem.MolFromSmiles("C1CCCCC1"), 0, 6)
    chain = hose_code(Chem.MolFromSmiles("CCCCCC"), 0, 6)

    assert ring != chain


def test_deeper_spheres_are_at_least_as_discriminating():
    """A lookup widens by REDUCING the sphere count, so a shallower code
    must never separate atoms that a deeper one merged."""
    for spheres in (1, 2, 3, 4):
        shallow = _carbon_codes("Cc1ccccc1", spheres)
        deep = _carbon_codes("Cc1ccccc1", spheres + 1)
        assert len(set(deep.values())) >= len(set(shallow.values()))


def test_codes_come_back_largest_sphere_first():
    """The order a lookup tries them: most specific first, widening only
    when there is not enough evidence."""
    mol = Chem.MolFromSmiles("Cc1ccccc1")

    listed = hose_codes(mol, 1, max_spheres=4)

    assert len(listed) == 4
    assert listed[0] == hose_code(mol, 1, 4)
    assert listed[-1] == hose_code(mol, 1, 1)


def test_a_proton_is_described_by_the_atom_it_sits_on():
    """A hydrogen has no environment of its own beyond one bond, so its
    code is its parent's. Two protons on one carbon therefore match --
    which is right, they are equivalent."""
    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))

    proton_codes = hose_codes_for_element(mol, "H", max_spheres=3)
    methyl_protons = [
        index
        for index in proton_codes
        if mol.GetAtomWithIdx(index).GetNeighbors()[0].GetIdx() == 0
    ]

    assert len(methyl_protons) == 3
    assert len({tuple(proton_codes[i]) for i in methyl_protons}) == 1


def test_hydroxyl_and_methyl_protons_do_not_share_a_code():
    mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    proton_codes = hose_codes_for_element(mol, "H", max_spheres=3)

    by_parent = {
        index: mol.GetAtomWithIdx(index).GetNeighbors()[0].GetSymbol() for index in proton_codes
    }
    on_carbon = next(i for i, symbol in by_parent.items() if symbol == "C")
    on_oxygen = next(i for i, symbol in by_parent.items() if symbol == "O")

    assert proton_codes[on_carbon] != proton_codes[on_oxygen]


@pytest.mark.parametrize("smiles", ["CCO", "c1ccccc1", "CC(=O)O", "C1CCCCC1", "CC#N"])
def test_generation_is_deterministic(smiles):
    mol = Chem.MolFromSmiles(smiles)

    first = [hose_code(mol, i, 4) for i in range(mol.GetNumAtoms())]
    second = [hose_code(mol, i, 4) for i in range(mol.GetNumAtoms())]

    assert first == second


def test_bond_order_changes_the_code():
    """Carbonyl and alcohol carbons must not collide."""
    ketone = hose_code(Chem.MolFromSmiles("CC(=O)C"), 1, 2)
    alcohol = hose_code(Chem.MolFromSmiles("CC(O)C"), 1, 2)

    assert ketone != alcohol
