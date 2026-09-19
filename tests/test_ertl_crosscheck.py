"""Vocabulary v2 against Ertl's algorithm, both ways (plan B1).

The observations are regenerated from the pinned `Contrib/IFG/ifg.py` and
compared with the committed `ertl_mapping.toml`, so a pattern change that
moves what v2 covers shows up as a diff someone has to accept -- and every
Ertl category v2 leaves uncovered, and every v2 feature Ertl never marks,
has to carry a written reason. Ertl is an oracle, never a definition
(`docs/sources.toml`, ertl2017).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from rdkit import Chem

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import ertl_crosscheck as ec  # noqa: E402

#: Molecules whose category the paper's own Additional file 1 lists, with
#: that listing: the generalisation is checked against Ertl's table, not
#: against itself.
PAPER_CATEGORIES = [
    ("CC(=O)NC", "[R]N([R])C([R])=O"), ("CCOCC", "[R]O[R]"), ("CCN(C)C", "[R]N([R])[R]"),
    ("CF", "[R]F"), ("c1ccccc1O", "O[Car]"), ("CCO", "O[Cal]"), ("CC(=O)O", "[R]C(O)=O"),
    ("CCNCC", "[R]N[R]"), ("CS(C)(=O)=O", "[R]S([R])(=O)=O"), ("CC=O", "[R]C=O"),
    ("CC(C)=O", "[R]C([R])=O"), ("CC#N", "C#N"), ("c1ccncc1", "[Nar]"), ("CCS", "[R]S"),
    ("c1ccccc1N", "N[Car]"), ("CNS(=O)(=O)C", "[R]N([R])S([R])(=O)=O"),
    ("CNC(=O)NC", "[R]N([R])C(=O)N([R])[R]"), ("CC=CC", "C=C"), ("COC(C)=O", "[R]OC([R])=O"),
]


@pytest.fixture(scope="module")
def observed():
    return ec.observe()


def test_the_oracle_is_the_pinned_implementation():
    ec.ifg_module()  # raises on any other sha256


@pytest.mark.parametrize("smiles,pseudo", PAPER_CATEGORIES)
def test_the_generalisation_reproduces_the_papers_table(smiles, pseudo):
    mol = Chem.MolFromSmiles(smiles)
    keys = [ec.generalize(mol, g) for g in ec.ertl_groups(mol)]
    assert ec.si_key(pseudo) in keys


def test_the_observations_match_the_committed_mapping(observed):
    categories, outside = observed
    now = ec.as_mapping(categories, outside)
    committed = ec.committed()
    was = {
        "category": {k: {f: v[f] for f in ("features", "uncovered", "wider")}
                     for k, v in committed["category"].items()},
        "outside": {k: sorted(set(v["examples"]) | set(now["outside"].get(k, [])))
                    for k, v in committed.get("outside", {}).items()},
    }
    assert now["category"] == was["category"], (
        "Ertl categories or their v2 coverage changed: rerun "
        "`python tools/ertl_crosscheck.py --write` and review the diff"
    )
    assert set(now["outside"]) == set(was["outside"]), "the OpenChem-only features changed"


def test_every_gap_in_either_direction_is_justified():
    committed = ec.committed()
    unjustified = [k for k, v in committed["category"].items() if v["uncovered"] and not v.get("why")]
    assert not unjustified, f"Ertl categories v2 leaves uncovered with no reason: {unjustified}"
    stale = [k for k, v in committed["category"].items() if not v["uncovered"] and v.get("why")]
    assert not stale, f"a reason for a gap that no longer exists: {stale}"
    silent = [k for k, v in committed.get("outside", {}).items() if not v.get("why")]
    assert not silent, f"OpenChem-only features with no reason: {silent}"


@pytest.mark.parametrize("row", ec.si_representatives(), ids=lambda r: r["pseudo"])
def test_a_representative_still_regenerates_its_papers_category(row):
    """The SI-derived fixtures are only worth anything if each one IS an
    instance of the category it stands for, by Ertl's own rules."""
    mol = Chem.MolFromSmiles(row["smiles"])
    keys = [ec.generalize(mol, g) for g in ec.ertl_groups(mol)]
    assert ec.si_key(row["pseudo"]) in keys
