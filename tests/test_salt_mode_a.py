"""Mode A from four molecules: two parents and two product ions.

Contract: docs/SALT_COMPOSITION_DESIGN.md.
"""

from rdkit import Chem

from openchem.chem.salt_mode_a import compose_from_mols
from openchem.domain.salt_stoichiometry import ModeAComposition, ModeARefusal


def _mol(smiles: str) -> Chem.Mol:
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None
    return mol


def test_ethylamine_and_acetic_acid_mols_are_one_to_one() -> None:
    result = compose_from_mols(
        _mol("CCN"),
        _mol("CC(=O)O"),
        _mol("CC[NH3+]"),
        _mol("CC(=O)[O-]"),
    )
    assert result == ModeAComposition(
        cation_count=1, anion_count=1, charge_valid=True
    )


def test_sodium_hydroxide_and_acetic_acid_mols_are_refused() -> None:
    result = compose_from_mols(
        _mol("[Na]O"),
        _mol("CC(=O)O"),
        _mol("[Na+]"),
        _mol("CC(=O)[O-]"),
    )
    assert isinstance(result, ModeARefusal)
    assert result.code == "hydroxide_neutralization"


def test_ethylamine_and_sulfate_mols_are_refused() -> None:
    result = compose_from_mols(
        _mol("CCN"),
        _mol("S(=O)(=O)([O-])[O-]"),
        _mol("CC[NH3+]"),
        _mol("S(=O)(=O)([O-])[O-]"),
    )
    assert isinstance(result, ModeARefusal)
    assert result.code == "missing_proton_source"
