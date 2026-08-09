"""Offline guards on the RCSB assembly gate's own corpus.

The gate itself lives in `benchmarks/assembly/` and needs the network, so
it cannot run here. What CAN be guarded offline is the property that
makes it worth running: **the corpus has to contain a matrix whose
transpose is a different rotation.**

That is not a stylistic preference. Measured against the real gate, a
transposed builder produces byte-identical output for 4DKL, 4EA3 and
5I6X, and for all 49 receptors in the bundled catalogue, because every
one of their operator matrices is axis-aligned. Only 2OMF's 3-fold
catches it, and it misses by 118.5 A when it does. Drop that one entry
and the gate keeps passing while testing strictly less.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openchem.chem.structure_assembly import operator_transforms

_CORPUS = Path(__file__).resolve().parents[1] / "benchmarks" / "assembly" / "corpus.json"

#: 2OMF's REMARK 350, verbatim from the deposit, so the claim below is
#: checked against real data rather than against a flag somebody set.
#: Only operator 2 is needed -- 1 is the identity and 3 is its inverse.
_2OMF_REMARK_350 = (
    "REMARK 350 BIOMOLECULE: 1\n"
    "REMARK 350 APPLY THE FOLLOWING TO CHAINS: A\n"
    "REMARK 350   BIOMT1   1  1.000000  0.000000  0.000000        0.00000\n"
    "REMARK 350   BIOMT2   1  0.000000  1.000000  0.000000        0.00000\n"
    "REMARK 350   BIOMT3   1  0.000000  0.000000  1.000000        0.00000\n"
    "REMARK 350   BIOMT1   2 -0.500000 -0.866025  0.000000       59.25000\n"
    "REMARK 350   BIOMT2   2  0.866025 -0.500000  0.000000      102.62401\n"
    "REMARK 350   BIOMT3   2  0.000000  0.000000  1.000000        0.00000\n"
    "ATOM      1  N   ALA A   1       1.000   2.000   3.000  1.00 20.00           N\n"
    "END\n"
)


def _corpus() -> dict:
    return json.loads(_CORPUS.read_text(encoding="utf-8"))


def test_the_gate_corpus_declares_a_structure_that_catches_a_transpose():
    """Exactly the entry the mutation table depends on."""
    declared = [e for e in _corpus()["structures"] if e.get("catches_transpose")]
    assert declared, (
        "no corpus entry claims to catch a transposed matrix -- the gate can "
        "pass with the rotation transposed, which is what it exists to prevent"
    )


def test_the_declared_entry_really_has_a_non_symmetric_matrix():
    """The declaration is CHECKED, not trusted.

    A symmetric matrix equals its own transpose, so an entry that claimed
    this role while carrying one would leave the gate exactly as blind
    while looking guarded -- the failure mode this project records for
    `inapplicable_calculators`, whose blocklist rotted silently because
    nothing rederived it.
    """
    declared = [e for e in _corpus()["structures"] if e.get("catches_transpose")]
    assert [e["pdb_id"] for e in declared] == ["2OMF"], (
        "the bundled REMARK 350 fixture below is 2OMF's; a new entry needs its "
        "own, taken from the real deposit"
    )

    matrix = operator_transforms(_2OMF_REMARK_350, "pdb", "1")["2"].matrix
    off_diagonal = [
        (matrix[row][column], matrix[column][row])
        for row in range(3)
        for column in range(row + 1, 3)
    ]
    assert any(a != b for a, b in off_diagonal), (
        f"{matrix} is symmetric, so transposing it is a no-op and the gate "
        "cannot detect a transposed builder"
    )


def test_every_corpus_entry_says_why_it_is_there():
    """A gate corpus is a set of decisions, and an entry nobody can
    justify is one nobody will defend when it starts failing."""
    for entry in _corpus()["structures"]:
        assert entry.get("why", "").strip(), entry["pdb_id"]
        assert entry["expect"] in ("built", "refused"), entry["pdb_id"]


def test_the_refusal_entry_states_the_atom_count_it_refuses_on():
    """1A34's value is that RCSB confirms the number, so the number has to
    be written down where a drift would show."""
    refusals = [e for e in _corpus()["structures"] if e["expect"] == "refused"]
    assert refusals, "no refusal case: the size guard would be unchecked"
    for entry in refusals:
        assert isinstance(entry.get("expect_atoms"), int), entry["pdb_id"]


@pytest.mark.parametrize("script", ["fetch.py", "build.py", "score.py"])
def test_the_gate_scripts_are_present(script: str):
    """The README documents a three-script split; a missing one turns a
    documented command into a traceback."""
    assert (_CORPUS.parent / script).is_file()
