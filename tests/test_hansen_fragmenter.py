"""The Hansen fragmenter must reproduce Stefanis & Panayiotou from a SMILES.

`[source:stefanis2008]`. Where `test_hansen_table.py` gates the transcribed
numbers, this gates the chemistry: which groups a structure decomposes into,
and therefore which contributions get summed.

THE PAPER SUPPLIES TWO KINDS OF ORACLE AND BOTH ARE USED HERE:

    two worked examples   1-hexanal at W=0 and alizarin at W=1, each printing
                          its group assignment AND its totals
    76 example compounds  every row of Table 3 names a compound and the
                          number of times that group occurs in it

The second is the stronger of the two for a FRAGMENTER, because it exercises
one group at a time against a structure the authors chose for it. A wrong
priority order shows up as a count, not as a shifted total.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem import hansen
from openchem.chem.hansen import HansenRefusal, ParameterBasis as Basis


def _fragment(smiles: str):
    return hansen.fragment(Chem.MolFromSmiles(smiles))


# ---------------------------------------------------------------------------
# The two worked examples, end to end from a SMILES
# ---------------------------------------------------------------------------

HEXANAL = "CCCCCC=O"
ALIZARIN = "O=C1c2ccccc2C(=O)c2c1ccc(O)c2O"


def test_1_hexanal_decomposes_as_the_paper_does():
    """Tables 7-9: 1 CH3 + 4 CH2 + 1 CHO, and no second-order group.

    **THIS CAUGHT A REAL BUG.** Written the obvious way, `CH2CO` -- the
    ketone group -- also matches the carbon alpha to an ALDEHYDE, because an
    aldehyde carbonyl is a CX3 too. 1-hexanal came out 1 CH3 + 3 CH2 + 1
    CH2CO, and its three parameters were wrong by 1.08, 0.56 and 0.29: a
    plausible answer for the wrong decomposition, which no range check would
    have flagged.
    """
    f = _fragment(HEXANAL)

    assert f.applicable, hansen.refusal_text(f)
    assert f.first == {
        hansen._key("-CH3"): 1,
        hansen._key("-CH2"): 4,
        hansen._key("CHO (aldehydes)"): 1,
    }
    assert f.second == {}
    assert f.w == 0


@pytest.mark.parametrize(
    "parameter,printed", [("d", 15.8411), ("p", 7.9654), ("hb", 5.7191)]
)
def test_1_hexanal_reproduces_the_printed_parameters(parameter, printed):
    value = hansen.parameter_value(_fragment(HEXANAL), parameter)
    assert value.basis is Basis.MAIN
    assert value.value == pytest.approx(printed, abs=5e-4)


def test_alizarin_decomposes_as_the_paper_does():
    """Tables 11-16, and the only W=1 example the paper prints."""
    f = _fragment(ALIZARIN)

    assert f.applicable, hansen.refusal_text(f)
    assert f.first == {
        hansen._key("ACH"): 6,
        hansen._key("AC"): 4,
        hansen._key("ACOH"): 2,
        hansen._key(">C=O (except as above)"): 2,
    }
    assert f.second == {hansen._key("Ccyclic=O"): 2}
    assert f.w == 1


def test_alizarin_reproduces_the_printed_second_order_parameter():
    """delta_hb = 22.02, the paper's own figure with the correction applied."""
    assert hansen.parameter(_fragment(ALIZARIN), "hb") == pytest.approx(22.02, abs=5e-3)


# ---------------------------------------------------------------------------
# Table 3's own example compounds, one per group
# ---------------------------------------------------------------------------

