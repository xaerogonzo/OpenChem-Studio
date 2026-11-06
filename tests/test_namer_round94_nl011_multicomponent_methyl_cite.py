"""NL-011: multicomponent dispiro must not cite spurious methyl partners (bucket C narrow).

After bucket C, chains #6/#7/#14 regressed to ``5-methylbicyclo`` / ``2-methyltricyclo`` citations
that OPSIN cannot parse. Only N-alkyl on aza partners (#13) may use the expanded display name.
"""

from __future__ import annotations

from openchem.vendor.iupac_namer import name_smiles

# seed 8901 #7 — was unparsable with double 5-methylbicyclo citations post bucket C.
SMILES_7 = "C1CN2CCC1C1(C3CCC1C3)C21C2CCC1C2"


def test_nl011_seed8901_chain7_no_spurious_methyl_partner_citations():
    got = name_smiles(SMILES_7)
    assert "5-methylbicyclo" not in got
    assert "dispiro[" in got
