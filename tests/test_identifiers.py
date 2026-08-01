"""Copying a structure's identifiers.

These matter more than they look. The naming benchmark
(benchmarks/naming) established that most structures have no verified
IUPAC name, so a SMILES or an InChIKey is frequently the only
unambiguous way to refer to a molecule at all.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.identifiers import KINDS, identifier_for_molblock


def _molblock(smiles: str) -> str:
    return Chem.MolToMolBlock(Chem.MolFromSmiles(smiles))


def test_smiles_round_trips_to_the_same_molecule():
    block = _molblock("CC(=O)Oc1ccccc1C(=O)O")

    got = identifier_for_molblock(block, "smiles")

    assert Chem.MolToSmiles(Chem.MolFromSmiles(got)) == Chem.MolToSmiles(
        Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")
    )


def test_stereochemistry_survives_the_copy():
    """Dropping it would silently equate two different compounds -- and
    the two enantiomers of a drug are not interchangeable."""
    r = identifier_for_molblock(_molblock("C[C@H](N)C(=O)O"), "smiles")
    s = identifier_for_molblock(_molblock("C[C@@H](N)C(=O)O"), "smiles")

    assert "@" in r and "@" in s
    assert r != s


def test_inchikey_is_the_expected_shape():
    """Fixed-length, hyphenated, no characters that break a URL or a
    spreadsheet cell -- which is why it is the one to paste into a search
    engine."""
    key = identifier_for_molblock(_molblock("CCO"), "inchikey")

    assert key == "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"
    block1, block2, block3 = key.split("-")
    assert (len(block1), len(block2), len(block3)) == (14, 10, 1)


def test_inchi_is_produced():
    inchi = identifier_for_molblock(_molblock("CCO"), "inchi")

    assert inchi.startswith("InChI=1S/C2H6O")


def test_an_unparseable_structure_yields_nothing_rather_than_raising():
    """Every caller is a context-menu action. A structure that will not
    parse is a normal thing to right-click, not an error worth
    interrupting someone over."""
    for kind in KINDS:
        assert identifier_for_molblock("not a molblock", kind) == ""
        assert identifier_for_molblock("", kind) == ""


def test_an_unknown_kind_is_a_programming_error_and_says_so():
    with pytest.raises(ValueError, match="Unknown identifier kind"):
        identifier_for_molblock(_molblock("CCO"), "iupac")