#: (group, compound, SMILES, occurrences) -- the compound and the count are
#: the paper's, from Table 3's "Examples (Occurrences)" column. The SMILES are
#: ours, and every one is a compound simple enough to write without looking it
#: up, which is deliberate: a mistyped structure here would read as a
#: fragmenter bug. This project has a fixture on record whose values were
#: typed from memory under a label claiming otherwise.
EXAMPLES = [
    ("-CH3", "propane", "CCC", 2),
    ("-CH2", "butane", "CCCC", 2),
    ("-CH<", "isobutane", "CC(C)C", 1),
    (">C<", "neopentane", "CC(C)(C)C", 1),
    ("CH2=CH-", "propylene", "C=CC", 1),
    ("-CH=CH-", "cis-2-butene", r"C/C=C\C", 1),
    ("CH2=C<", "isobutene", "CC(C)=C", 1),
    ("-CH=C<", "2-methyl-2-butene", "CC=C(C)C", 1),
    (">C=C<", "2,3-dimethyl-2-butene", "CC(C)=C(C)C", 1),
    ("CH≡C-", "propyne", "C#CC", 1),
    ("C≡C", "2-butyne", "CC#CC", 1),
    ("ACH", "benzene", "c1ccccc1", 6),
    ("AC", "naphthalene", "c1ccc2ccccc2c1", 2),
    ("ACCH3", "toluene", "Cc1ccccc1", 1),
    ("CH3CO", "methyl ethyl ketone", "CCC(C)=O", 1),
    ("CH2CO", "cyclopentanone", "O=C1CCCC1", 1),
    ("CHO (aldehydes)", "1-butanal", "CCCC=O", 1),
    ("COOH", "acrylic acid", "C=CC(=O)O", 1),
    ("CH3COO", "ethyl acetate", "CCOC(C)=O", 1),
    ("OH", "isopropanol", "CC(C)O", 1),
    ("ACOH", "phenol", "Oc1ccccc1", 1),
    ("CH3O", "methyl ethyl ether", "CCOC", 1),
    ("CHNH2", "isopropylamine", "CC(C)N", 1),
    ("ACNH2", "aniline", "Nc1ccccc1", 1),
    ("I", "isopropyl iodide", "CC(C)I", 1),
    ("Br", "2-bromopropane", "CC(C)Br", 1),
    ("CH2Cl", "n-butyl chloride", "CCCCCl", 1),
    ("CHCl", "isopropyl chloride", "CC(C)Cl", 1),
    ("CCl", "t-butyl chloride", "CC(C)(C)Cl", 1),
    ("ACCl", "m-dichlorobenzene", "Clc1cccc(Cl)c1", 2),
    ("ACF", "fluorobenzene", "Fc1ccccc1", 1),
    ("ACNO2", "nitrobenzene", "O=[N+]([O-])c1ccccc1", 1),
    ("CH2NO2", "1-nitropropane", "CCC[N+](=O)[O-]", 1),
    ("CHNO2", "2-nitropropane", "CC(C)[N+](=O)[O-]", 1),
    ("CH2CN", "n-butyronitrile", "CCCC#N", 1),
]


@pytest.mark.parametrize(
    "group,compound,smiles,occurrences",
    EXAMPLES,
    ids=[f"{g}-{c}" for g, c, _, _ in EXAMPLES],
)
def test_each_group_occurs_as_often_as_the_paper_says(
    group, compound, smiles, occurrences
):
    """One group at a time, against the compound the authors chose for it.

    A wrong PRIORITY ORDER shows up here as a count rather than as a shifted
    total, which is what makes this sharper than the two worked examples for
    testing a fragmenter.
    """
    f = _fragment(smiles)
    assert f.applicable, f"{compound}: {hansen.refusal_text(f)}"
    assert f.first.get(hansen._key(group), 0) == occurrences, (
        f"{compound} decomposed as {dict(sorted(f.first.items()))}"
    )


def test_the_example_set_covers_a_real_share_of_the_table():
    """The setup assertion, so the parametrised list cannot quietly shrink."""
    assert len(EXAMPLES) >= 35
    covered = {hansen._key(g) for g, _, _, _ in EXAMPLES}
    assert len(covered) == len(EXAMPLES), "a group is tested twice"
    assert covered <= set(hansen.first_order_groups())


# ---------------------------------------------------------------------------
# The two passes, and why they cannot share a rule
# ---------------------------------------------------------------------------

