"""Tests for phosphanyl-sulfanyl ether prefix bracketing fix.

When a P-containing fragment (like di(methoxy)(oxo)phosphanyl) is named as
a substituent via an S or O bridge, the compound substituent name must be
enclosed in square brackets before the bridge suffix to prevent OPSIN from
misinterpreting the S/O as the central atom.

Correct:   [di(methoxy)(oxo)phosphanyl]sulfanyl
Incorrect: di(methoxy)(oxo)phosphanylsulfanyl  (OPSIN reads S as centre)

See: Cluster 6 of the triage (ZT-2532, ZT-2264, ZT-2644, ZT-2425).
"""
from __future__ import annotations

import pytest

from openchem.vendor.iupac_namer.engine import name_smiles


# ---------------------------------------------------------------------------
# Phosphorus ester compounds — compound substituent bracketing (Cluster 6)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "smiles,expected_fragment",
    [
        # THE INPUTS HERE CHANGED IN NAMING ROUND 3, NOT THE RULE THEY TEST.
        #
        # The subject is BRACKETING: a P-containing compound substituent must
        # be enclosed before the `sulfanyl` bridge or OPSIN reads the S as the
        # centre. That needs a molecule where P really is a SUBSTITUENT, and
        # the three original inputs no longer are: with the plan-budget fix
        # the phosphorus parent is finally proposed, and P-44.1.2 prefers it
        # over the carbocycle (BlueBookV2.pdf p. 375 -- carbon is last in the
        # element order, and the criterion explicitly chooses between rings
        # and chains). `CCOP(=S)(CC)Sc1ccccc1` is now
        # `(ethoxy)(ethyl)(phenylsulfanyl)(thioxo)phosphane`, which has no
        # phosphanyl substituent to bracket. It still round-trips on both
        # gates; see the `_unchanged` test below.
        #
        # The replacements carry a principal characteristic group -- an amide,
        # an amine, a carboxylic acid -- so the carbon chain is the parent by
        # P-44.1.1, which outranks the senior-atom criterion. That makes the
        # phosphanyl substituent appear deliberately rather than incidentally,
        # and it exercises two steps of the cascade instead of one. The
        # amide row below was already here and already said so.
        ("NCCSP(=O)(OC)OC", "[di(methoxy)(oxo)phosphanyl]sulfanyl"),
        ("OC(=O)CSP(=O)(OC)OC", "[di(methoxy)(oxo)phosphanyl]sulfanyl"),
        # ZT-2264: O,O-dimethyl S-R phosphorothioate ester
        # P is substituent of the amide chain (amide PCG wins)
        ("CNC(=O)CSP(=O)(OC)OC", "[di(methoxy)(oxo)phosphanyl]sulfanyl"),
        # ZT-2644: O,O-diethyl S-CH2-S-Ar phosphorothioate
        ("CCOP(=O)(OCC)SCC(=O)NC", "[di(ethoxy)(oxo)phosphanyl]sulfanyl"),
    ],
)
def test_phosphanyl_sulfanyl_bracketing(smiles, expected_fragment):
    """P-containing substituent names must be enclosed in [...] before sulfanyl."""
    result = name_smiles(smiles)
    assert expected_fragment in result, (
        f"Expected '{expected_fragment}' in name of {smiles!r}, got: {result!r}"
    )


@pytest.mark.parametrize(
    "smiles,expected",
    [
        ("CCOP(=S)(CC)Sc1ccccc1",
         "(ethoxy)(ethyl)(phenylsulfanyl)(thioxo)phosphane"),
        ("CCOP(=O)(OCC)SCSc1ccc(Cl)cc1",
         "({[(4-chlorophenyl)sulfanyl]methyl}sulfanyl)di(ethoxy)(oxo)phosphane"),
        ("COP(=S)(OC)SCSc1ccc(Cl)cc1",
         "({[(4-chlorophenyl)sulfanyl]methyl}sulfanyl)di(methoxy)(thioxo)phosphane"),
    ],
)
def test_the_three_original_inputs_now_take_phosphorus_as_parent(smiles, expected):
    """The three molecules moved out of the bracketing table above, kept here
    so the change is recorded rather than deleted.

    With no principal characteristic group to hold the parent on carbon,
    P-44.1.2 puts it on the phosphorus. Every one of these round-trips to its
    input on canonical SMILES and full InChIKey (checked 2026-09-17), so the
    bracketing hazard these used to guard cannot arise for them: there is no
    phosphanyl substituent left to bracket.
    """
    assert name_smiles(smiles) == expected


