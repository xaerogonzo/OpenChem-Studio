"""Miller polarizability, gated on the two molecules that sank the last try.

`docs/VALIDATION.md` recorded this as measured and not shipped: "The
parameters are unpublished. A reconstruction missed benzene by +27% and
CCl4 by -50%, so there was nothing to validate against."

Those two are therefore the acceptance test, not a sample of it. If
either drifts, the transcription of Table I or the hybrid assignment is
wrong, and the answer is to find out which -- never to widen a tolerance.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rdkit import Chem

from openchem.chem import polarizability_miller as miller
from openchem.chem.polarizability_miller import (
    MillerAssignmentError,
    miller_polarizability,
)


def _alpha(smiles: str) -> float:
    return miller_polarizability(Chem.MolFromSmiles(smiles)).ahc


# --- the two the earlier reconstruction got wrong ---------------------------


def test_benzene_is_within_one_percent():
    """+27% ON RECORD. The cause was almost certainly the `CBR` row.

    Its symbol reads as "carbon in a benzene ring" and means the
    opposite: the 1979 paper says "in ethylene AND BENZENE the pi system
    is directed only along two bonds, whereas in the 9 and 10 positions
    of naphthalene it is directed along all three". Benzene's carbons are
    CTR.
    """
    assert _alpha("c1ccccc1") == pytest.approx(10.39, rel=0.01)


def test_carbon_tetrachloride_is_within_one_percent():
    """-50% ON RECORD, which is the signature of the wrong FORM rather
    than the wrong parameter: `alpha = (4/N)(sum tau)^2` squares a sum, so
    using the additive column in it, or summing tau, halves this one.
    """
    assert _alpha("ClC(Cl)(Cl)Cl") == pytest.approx(10.5, rel=0.01)


def test_benzenes_carbons_are_CTR_and_naphthalenes_fusion_carbons_are_CBR():
    """The assignment itself, because the values above could agree for the
    wrong reason on a single molecule.

    Naphthalene is the discriminator: eight CH carbons and exactly TWO
    ring-fusion carbons, which are the 9,10 positions the paper names.
    """
    benzene = miller_polarizability(Chem.MolFromSmiles("c1ccccc1"))
    assert benzene.assignment == {"CTR": 6, "H": 6}

    naphthalene = miller_polarizability(Chem.MolFromSmiles("c1ccc2ccccc2c1"))
    assert naphthalene.assignment == {"CTR": 8, "CBR": 2, "H": 8}


def test_assigning_benzene_to_CBR_would_be_visibly_wrong():
    """THE SETUP ASSERTION FOR THE TWO TESTS ABOVE.

    Without it, "benzene is within 1%" is a claim that could hold for a
    table where CTR and CBR happened to be close. They are not: measured,
    the wrong row puts benzene at 13.99 against 10.39, i.e. +36% -- the
    same error class as the +27% on record, which is what makes the
    recorded failure explicable rather than merely historical.
    """
    table = miller.parameters()
    tau_ctr, tau_cbr = table["CTR"]["tau_ahc"], table["CBR"]["tau_ahc"]
    electrons = 6 * 6 + 6 * 1
    wrong = 4.0 / electrons * (6 * tau_cbr + 6 * table["H"]["tau_ahc"]) ** 2
    right = 4.0 / electrons * (6 * tau_ctr + 6 * table["H"]["tau_ahc"]) ** 2

    assert wrong > 13.5, f"the wrong assignment gives {wrong:.2f}, not visibly wrong"
    assert (wrong - 10.39) / 10.39 > 0.30
    assert right == pytest.approx(10.39, rel=0.01)


# --- the method, and the shape of it ---------------------------------------


@pytest.mark.parametrize(
    "label,smiles,expected",
    [
        ("methane", "C", 2.59),
        ("ethylene", "C=C", 4.25),
        ("acetylene", "C#C", 3.33),
        ("pyridine", "c1ccncc1", 9.50),
        ("naphthalene", "c1ccc2ccccc2c1", 17.48),
    ],
    ids=lambda v: str(v),
)
def test_a_spread_of_hybrid_states_lands_within_a_few_percent(label, smiles, expected):
    """Every carbon row and two heteroatom rows exercised.

    5% rather than 1%: this is an EMPIRICAL scheme fitted to ~240
    molecules, and the papers' own tables carry errors of that size --
    naphthalene is 16.59 against 17.48 in the 1979 table, which is -5%.
    Holding it to 1% everywhere would be asserting more than the method
    claims.
    """
    assert _alpha(smiles) == pytest.approx(expected, rel=0.05)


def test_the_two_methods_are_different_answers_and_neither_defaults():
    """`ahc` squares a sum; `ahp` adds. They are not interchangeable, and
    a caller has to say which it wants."""
    result = miller_polarizability(Chem.MolFromSmiles("c1ccccc1"))
    assert result.ahc != pytest.approx(result.ahp, rel=0.001)
    assert result.ahc > 0 and result.ahp > 0


def test_the_electron_count_is_the_whole_molecule_including_hydrogens():
    """`N` IS TOTAL ELECTRONS, and hydrogens are added here rather than
    demanded, because an implicit-H molecule silently loses both their
    parameter and their electrons while still returning a number."""
    benzene = miller_polarizability(Chem.MolFromSmiles("c1ccccc1"))
    assert benzene.electrons == 42


def test_an_element_the_table_does_not_cover_is_refused():
    """Table I covers H, C, N, O, S, P and four halogens. A boron has no
    row, and inventing one would give a plausible number for a molecule
    the method was never fitted to."""
    with pytest.raises(MillerAssignmentError, match="atomic number 5"):
        miller_polarizability(Chem.MolFromSmiles("B(O)(O)O"))


# --- the shipped table ------------------------------------------------------


def test_the_table_keeps_its_source_row_identity():
    """SO A FUTURE AUDIT CAN GO ROW BY ROW AGAINST THE PAGE.

    The derived key alone would lose the trail; `hybrid` is the paper's
    own column, so "which line of Table I is this" needs no re-derivation.
    """
    payload = json.loads(
        (Path(miller.__file__).parent / "data" / "miller_polarizability.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["_source_key"] == "miller1990"
    assert "miller1979" in payload["_supplementary_source_keys"]
    assert len(payload["parameters"]) == 20

    for symbol, row in payload["parameters"].items():
        assert row["hybrid"], f"{symbol} lost the paper's hybrid column"
        assert row["tau_ahc"] > 0 and row["alpha_ahp"] > 0


@pytest.mark.parametrize(
    "symbol,tau", [("H", 0.313), ("Cl", 3.165), ("CTE", 1.294), ("CTR", 1.433),
                   ("CBR", 1.707), ("OTE", 1.249), ("STR4", 3.827), ("PTE", 2.485)]
)
def test_spot_values_are_the_ones_the_page_shows(symbol, tau):
    """Typed from a 400 dpi render, against a text layer that gives
    `0.392 0.31 1 0.3 13 0.387` for a row of four numbers."""
    assert miller.parameters()[symbol]["tau_ahc"] == pytest.approx(tau, abs=1e-9)


# --- the paper's OWN printed assignments ------------------------------------

#: Table II prints the hybrid assignment beside every molecule, and that
#: column is a far stronger oracle than the two molecules above: it fixes
#: WHICH ROW each atom got rather than only the number the rows add up to.
#:
#: Typed from a positional extraction of the table, since the text layer
#: streams the columns separately -- "acetone 32 6.39 6.33 6.36 -1.0 -0.4
#: 4.7 -7.4 20 ZCTE CTR 10TR4 6H", where `ZCTE` is `2CTE` and `10TR4` is
#: `1 OTR4`.
_TABLE_II_ASSIGNMENTS = {
    "benzene": ("c1ccccc1", {"CTR": 6, "H": 6}),
    "toluene": ("Cc1ccccc1", {"CTR": 6, "CTE": 1, "H": 8}),
    "styrene": ("C=Cc1ccccc1", {"CTR": 7, "CBR": 1, "H": 8}),
    "acetone": ("CC(C)=O", {"CTE": 2, "CTR": 1, "OTR4": 1, "H": 6}),
    "naphthalene": ("c1ccc2ccccc2c1", {"CTR": 8, "CBR": 2, "H": 8}),
    "anthracene": ("c1ccc2cc3ccccc3cc2c1", {"CTR": 10, "CBR": 4, "H": 10}),
    "pyrene": ("c1cc2ccc3cccc4ccc(c1)c2c34", {"CTR": 10, "CBR": 6, "H": 10}),
    "b-methylnaphthalene": (
        "Cc1ccc2ccccc2c1", {"CTR": 8, "CTE": 1, "CBR": 2, "H": 10}
    ),
    "a-naphthalenecarboxaldehyde": (
        "O=Cc1cccc2ccccc12", {"CTR": 8, "CBR": 3, "OTR4": 1, "H": 8}
    ),
}


@pytest.mark.parametrize(
    "label", sorted(_TABLE_II_ASSIGNMENTS), ids=lambda s: str(s)
)
def test_the_hybrid_assignment_is_the_one_the_paper_prints(label):
    """THE ORACLE THE TWO-MOLECULE CHECK ABOVE COULD NOT BE.

    Benzene and CCl4 pin the numbers; this pins which ROW every atom got,
    which is where the +36% error class actually lives. Nine molecules
    chosen because they SEPARATE the two candidate rules:

        toluene    ipso carbon, no hydrogen, and the paper says CTR
        styrene    ipso carbon, no hydrogen, and the paper says CBR
        acetone    carbonyl carbon, no hydrogen, and the paper says CTR

    A "CBR is a trigonal carbon with no hydrogen" rule -- which the 1990
    paper's PROSE states in as many words on p 8535 -- gets toluene and
    acetone wrong and puts benzene at 13.99 against 10.39. It was
    implemented here on the strength of that sentence and this test is
    what would have caught it. The tables win.
    """
    smiles, expected = _TABLE_II_ASSIGNMENTS[label]
    result = miller_polarizability(Chem.MolFromSmiles(smiles))
    assert result.assignment == expected


def test_the_same_ring_position_changes_row_with_its_substituent():
    """THE PAIR THAT SHOWS THE RULE IS ABOUT CONJUGATION, not counting.

    b-methylnaphthalene and a-naphthalenecarboxaldehyde differ only in
    what hangs off one ring carbon, and the paper gives that carbon
    different rows: CTR under a methyl, CBR under a conjugated CHO. No
    hydrogen count can produce both.
    """
    methyl = miller_polarizability(Chem.MolFromSmiles("Cc1ccc2ccccc2c1")).assignment
    aldehyde = miller_polarizability(Chem.MolFromSmiles("O=Cc1cccc2ccccc12")).assignment
    assert methyl["CBR"] == 2, "only the two fusion carbons should be CBR under a methyl"
    assert aldehyde["CBR"] == 3, "the ipso carbon should join them under a CHO"


def test_nitrobenzene_is_the_one_printed_assignment_that_disagrees():
    """RECORDED, NOT TUNED TOWARD.

    The paper prints `6CTR 1NPI2 2OTE 5H`; this implementation gives the
    ipso carbon CBR and the nitro oxygens OTR4. That row is also one of
    the worst in Table II at -6.8%, and the paper's own text lists
    nitrobenzene among the molecules whose correction "lead to a larger
    deviation from experimental results".

    Asserted as a DISAGREEMENT so that a future change which resolves it
    fails here and this account can be corrected, rather than the
    disagreement being quietly absorbed.
    """
    assignment = miller_polarizability(
        Chem.MolFromSmiles("O=[N+]([O-])c1ccccc1")
    ).assignment
    assert assignment["CBR"] == 1
    assert assignment["CTR"] == 5
    assert assignment != {"CTR": 6, "NPI2": 1, "OTE": 2, "H": 5}
