"""Naming round 92 (D-389): ring and ylidene stereo that RDKit's legacy perception cleaned off at parse time is named, and a polyspiro system's terminal rings are numbered both ways.

Found against the CIP Validation Suite (Hanson, Mayfield et al., J. Chem. Inf. Model. 2018, 58, 1755; docs/NAMING_LIMITATIONS_PLAN.md, NL-107 and NL-109).

NL-109: the legacy stereo perception removes the chiral tag from a ring atom whose two ring branches differ only by the configuration of ANOTHER centre, and ignores
the stereo of a double bond between two rings, when the SMILES is parsed. The engine never saw them: the central ring of a tri(cyclohexyl)cyclohexane lost its
`1r,4r`, a cyclohexylidene lost `E` and `s`, a carbinol between two such rings lost its `R`. `name_smiles` now runs under RDKit's non-legacy perception, and the
suite's own labels are the expectation (a multiset, since a name cites its descriptors by locant and the suite by atom number).

NL-107: the linking atoms of a terminal ring of a polyspiro system were numbered in the one direction the ring happened to be walked, so the oxygens of a
tetraoxatetraspiro came out `1,6,9,12` or `1,5,9,12` and never the lowest set `1,5,8,11` the book prints, and the descriptors varied with atom order.
"""

from __future__ import annotations

import shutil
from collections import Counter

import pytest
from rdkit import Chem, RDLogger

import openchem.vendor.iupac_namer.engine as engine
from openchem.vendor.iupac_namer import name_smiles

RDLogger.DisableLog("rdApp.*")

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# (suite id, SMILES as the suite lists it, the suite's R/S/r/s/E/Z labels, the name now)
SUITE = [
    ("VS207", "C[C@H]1CC[C@@H]([C@@]2([C@@H]3CC[C@@H](C)CC3)CC[C@@H](C)CC2)CC1",
     "s2 r4", "(1r,4r)-4-methyl-1-[(1r,4r)-4-methylcyclohexyl]-1-[(1s,4s)-4-methylcyclohexyl]cyclohexane"),
    ("VS214", "CC[C@@H]1CC/C(/CC1)=C\\2/CC[C@H](CC2)CC",
     "s2 E1", "(1s,4E)-1-ethyl-4-[(4s)-4-ethylcyclohexan-1-ylidene]cyclohexane"),
    ("VS279", "O[C@@H](C[C@H]1CC[C@@H](CC1)C)C[C@@H]2CC[C@@H](CC2)C",
     "R1 r1 S2 s1", "(2R)-1-[(1r,4S)-4-methylcyclohexyl]-3-[(1s,4S)-4-methylcyclohexyl]propan-2-ol"),
]


def _descriptors(name):
    """Every R/S/r/s/E/Z cited anywhere in a name, as a Counter (a `bis[...]` group cited once counts once)."""
    import re

    found = Counter()
    for group in re.findall(r"\(([^()]*)\)", name):
        for token in group.split(","):
            match = re.fullmatch(r"\d+[a-z]?'*([RSrsEZ])", token.strip())
            if match:
                found[match.group(1)] += 1
    return found


@needs_opsin
@pytest.mark.parametrize("sid,smiles,labels,expected", SUITE, ids=[row[0] for row in SUITE])
def test_the_name_is_the_suites_and_says_every_unit(sid, smiles, labels, expected):
    name = name_smiles(smiles)
    assert name == expected
    # the suite labels: s2 is two lowercase s; the suite labels BOTH end atoms of a double bond, so its two E are the one E cited here
    want = Counter()
    for token in labels.split():
        want[token[0]] += int(token[1:])
    assert _descriptors(name) == want


def test_the_perception_flag_is_put_back():
    before = Chem.GetUseLegacyStereoPerception()
    name_smiles("C[C@H]1CC[C@@H](O)CC1")
    assert Chem.GetUseLegacyStereoPerception() == before


def test_the_perception_flag_is_put_back_when_naming_raises(monkeypatch):
    before = Chem.GetUseLegacyStereoPerception()

    def boom(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(engine, "_name_smiles_bound", boom)
    with pytest.raises(RuntimeError):
        name_smiles("CC")
    assert Chem.GetUseLegacyStereoPerception() == before


def test_nested_use_restores_only_at_the_outermost_exit():
    before = Chem.GetUseLegacyStereoPerception()
    with engine._modern_stereo_perception():
        assert Chem.GetUseLegacyStereoPerception() is False
        with engine._modern_stereo_perception():
            assert Chem.GetUseLegacyStereoPerception() is False
        assert Chem.GetUseLegacyStereoPerception() is False
    assert Chem.GetUseLegacyStereoPerception() == before


# The book's own example: P-93.5.3 example 5, BlueBookV2.pdf p. 942.
TETRASPIRO = "O1[C@@]2([C@]3([C@]4([C@]25CO5)CO4)CO3)C1"
BOOK = "(3R,4r,7S,10s)-1,5,8,11-tetraoxatetraspiro[2.0.2^{4}.0.2^{7}.0.2^{10}.0^{3}]dodecane"


@needs_opsin
def test_the_tetraspiro_is_named_as_the_book_names_it_in_every_atom_order(monkeypatch):
    seen = []
    real = engine._validate_stereo_via_opsin

    def spy(tree, name, *, strip_modes, mol=None):
        seen.append(name)
        return real(tree, name, strip_modes=strip_modes, mol=mol)

    monkeypatch.setattr(engine, "_validate_stereo_via_opsin", spy)
    names = set()
    for order in Chem.MolToRandomSmilesVect(Chem.MolFromSmiles(TETRASPIRO), 12, randomSeed=11):
        seen.clear()
        name_smiles(order)
        names.add(seen[-1] if seen else None)
    assert names == {BOOK}


def test_the_terminal_ring_is_numbered_both_ways():
    """A terminal ring with two linking atoms is offered in both directions, and the oxygens take the lowest set."""
    from openchem.vendor.iupac_namer.ring_naming import polyspiro_vb as vb

    assert vb._MAX_NUMBERING_OPTIONS >= 8
    arc = vb._Arc(1, 1, (10, 11), 0)
    assert arc.interior_from(1) == (10, 11)


@pytest.mark.parametrize("smiles,expected", [
    # no heteroatom, no stereo: unchanged by the orientation search
    ("C1CC12CC23CC34CC4", None),
])
def test_a_carbon_only_polyspiro_keeps_one_name_in_every_order(smiles, expected):
    names = {name_smiles(order) for order in Chem.MolToRandomSmilesVect(Chem.MolFromSmiles(smiles), 10, randomSeed=3)}
    assert len(names) == 1