def test_every_table_group_is_expressible(monkeypatch):
    """Full coverage, asserted so it can only be lost deliberately.

    A missing FIRST-ORDER group is fail-closed: the molecule needing it hits
    UNCOVERED_ATOM and is refused. A missing SECOND-ORDER group is NOT --
    corrections do not claim, so an unexpressed one silently fails to apply
    and the answer comes back plausible and uncorrected. That asymmetry is
    why this asserts both halves at 100% rather than recording a debt.
    """
    first = {g for g, _, _ in hansen._FIRST_ORDER_SPEC}
    second = {g for g, _, _ in hansen._SECOND_ORDER_SPEC}
    assert first == set(hansen.first_order_groups())
    assert second == set(hansen.second_order_groups())


def test_a_second_order_group_overlaps_the_first_order_ones():
    """Principle (ii): a second-order group is BUILT FROM first-order groups.

    Alizarin's `Ccyclic=O` is the same two carbonyls the first pass already
    claimed as `>C=O`. If the correction pass claimed atoms, or skipped
    matches touching claimed atoms, it would find nothing here -- and would
    raise nothing, returning a plausible uncorrected number.
    """
    f = _fragment(ALIZARIN)

    assert f.second[hansen._key("Ccyclic=O")] == 2
    assert f.first[hansen._key(">C=O (except as above)")] == 2
    # The setup: those really are the same atoms, so this is an overlap
    # rather than two disjoint findings.
    mol = Chem.MolFromSmiles(ALIZARIN)
    carbonyls = mol.GetSubstructMatches(Chem.MolFromSmarts("[CX3]=[OX1]"))
    assert len(carbonyls) == 2


def test_w_is_a_switch_and_not_a_tier():
    """Eq. 23: 0 for a compound with no second-order groups, 1 for one with.

    A first-order-only answer is the METHOD, not a degraded fallback, so
    1-hexanal is a complete result at W=0 rather than a partial one.
    """
    assert _fragment(HEXANAL).w == 0
    assert _fragment(ALIZARIN).w == 1
    assert _fragment(HEXANAL).applicable
    assert hansen.parameter(_fragment(HEXANAL), "d") is not None


# ---------------------------------------------------------------------------
# The low-range branch
# ---------------------------------------------------------------------------

def test_a_low_polar_parameter_comes_from_the_low_range_tables():
    """n-hexane's delta_p falls under 3, so Eq. 27 and Table 5 apply.

    The basis is part of the RESULT rather than only the provenance: a
    main-table number and a low-range number come from different regressions
    and must not render as one kind of thing.
    """
    value = hansen.parameter_value(_fragment("CCCCCC"), "p")

    assert value.basis is Basis.LOW
    assert value.value == pytest.approx(0.737, abs=5e-3)


def test_the_low_range_branch_uses_its_own_intercepts():
    """EQS. 27 AND 28, WHICH ARE EASY TO MISS AND WERE MISSED.

    The paper gives them in a sentence between two figures rather than beside
    Tables 5 and 6, so a first implementation of this branch used the group
    contributions with NO intercept and put n-hexane's delta_p at -2.009 -- a
    negative solubility parameter, which is impossible. Reusing Eq. 25's
    7.3548 is the other wrong answer: it gives 5.35, above the very threshold
    that selected this branch, so the result would contradict its own reason
    for existing.
    """
    low = hansen._table()["_low_delta"]["constants"]
    assert low["p"] == pytest.approx(2.7467)
    assert low["hb"] == pytest.approx(1.3720)
    assert low["p"] != hansen.constants()["p"]
    assert low["hb"] != hansen.constants()["hb"]

    value = hansen.parameter_value(_fragment("CCCCCC"), "p").value
    assert value > 0, "a solubility parameter cannot be negative"
    assert value < hansen.LOW_DELTA_THRESHOLD, (
        "the low branch must not return a value above the threshold that "
        "selected it"
    )


def test_the_dispersion_parameter_has_no_low_range_branch():
    """Eq. 24 carries no validity caveat, and Tables 5/6 hold no delta_d."""
    assert "d" not in hansen.LOW_DELTA_PARAMETERS
    for row in hansen._table()["first_order_low"].values():
        assert "d" not in row


