"""WS5 P2: NL-051..NL-055 — programme closure on charge and ring-cation work (rounds 41–54).

These limitations were **carried** without structures in the plan text; the round test files
hold the full pin sets. Programme disposition (2026-11-16): **closed** by re-measuring exemplars
here and pointing at the round files for exhaustive coverage.

Residual gaps called out in the plan (not pursued here): NL-051 (f) census non-exact rows;
NL-051 (e) `N-[methoxy(oxo)methyl]…` vs book `methoxycarbonyl`; NL-055 items still listed in
vendor KNOWN_LIMITATIONS (Hantzsch-Widman ring cations, some curated tables).
"""

from __future__ import annotations

import shutil

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import inchi

from openchem.vendor.iupac_namer import name_smiles

RDLogger.DisableLog("rdApp.*")

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

PINS = [
    # NL-051 (round 49–54)
    (
        "NL-051 acyl isothiourea thiolate",
        "NC([S-])=NC(=O)c1ccccc1",
        "amino(benzoylimino)methanethiolate",
    ),
    (
        "NL-051 N-sulfonyl iminium (named since round 50)",
        "CC(=[NH+]S(=O)(=O)C)C",
        "methylsulfonyl(propan-2-ylidene)azanium",
    ),
    (
        "NL-051 hydrazide anion (round 51)",
        "CC(=O)[N-]N",
        "acetyl(amino)azanide",
    ),
    (
        "NL-051 amidinium with two neutral acids (round 54)",
        "NC(=[NH2+])C(C(=O)O)(C(=O)O)C(=O)[O-]",
        "2-carboxylato-3-hydroxy-2-carboxy-3-oxopropanamidinium",
    ),
    (
        "NL-051 N-acyl sulfonamidate spelling",
        "CS(=O)(=O)[N-]C(=O)OC",
        "N-[methoxy(oxo)methyl]methanesulfonamidate",
    ),
    # NL-052 (rounds 46–49)
    (
        "NL-052 isothiourea thiolate prefix",
        "[S-]C(=N)N",
        "amino(imino)methanethiolate",
    ),
    (
        "NL-052 protonated thioimidate (round 49)",
        "CC(=[NH2+])S",
        "(1-sulfanylethylidene)azanium",
    ),
    (
        "NL-052 hydro azolium indicated H (round 48)",
        "Cn1c[n+](C)c2CCCCc12",
        "1,3-dimethyl-4,5,6,7-tetrahydro-1H-benzimidazol-3-ium",
    ),
    # NL-053 (rounds 43–45, 44)
    (
        "NL-053 amidinium beside second acid",
        "NC(=[NH2+])CCC(C(=O)[O-])C(=O)O",
        "4-carboxylato-5-hydroxy-5-oxopentanamidinium",
    ),
    (
        "NL-053 anion as parent beside nitrile",
        "N#Cc1ccc([O-])cc1",
        "4-cyanobenzen-1-olate",
    ),
    (
        "NL-053 protonated acylhydrazone cation",
        "C=[NH+]NC(=O)c1ccccc1",
        "benzamido(methylidene)azanium",
    ),
    (
        "NL-053 phenolate beside neutral OH",
        "N#Cc1ccc([O-])cc1O",
        "4-cyano-3-hydroxybenzen-1-olate",
    ),
    # NL-054 (rounds 36, 43)
    (
        "NL-054 exocyclic ylidene ring cation",
        "C=C1CCC[NH+]=C1",
        "5-methylidene-2,3,4,5-tetrahydropyridin-1-ium",
    ),
    (
        "NL-054 N-substituted pyrrolinium retained spelling",
        "C[N+]1=CCCC1",
        "1-methyl-3,4-dihydro-2H-pyrrol-1-ium",
    ),
    # NL-055 (rounds 40–41, 48)
    (
        "NL-055 fused azetidinium (round 40)",
        "C1CCC2[NH+](CC1)CC2",
        "1-azabicyclo[5.2.0]nonan-1-ium",
    ),
    (
        "NL-055 curated lactam cation",
        "C[N+]1(C)CCN2C1OCC2",
        "7,7-dimethylhexahydroimidazo[2,1-b][1,3]oxazol-7-ium",
    ),
    (
        "NL-055 bicyclic amidinium resonance form A",
        "C1CCN2CCC[NH+]=C2C1",
        "3,4,6,7,8,9-hexahydro-2H-pyrido[1,2-a]pyrimidin-1-ium",
    ),
    (
        "NL-055 bicyclic amidinium resonance form B",
        "C1CC[N+]2=C(C1)NCCC2",
        "3,4,6,7,8,9-hexahydro-2H-pyrido[1,2-a]pyrimidin-1-ium",
    ),
    (
        "NL-055 second-order fusion built (round 40)",
        "c1ncc2cc3cc[nH]c3nc2n1",
        "8H-pyrrolo[3',2':5,6]pyrido[2,3-d]pyrimidine",
    ),
]

AZINAN_WRONG = "5-methylideneazinan-1-ium"
ACYL_THIOLATE = PINS[0][1]


@pytest.mark.parametrize("label,smiles,expected", PINS, ids=[p[0] for p in PINS])
def test_engine_keeps_documented_name(label, smiles, expected):
    del label
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", PINS, ids=[p[0] for p in PINS])
def test_documented_name_round_trips_where_opsin_can(label, smiles, expected):
    del label
    from py2opsin import py2opsin

    back = py2opsin(expected)
    if not back:
        pytest.skip(f"OPSIN cannot parse {expected!r}")
    assert inchi.MolToInchiKey(Chem.MolFromSmiles(back)) == inchi.MolToInchiKey(
        Chem.MolFromSmiles(smiles)
    )


def test_nl054_never_emits_saturated_azinan_wrong_molecule():
    assert name_smiles("C=C1CCC[NH+]=C1") != AZINAN_WRONG


def test_nl051_sulfonamidate_uses_engine_spelling_not_methoxycarbonyl_pin():
    got = name_smiles("CS(=O)(=O)[N-]C(=O)OC")
    assert "methoxy(oxo)methyl" in got
    assert got == "N-[methoxy(oxo)methyl]methanesulfonamidate"


def test_nl051_acyl_thiolate_no_sulfanide_prefix(monkeypatch):
    """Strict ownership: no latent `sulfanide` prefix (round 49)."""
    monkeypatch.setenv("OPENCHEM_NAMER_OWNERSHIP", "enforce")
    name = name_smiles(ACYL_THIOLATE)
    assert name == "amino(benzoylimino)methanethiolate"
    assert "sulfanide" not in name