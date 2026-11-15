"""NL-088 and NL-089 (WS3): deliberate benchmark policies, not defects.

NL-088: all purine tautomers normalise to ``9H-purine`` (xanthine/caffeine numbering).
NL-089: metformin uses the book's ``imidodicarbonimidic diamide`` PIN (D-079), not retained
``biguanide``; the benchmark row is tautomer-agnostic by policy.
"""

from __future__ import annotations

from openchem.vendor.iupac_namer import name_smiles

# Four purine NH placements; keys match ``data_loader.py`` retained entries (D-026u).
PURINE_TAUTOMERS = (
    "c1nc2c[nH]cnc-2n1",
    "c1nc2cnc[nH]c-2n1",
    "c1ncc2nc[nH]c2n1",
    "c1ncc2[nH]cnc2n1",
)
PURINE_PIN = "9H-purine"

METFORMIN = "CN(C)C(=N)NC(N)=N"
METFORMIN_PIN = "N1,N1-dimethylimidodicarbonimidic diamide"


def test_nl088_four_purine_tautomers_all_name_9h_purine():
    names = {name_smiles(s) for s in PURINE_TAUTOMERS}
    assert names == {PURINE_PIN}


def test_nl089_metformin_uses_imidodicarbonimidic_book_pin():
    assert name_smiles(METFORMIN) == METFORMIN_PIN