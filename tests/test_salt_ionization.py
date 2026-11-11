from rdkit import Chem

from openchem.chem.salt_components import fragment_formal_charge, fragment_key
from openchem.chem.salt_ionization import (
    SiteTransform,
    apply_site_transform,
    select_by_net_charge,
    structures_at_net_charge,
)
from openchem.domain.salt_stoichiometry import IonizationRefusal


def _acetic() -> Chem.Mol:
    return Chem.MolFromSmiles("CC(=O)O")


def test_deprotonating_explicit_hydrogen_acetic_acid_removes_the_bonded_hydrogen() -> None:
    parent = Chem.AddHs(Chem.MolFromSmiles("CC(=O)O"))
    oxygen = next(
        atom.GetIdx()
        for atom in parent.GetAtoms()
        if atom.GetSymbol() == "O" and any(neighbor.GetAtomicNum() == 1 for neighbor in atom.GetNeighbors())
    )
    parent_smiles = Chem.MolToSmiles(parent)
    result = apply_site_transform(parent, SiteTransform(oxygen, "deprotonate"))
    assert fragment_formal_charge(result) == -1
    assert fragment_key(result) == "CC(=O)[O-]"
    assert Chem.MolToSmiles(parent) == parent_smiles


def test_protonating_explicit_hydrogen_oxygen_does_not_stack_a_hydrogen_property() -> None:
    parent = Chem.AddHs(Chem.MolFromSmiles("CC(=O)O"))
    oxygen = next(
        atom.GetIdx()
        for atom in parent.GetAtoms()
        if atom.GetSymbol() == "O" and any(neighbor.GetAtomicNum() == 1 for neighbor in atom.GetNeighbors())
    )
    parent_smiles = Chem.MolToSmiles(parent)
    result = apply_site_transform(parent, SiteTransform(oxygen, "protonate"))
    assert fragment_formal_charge(result) == 1
    assert fragment_key(result) == "CC(=O)[OH2+]"
    assert Chem.MolToSmiles(parent) == parent_smiles


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


def test_acetic_acid_at_minus_one_is_acetate() -> None:
    mol = Chem.MolFromSmiles("CC(=O)O")
    chosen = select_by_net_charge(mol, -1)
    assert chosen == fragment_key(Chem.MolFromSmiles("CC(=O)[O-]"))


def test_acetic_acid_at_plus_one_is_net_charge_only() -> None:
    mol = Chem.MolFromSmiles("CC(=O)O")
    refused = select_by_net_charge(mol, 1)
    assert isinstance(refused, IonizationRefusal)
    assert refused.code == "net_charge_only"


def test_two_inequivalent_sites_at_the_same_charge_are_not_picked() -> None:
    # 4-hydroxybenzoic acid: carboxylate vs phenolate at -1 are different graphs.
    # If RDKit collapses them to one SMILES, identity is graph, not formula —
    # switch the pair to tyrosol (OCCc1ccc(O)cc1).
    mol = Chem.MolFromSmiles("O=C(O)c1ccc(O)cc1")
    keys = structures_at_net_charge(mol, -1)
    assert len(set(keys)) >= 2
    refused = select_by_net_charge(mol, -1)
    assert isinstance(refused, IonizationRefusal)
    assert refused.code == "ambiguous_microspecies"
