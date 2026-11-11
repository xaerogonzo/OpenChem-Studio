"""Mode B pieces: identity is the graph, not the formula.

Contract: docs/SALT_COMPOSITION_DESIGN.md.
"""

from rdkit import Chem

from openchem.chem.salt_components import fragment_key


def _mol(smiles: str) -> Chem.Mol:
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None
    return mol


def test_butanoate_and_methylpropanoate_do_not_share_an_identity() -> None:
    a = fragment_key(_mol("CCCC(=O)[O-]"))
    b = fragment_key(_mol("CC(C)C(=O)[O-]"))
    assert isinstance(a, str) and isinstance(b, str)
    assert a != b
    formula_a = Chem.rdMolDescriptors.CalcMolFormula(_mol("CCCC(=O)[O-]"))
    formula_b = Chem.rdMolDescriptors.CalcMolFormula(_mol("CC(C)C(=O)[O-]"))
    assert formula_a.split("-")[0] == formula_b.split("-")[0]


def test_atom_maps_are_stripped_from_the_key() -> None:
    mapped = _mol("[Na+:1]")
    plain = _mol("[Na+]")
    assert fragment_key(mapped) == fragment_key(plain)


def test_enantiomeric_carboxylates_keep_distinct_keys() -> None:
    r = fragment_key(_mol("C[C@H](O)C(=O)[O-]"))
    s = fragment_key(_mol("C[C@@H](O)C(=O)[O-]"))
    assert r != s


def test_sodium_oxide_is_not_sulfate() -> None:
    oxide = fragment_key(_mol("[O-2]"))
    sulfate = fragment_key(_mol("S(=O)(=O)([O-])[O-]"))
    assert oxide != sulfate
