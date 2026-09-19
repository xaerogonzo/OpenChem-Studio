"""
tests/test_fc_carbamates.py

Functional Class (FC) path for carbamates (R-O-C(=O)-N(R')(R'')).
Expected outputs verified against OPSIN canonical names.
"""
import logging
import pytest

logging.disable(logging.WARNING)

from openchem.vendor.iupac_namer.engine import name_smiles


@pytest.mark.parametrize("smiles,expected", [
    # Unsubstituted N (NH2)
    ("CCOC(=O)N",         "ethyl carbamate"),
    # N-monosubstituted
    # Naming round 4: no N locant -- carbamic acid has one substitutable atom
    # (P-16.5.1.3.2); "2-hydroxypropyl (2-aminoethyl)carbamate (PIN)", p. 601.
    ("CCOC(=O)NC",        "ethyl methylcarbamate"),
    ("CCCCOC(=O)Nc1ccccc1", "butyl phenylcarbamate"),
    ("CC(C)OC(=O)Nc1cccc(Cl)c1", "propan-2-yl (3-chlorophenyl)carbamate"),
    # N,N-disubstituted
    ("CCOC(=O)N(C)C",     "ethyl dimethylcarbamate"),
])
def test_carbamate_fc_naming(smiles, expected):
    result = name_smiles(smiles)
    assert result == expected, f"SMILES={smiles!r}: got {result!r}, expected {expected!r}"
