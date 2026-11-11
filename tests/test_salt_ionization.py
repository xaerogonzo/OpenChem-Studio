from rdkit import Chem

from openchem.chem.salt_components import fragment_formal_charge, fragment_key
from openchem.chem.salt_ionization import SiteTransform, apply_site_transform


def _acetic() -> Chem.Mol:
    return Chem.MolFromSmiles("CC(=O)O")


def test_deprotonating_acetic_acid_updates_hydrogen_and_charge() -> None:
    mol = _acetic()
    oxygen = next(
        atom.GetIdx()
        for atom in mol.GetAtoms()
        if atom.GetSymbol() == "O" and atom.GetTotalNumHs() == 1
    )
    result = apply_site_transform(mol, SiteTransform(oxygen, "deprotonate"))
    assert fragment_formal_charge(result) == -1
    assert fragment_key(result) == "CC(=O)[O-]"
    # parent unchanged
    assert fragment_formal_charge(mol) == 0


def test_protonating_pyridine_updates_hydrogen_and_charge() -> None:
    mol = Chem.MolFromSmiles("c1ccncc1")
    nitrogen = next(atom.GetIdx() for atom in mol.GetAtoms() if atom.GetSymbol() == "N")
    result = apply_site_transform(mol, SiteTransform(nitrogen, "protonate"))
    assert fragment_formal_charge(result) == 1
    assert "[nH+]" in fragment_key(result) or "c1cc[nH+]cc1" == fragment_key(result)


def test_a_bad_atom_index_is_refused() -> None:
    mol = _acetic()
    refused = apply_site_transform(mol, SiteTransform(99, "deprotonate"))
    assert refused.code == "invalid_site"
