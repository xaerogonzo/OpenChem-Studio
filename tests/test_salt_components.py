"""Mode B pieces: identity is the graph, not the formula.

Contract: docs/SALT_COMPOSITION_DESIGN.md.
"""

from rdkit import Chem

from openchem.chem.salt_components import analyze_drawing, fragment_key
from openchem.domain.salt_stoichiometry import TwoIonBalance


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


def test_two_chlorides_and_calcium_is_charge_neutral() -> None:
    mol = _mol("[Ca+2].[Cl-].[Cl-]")
    result = analyze_drawing(mol)
    assert result.code == "charge_neutral"
    assert result.charge_valid is True
    assert result.drawn_total_charge == 0
    assert result.theoretical == TwoIonBalance(cation_count=1, anion_count=2)
    calcium = next(c for c in result.ions if c.charge > 0)
    chloride = next(c for c in result.ions if c.charge < 0)
    assert calcium.drawn_count == 1 and chloride.drawn_count == 2


def test_one_chloride_and_calcium_is_not_silently_corrected() -> None:
    mol = _mol("[Ca+2].[Cl-]")
    result = analyze_drawing(mol)
    assert result.code == "unbalanced"
    assert result.charge_valid is False
    assert result.drawn_total_charge == 1
    assert result.theoretical == TwoIonBalance(cation_count=1, anion_count=2)
    chloride = next(c for c in result.ions if c.charge < 0)
    assert chloride.drawn_count == 1


def test_one_sodium_and_sulfate_is_unbalanced() -> None:
    mol = _mol("[Na+].S(=O)(=O)([O-])[O-]")
    result = analyze_drawing(mol)
    assert result.code == "unbalanced"
    assert result.charge_valid is False
    assert result.theoretical == TwoIonBalance(cation_count=2, anion_count=1)


def test_two_sodium_and_sulfate_is_charge_neutral() -> None:
    mol = _mol("[Na+].[Na+].S(=O)(=O)([O-])[O-]")
    result = analyze_drawing(mol)
    assert result.code == "charge_neutral"
    assert result.charge_valid is True
    sodium = next(c for c in result.ions if c.charge > 0)
    assert sodium.drawn_count == 2


def test_two_cations_and_one_anion_is_unsupported() -> None:
    mol = _mol("[Na+].[K+].[Cl-]")
    result = analyze_drawing(mol)
    assert result.code == "unsupported_multicomponent"
    assert result.theoretical is None
    assert result.charge_valid is False


def test_one_cation_and_two_anions_is_unsupported() -> None:
    mol = _mol("[Na+].[Cl-].[Br-]")
    result = analyze_drawing(mol)
    assert result.code == "unsupported_multicomponent"
    assert result.theoretical is None


def test_nacl_and_kbr_is_ambiguous() -> None:
    mol = _mol("[Na+].[Cl-].[K+].[Br-]")
    result = analyze_drawing(mol)
    assert result.code == "ambiguous_pairing"
    assert result.theoretical is None
    assert result.drawn_total_charge == 0
    assert result.charge_valid is True


def test_ethanol_and_benzene_is_not_a_salt() -> None:
    mol = _mol("CCO.c1ccccc1")
    result = analyze_drawing(mol)
    assert result.code == "not_a_salt"
    assert result.charge_valid is True
    assert result.ions == ()
    assert len(result.extras) == 2
    assert "coformer" not in result.reason.lower()
    assert "hydrate" not in result.reason.lower()
    assert "solvate" not in result.reason.lower()


def test_a_neutral_extra_beside_nacl_is_unclassified() -> None:
    mol = _mol("[Na+].[Cl-].CCO")
    result = analyze_drawing(mol)
    assert result.code == "charge_neutral"
    assert len(result.extras) == 1
    assert "coformer" not in result.reason.lower()


def test_glycine_zwitterion_is_one_molecule() -> None:
    mol = _mol("C(C(=O)[O-])[NH3+]")
    result = analyze_drawing(mol)
    assert result.code == "zwitterion"
    assert result.charge_valid is True
    assert result.ions == ()
    assert result.theoretical is None


def test_drawn_counts_survive_when_the_ratio_reduces() -> None:
    mol = _mol("[Ca+2].[Ca+2].[Cl-].[Cl-].[Cl-].[Cl-]")
    result = analyze_drawing(mol)
    assert result.code == "charge_neutral"
    calcium = next(c for c in result.ions if c.charge > 0)
    chloride = next(c for c in result.ions if c.charge < 0)
    assert calcium.drawn_count == 2
    assert chloride.drawn_count == 4
    assert result.theoretical == TwoIonBalance(cation_count=1, anion_count=2)
