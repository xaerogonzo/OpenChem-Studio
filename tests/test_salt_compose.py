"""Salt-composition preview from molecules, the path the window calls."""

from rdkit import Chem

from openchem.chem.salt_compose import compose
from openchem.domain.salt_preview import (
    DISCLAIMER,
    MODE_ANALYZE,
    MODE_ENUMERATE,
    MODE_IONS,
    MODE_NEUTRALS,
)


def _mol(smiles: str) -> Chem.Mol:
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None
    return mol


def test_disclaimer_is_on_every_preview() -> None:
    preview = compose(MODE_ANALYZE, _mol("[NH4+].[Cl-]"), None)
    assert preview.body.startswith(DISCLAIMER)
    assert "isolable salt" in DISCLAIMER


def test_ammonium_chloride_drawing_is_charge_valid() -> None:
    preview = compose(MODE_ANALYZE, _mol("[NH4+].[Cl-]"), None)
    assert preview.charge_valid is True
    assert "theoretical ratio" in preview.body


def test_ethylamine_and_acetic_acid_are_one_to_one() -> None:
    preview = compose(MODE_NEUTRALS, _mol("CCN"), _mol("CC(=O)O"))
    assert preview.charge_valid is True
    assert "1 : 1" in preview.headline
    assert "pKa evidence: missing" in preview.body


def test_sodium_hydroxide_is_refused() -> None:
    preview = compose(MODE_NEUTRALS, _mol("[Na]O"), _mol("CC(=O)O"))
    assert preview.charge_valid is False
    assert "hydroxide_neutralization" in preview.body


def test_two_ions_as_drawn() -> None:
    preview = compose(MODE_IONS, _mol("CC[NH3+]"), _mol("CC(=O)[O-]"))
    assert preview.charge_valid is True
    assert "pKa evidence: not_assessed" in preview.body


def test_enumerate_pyridinium_acetate() -> None:
    preview = compose(MODE_ENUMERATE, _mol("c1ccncc1"), _mol("CC(=O)O"))
    assert preview.charge_valid is True
    assert "1 : 1" in preview.headline
    assert "omitted 0" in preview.body