@pytest.mark.parametrize(
    "smiles,not_expected_fragment",
    [
        # Must NOT generate the unbracketed form that OPSIN misparses
        ("CCOP(=S)(CC)Sc1ccccc1", "phosphanylsulfanyl"),
        ("CNC(=O)CSP(=O)(OC)OC", "phosphanylsulfanyl"),
        ("CCOP(=O)(OCC)SCSc1ccc(Cl)cc1", "phosphanylsulfanyl"),
        ("COP(=S)(OC)SCSc1ccc(Cl)cc1", "phosphanylsulfanyl"),
    ],
)
def test_phosphanyl_sulfanyl_no_unbracketed(smiles, not_expected_fragment):
    """Unbracketed phosphanylsulfanyl must not appear in output."""
    result = name_smiles(smiles)
    assert not_expected_fragment not in result, (
        f"Found '{not_expected_fragment}' in name of {smiles!r}: {result!r}"
    )


# ---------------------------------------------------------------------------
# Non-regression: simple phosphane cases must still work
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "smiles,expected",
    [
        # Simple S-alkyl: no brackets needed (methylsulfanyl, ethylsulfanyl).
        # These carry a thio (S-alkyl) substituent, so they are NOT pure
        # O-organyl oxoacid esters and remain substitutive phosphane names.
        ("COP(=O)(OC)SC", "di(methoxy)(methylsulfanyl)(oxo)phosphane"),
        ("CCOP(=O)(OCC)SCC", "di(ethoxy)(ethylsulfanyl)(oxo)phosphane"),
    ],
)
def test_simple_phosphane_names_unchanged(smiles, expected):
    """Mixed thio/O phosphane esters keep the substitutive phosphane name."""
    assert name_smiles(smiles) == expected


@pytest.mark.parametrize(
    "smiles,expected",
    [
        # Full O-organyl phosphate triesters are PINs by functional-class
        # ester nomenclature (P-65.6.3 / P-67.1.3.2), NOT the substitutive
        # "tri(methoxy)(oxo)phosphane" form, which merely round-trips.
        ("COP(=O)(OC)OC", "trimethyl phosphate"),
        ("CCOP(=O)(OCC)OCC", "triethyl phosphate"),
    ],
)
def test_full_phosphate_triesters_are_pins(smiles, expected):
    """Fully O-esterified phosphoric acid -> trialkyl phosphate (P-67.1.3.2)."""
    assert name_smiles(smiles) == expected


# ---------------------------------------------------------------------------
# Non-regression: ring-yloxy must NOT get extra brackets
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "smiles,expected_fragment",
    [
        # Ring O-ether: (pyridin-4-yl)oxy, never [pyridin-4-yl]oxy.
        # P-16.5.1.3 (BlueBookV2 pdf p. 130): a simple prefix qualified by locants is enclosed -- '(pyridin-2-yl)oxy', '(propan-2-yl)oxy' (naming round 4)
        # Use a chain-PCG context (carboxylic acid / amine) so pyridine is
        # unambiguously a SUBSTITUENT.  (The previous oxane+pyridine context
        # made the parent-vs-substituent choice ambiguous: per P-44.1.2 the
        # nitrogen heterocycle outranks the oxygen heterocycle, so pyridine
        # is now correctly the parent in those — which defeated this test's
        # intent of probing the ring-yloxy substituent connector.)
        ("OC(=O)CCOc1ccncc1", "(pyridin-4-yl)oxy"),
        ("NCCOc1ccncc1", "(pyridin-4-yl)oxy"),
    ],
)
def test_ring_yloxy_not_bracketed(smiles, expected_fragment):
    """Ring yloxy names must NOT gain extra brackets from the compound-name check."""
    result = name_smiles(smiles)
    assert expected_fragment in result, (
        f"Expected '{expected_fragment}' in name of {smiles!r}, got: {result!r}"
    )
    # Must not produce [pyridin-4-yl]oxy
    assert "[pyridin-4-yl]oxy" not in result, (
        f"Got unwanted bracketed form in: {result!r}"
    )