def test_a_main_range_value_says_so():
    """The control: the basis is not simply LOW everywhere."""
    assert hansen.parameter_value(_fragment(HEXANAL), "p").basis is Basis.MAIN
    assert hansen.parameter_value(_fragment(HEXANAL), "hb").basis is Basis.MAIN


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "smiles,expected",
    [
        ("CC", HansenRefusal.TOO_FEW_CARBONS),
        ("C", HansenRefusal.TOO_FEW_CARBONS),
        ("CCC.CCC", HansenRefusal.NOT_A_PURE_COMPONENT),
        ("CCC[O-]", HansenRefusal.CHARGED),
    ],
)
def test_a_structure_outside_the_model_is_refused(smiles, expected):
    f = _fragment(smiles)
    assert not f.applicable
    assert f.refusal is expected


def test_the_carbon_floor_is_the_papers_own():
    """p574: three or more carbons. A LIMIT, so a refusal rather than a note."""
    assert hansen.MINIMUM_CARBONS == 3
    assert _fragment("CCC").applicable
    assert not _fragment("CC").applicable


def test_an_unreadable_structure_refuses_rather_than_raising():
    assert hansen.fragment(None).refusal is HansenRefusal.NOT_A_STRUCTURE


def test_a_refusal_carries_a_reason_a_reader_can_act_on():
    text = hansen.refusal_text(_fragment("CC"))
    assert "three or more carbons" in text
    assert "2 carbon" in text


# ---------------------------------------------------------------------------
# The total
# ---------------------------------------------------------------------------

def test_the_total_is_the_pythagorean_combination_not_a_sum():
    """Eq. 4. A plain sum is the obvious wrong implementation and is larger."""
    f = _fragment(HEXANAL)
    parts = [hansen.parameter(f, which) for which in hansen.PARAMETERS]

    total = hansen.total_parameter(f)
    assert total == pytest.approx((sum(p * p for p in parts)) ** 0.5, abs=1e-9)
    assert total < sum(parts), "a plain sum would be larger, and is wrong"


def test_a_refused_structure_has_no_total():
    assert hansen.total_parameter(_fragment("CC")) is None


# ---------------------------------------------------------------------------
# The three guards the mutation pass asked for
# ---------------------------------------------------------------------------

#: Cyclohexane-1,2-diol. FOUR second-order groups apply and they OVERLAP EACH
#: OTHER -- both hydroxyls are matched by `>CHOH` and by `Ccyclic-OH`, and the
#: pair together by `-C(OH)C(OH)-`.
OVERLAPPING = "OC1CCCCC1O"


def test_second_order_groups_may_overlap_EACH_OTHER():
    """THE CASE ALIZARIN CANNOT TEST, and the mutation pass found the gap.

    Alizarin has one second-order group type, appearing twice at disjoint
    sites, so counting it and claim-and-skipping it give the SAME answer --
    a mutation swapping the rules survived every test in this file.

    Here they differ catastrophically: four corrections become one, silently,
    with no atom uncovered and no refusal raised. That is the exact failure
    the two-pass design exists to prevent, and it needed a fixture where
    second-order groups overlap ONE ANOTHER rather than merely overlapping
    the first-order pass.
    """
    from openchem.chem.group_contribution import claim_groups, count_overlapping

    mol = Chem.MolFromSmiles(OVERLAPPING)
    patterns = hansen._second_order_patterns()

    counted = count_overlapping(mol, patterns)
    claimed = claim_groups(mol, patterns).counts

    assert len(counted) == 4, dict(sorted(counted.items()))
    assert len(claimed) == 1, "the fixture no longer discriminates the two rules"
    assert counted != claimed


def test_the_fragmenter_uses_the_counting_rule_for_corrections():
    """The end-to-end half: the shipped path keeps all four corrections."""
    f = _fragment(OVERLAPPING)

    assert f.applicable, hansen.refusal_text(f)
    assert f.w == 1
    assert set(f.second) == {
        hansen._key("-C(OH)C(OH)-"),
        hansen._key(">CHOH"),
        hansen._key("Ccyclic-OH"),
        hansen._key("ring of 6 carbons"),
    }
    assert f.second[hansen._key(">CHOH")] == 2


