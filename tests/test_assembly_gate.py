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


#: 1A34's `_pdbx_struct_oper_list` row for X0, verbatim, so the claim
#: below is checked against the deposit rather than against a flag.
_1A34_X0 = (
    "loop_\n"
    "_pdbx_struct_oper_list.id\n"
    "_pdbx_struct_oper_list.type\n"
    "_pdbx_struct_oper_list.name\n"
    "_pdbx_struct_oper_list.symmetry_operation\n"
    "_pdbx_struct_oper_list.matrix[1][1]\n"
    "_pdbx_struct_oper_list.matrix[1][2]\n"
    "_pdbx_struct_oper_list.matrix[1][3]\n"
    "_pdbx_struct_oper_list.vector[1]\n"
    "_pdbx_struct_oper_list.matrix[2][1]\n"
    "_pdbx_struct_oper_list.matrix[2][2]\n"
    "_pdbx_struct_oper_list.matrix[2][3]\n"
    "_pdbx_struct_oper_list.vector[2]\n"
    "_pdbx_struct_oper_list.matrix[3][1]\n"
    "_pdbx_struct_oper_list.matrix[3][2]\n"
    "_pdbx_struct_oper_list.matrix[3][3]\n"
    "_pdbx_struct_oper_list.vector[3]\n"
    "X0 'identity operation' 1_555 x,y,z "
    "1.00000000 0.00000000 0.00000000 0.00000 "
    "0.00000000 1.00000000 0.00000000 0.00000 "
    "0.00000000 0.00000000 1.00000000 0.00000\n"
    "#\n"
)


#: Outer operator of each declared product expression, keyed by
#: `(pdb_id, operator id)`. A new product entry has to add its own row
#: here, which is the point: the composition-order claim is then DERIVED
#: from the deposit's own matrix instead of read off a flag.
_OUTER_OPERATOR_FIXTURES = {("1A34", "X0"): _1A34_X0}


def test_the_gate_corpus_contains_a_product_expression():
    """`(A)(B)` is an mmCIF-only construct -- `REMARK 350` enumerates
    operators and has no expression syntax at all -- so without an entry
    that uses one, nothing external exercises product expansion."""
    declared = [e for e in _corpus()["structures"] if e.get("has_product_expression")]
    assert declared, "no corpus entry uses a product expression"
    for entry in declared:
        assert ")(" in entry["has_product_expression"], entry
        assert entry.get("source_formats") == ["mmcif"], (
            f"{entry['pdb_id']} claims a product expression but is not restricted to "
            "mmCIF; REMARK 350 cannot state one"
        )


def test_the_composition_order_GAP_is_declared_and_justified():
    """**The gap is recorded because it is real, and the reason is CHECKED.**

    Measured through the gate: `build.py --mutate reverse-composition`
    passes every entry, because the only product expression reachable
    against RCSB coordinates has the IDENTITY as its outer group, and
    composing the identity with anything is order-independent. Every
    product whose outer group is non-identity (1M4X assembly 7, 1AL0
    assembly 6, 1NOV assembly 6) lives in an assembly RCSB does not
    pre-generate, and the one that is served -- 1M4X assembly 1
    `(1-60)(61-88)` -- is 16,284,240 atoms.

    A corpus that merely FAILED to cover this would look the same as one
    that had decided not to. The declaration plus this check is what
    tells them apart, and it fails loudly if somebody claims the coverage
    without changing the corpus.
    """
    from openchem.chem.structure_assembly import operator_transforms

    declared = [e for e in _corpus()["structures"] if e.get("has_product_expression")]
    for entry in declared:
        assert "catches_composition_order" in entry, entry["pdb_id"]
        outer = entry["has_product_expression"].split(")(")[0].lstrip("(")
        evidence = _OUTER_OPERATOR_FIXTURES.get((entry["pdb_id"], outer))
        assert evidence is not None, (
            f"{entry['pdb_id']}'s outer group {outer!r} has no bundled "
            f"_pdbx_struct_oper_list fixture, so its composition-order claim cannot "
            f"be checked. Add one, verbatim from the deposit."
        )
        identity = operator_transforms(evidence, "mmcif")[outer].is_identity
        # DERIVED, never trusted. Composing the identity with anything is
        # order-independent, so an entry whose outer group is the identity
        # CANNOT catch a reversed composition however the flag is set --
        # and flipping the flag to claim coverage the corpus does not have
        # is exactly the rot this check exists to stop.
        assert entry["catches_composition_order"] == (not identity), (
            f"{entry['pdb_id']} declares catches_composition_order="
            f"{entry['catches_composition_order']} but its outer group {outer!r} "
            f"{'IS' if identity else 'is NOT'} the identity"
        )
        if not entry["catches_composition_order"]:
            assert entry.get("why_not_composition_order", "").strip(), entry["pdb_id"]


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