def test_the_atom_count_invariant_refuses_a_mismatched_pattern():
    """ASSERTED ON THE PREDICATE, because it is unreachable through the spec.

    Every shipped SMARTS agrees with its declared atom count, so a mutation
    deleting the check changes nothing measurable and survives the whole
    file -- measured. This project's rule is that an unreachable branch is a
    question about WHERE to assert, not automatically dead code, and this one
    caught three bugs in Joback, two of which produced wrong answers.
    """
    from openchem.chem.group_contribution import build_patterns

    good = (("g", "[CX4H3]", "a methyl"),)
    assert len(build_patterns(good, {"g"}, {"g": 1}, "test")) == 1

    with pytest.raises(ValueError, match="would claim an atom belonging"):
        build_patterns(good, {"g"}, {"g": 2}, "test")

    with pytest.raises(ValueError, match="not in the shipped table"):
        build_patterns(good, set(), {"g": 1}, "test")

    with pytest.raises(ValueError, match="unparseable"):
        build_patterns((("g", "[[[", "nonsense"),), {"g"}, {"g": 1}, "test")


def test_the_aldehyde_is_protected_twice_and_either_alone_suffices():
    """TWO REDUNDANT GUARDS, recorded because mutation made it look untested.

    The ketone/aldehyde collision is prevented both by ordering `CHO
    (aldehydes)` ahead of the ketone groups AND by requiring H0 on their
    carbonyl. Reverting EITHER alone leaves 1-hexanal correct, so each
    mutation survives on its own and the pair reads as untested code.

    It is not untested -- it is defended twice -- and this asserts both
    halves directly so neither can be removed on the grounds that nothing
    noticed.
    """
    ids = [group for group, _, _ in hansen._FIRST_ORDER_SPEC]
    aldehyde = ids.index(hansen._key("CHO (aldehydes)"))
    for ketone in ("CH3CO", "CH2CO"):
        assert aldehyde < ids.index(hansen._key(ketone)), (
            "the aldehyde must be claimed before the ketone groups"
        )

    for ketone in ("CH3CO", "CH2CO"):
        smarts = next(s for g, s, _ in hansen._FIRST_ORDER_SPEC
                      if g == hansen._key(ketone))
        assert "CX3H0" in smarts, (
            f"{ketone}'s carbonyl must exclude an aldehyde's hydrogen"
        )


def test_the_calculator_runs_THROUGH_THE_REGISTRY():
    """THE INTEGRATION HALF, and a direct-import test cannot stand in for it.

    `RegistryExecution` calls `compute(mol, uuid, parameters_dict)`. Written
    with a `decimal_places: int` third argument instead, this module passed
    all 62 of its own tests -- they use the default -- and raised
    `TypeError: int() argument ... not 'dict'` the moment the button was
    pressed in the running app.

    This project already records the same class: a direct-import test passing
    while the registration bound to a shadowed two-argument function. The
    registry is the surface a user reaches, so it is the surface to assert.
    """
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
    from openchem.domain.common import CacheState

    definition = next(
        d for d in CALCULATOR_DEFINITIONS if d.calculator_id == "hansen_solubility"
    )
    result = definition.execution.compute(
        Chem.MolFromSmiles("CCOC(C)=O"), "uuid-1", {"decimal_places": 3}
    )

    assert result.cache_state is CacheState.COMPLETED
    assert result.category == "solubility"
    labels = {f.label for f in result.facts}
    assert "Dispersion (delta-d)" in labels
    assert "Total (Hildebrand, delta-t)" in labels

    # The parameter really is honoured, or the dict is being ignored rather
    # than read -- which is the same bug wearing a different shape.
    delta_d = next(f for f in result.facts if f.label == "Dispersion (delta-d)")
    assert delta_d.display_value == "15.785"


def test_the_registry_refusal_path_also_works():
    """A refused structure must come back FAILED, not raise."""
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
    from openchem.domain.common import CacheState

    definition = next(
        d for d in CALCULATOR_DEFINITIONS if d.calculator_id == "hansen_solubility"
    )
    result = definition.execution.compute(Chem.MolFromSmiles("CC"), "uuid-1", {})

    assert result.cache_state is CacheState.FAILED
    assert "three or more carbons" in result.error
