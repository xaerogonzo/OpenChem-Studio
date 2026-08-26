"""Bird's aromaticity index, in three validation layers.

THE LAYERS ARE NAMED BECAUSE THE PROVENANCE IS NOT UNIFORM, and somebody
reading `citation_and_claim` on the source six months from now must not
conclude that Bird's own printed table was reproduced.

    Layer 1  MATHEMATICAL SELF-CONSISTENCY
             benzene -> 100 because the bond-order variance is zero; the
             0-100 scale is exactly linear in V through (0, 100) and
             (V_K, 0); Gordy's relation and the V_K constants are the
             paper's. Independent of any transcription fixture.

    Layer 2  A SAME-PAPER GEOMETRY-BACKED ORACLE
             `[source:katritzky1990]` tabulates experimental bond lengths
             (Tables 1-2) AND the Bird indices computed from them (Table 6,
             `Exp.` column) for the same compounds. Reproducing a row tests
             THIS implementation of Bird's formula against THEIRS, on a
             geometry both have.

    Layer 3  BIRD 1985 IS THE METHOD DEFINITION AND NOTHING MORE
             It prints indices (Table 2, Figure 1) and NO bond lengths --
             pages 4-6 contain none. Its printed values are therefore NOT
             reproducible from it, and are NOT claimed here.

The two papers disagree where they chose different geometries: Bird's
Table 2 gives pyrrole 59, Katritzky's Exp. column gives 69.3. That is the
whole reason the claim is scoped to Katritzky.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem import aromaticity
from openchem.chem.aromaticity import GeometricAromaticityRefusal

_DATA = Path(aromaticity.__file__).parent / "data"
PARAMETERS = json.loads((_DATA / "bird_parameters.json").read_text(encoding="utf-8"))
ORACLE = json.loads((_DATA / "bird_oracle.json").read_text(encoding="utf-8"))


def _cyclic_polygon(sides: list[float]) -> list[tuple[float, float, float]]:
    """Planar coordinates for a ring whose consecutive distances are `sides`.

    A cyclic polygon: every vertex on one circle of radius R, so side i
    subtends a central angle of `2*asin(s_i / 2R)` and R is the value making
    those angles sum to a full turn. One bisection, no dependencies.

    THIS EXISTS SO THE ORACLE GOES THROUGH THE SHIPPED CODE. The first
    version of this file computed Bird's index in the TEST from the tabulated
    lengths, which validated the test's own arithmetic -- a mutation removing
    the mean-normalisation from `ring_bird` survived the whole file. Building
    a real conformer makes `ring_bird` do the work.
    """
    lower = max(sides) / 2.0 + 1e-12

    def turn(radius: float) -> float:
        return sum(2.0 * math.asin(min(1.0, s / (2.0 * radius))) for s in sides)

    upper = lower
    while turn(upper) > 2.0 * math.pi:
        upper *= 2.0
    for _ in range(200):
        middle = (lower + upper) / 2.0
        if turn(middle) > 2.0 * math.pi:
            lower = middle
        else:
            upper = middle
    radius = (lower + upper) / 2.0

    points, angle = [], 0.0
    for side in sides:
        points.append((radius * math.cos(angle), radius * math.sin(angle), 0.0))
        angle += 2.0 * math.asin(min(1.0, side / (2.0 * radius)))
    return points


def _ring_at(smiles: str, bonds) -> Chem.Mol:
    """A molecule whose ring bonds have exactly the tabulated lengths.

    **THE RING MUST BE ALIGNED TO THE TABLE FIRST.** `AtomRings()` returns
    the cycle in an ARBITRARY rotation and direction, while Katritzky's
    columns run 1-2, 2-3, ... from the heteroatom. Zipping the two naively
    puts each length on the wrong bond -- measured, all five fixtures failed
    at once, which is the honest failure and not a near miss.

    So every rotation and both directions are tried, and the one whose
    element sequence matches the table's is used. A structure where none
    matches raises rather than silently taking rotation zero.
    """
    mol = Chem.MolFromSmiles(smiles)
    AllChem.Compute2DCoords(mol)
    ring = list(mol.GetRingInfo().AtomRings()[0])
    size = len(ring)
    assert size == len(bonds), f"{smiles}: ring of {size} against {len(bonds)} bonds"

    wanted = [(a, b) for a, b, _ in bonds]

    def pairs_for(order):
        return [
            (
                mol.GetAtomWithIdx(order[i]).GetSymbol(),
                mol.GetAtomWithIdx(order[(i + 1) % size]).GetSymbol(),
            )
            for i in range(size)
        ]

    aligned = None
    for candidate in [ring, ring[::-1]]:
        for shift in range(size):
            order = candidate[shift:] + candidate[:shift]
            got = pairs_for(order)
            if all(set(g) == set(w) for g, w in zip(got, wanted)):
                aligned = order
                break
        if aligned:
            break
    assert aligned is not None, f"{smiles}: no ring order matches {wanted}"

    conformer = mol.GetConformer()
    for index, point in zip(aligned, _cyclic_polygon([length for _, _, length in bonds])):
        conformer.SetAtomPosition(index, point)
    conformer.Set3D(True)
    return mol


def _planar_ring(smiles: str, bond_length: float) -> Chem.Mol:
    mol = Chem.MolFromSmiles(smiles)
    AllChem.Compute2DCoords(mol)
    conformer = mol.GetConformer()
    n = mol.GetNumAtoms()
    radius = bond_length / (2 * math.sin(math.pi / n))
    for index in range(n):
        angle = 2 * math.pi * index / n
        conformer.SetAtomPosition(
            index, (radius * math.cos(angle), radius * math.sin(angle), 0.0)
        )
    conformer.Set3D(True)
    return mol


def _embedded(smiles: str, seed: int = 7) -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=seed)
    AllChem.MMFFOptimizeMolecule(mol)
    return Chem.RemoveHs(mol)


# ---------------------------------------------------------------------------
# LAYER 1 -- mathematical self-consistency
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bond_length", [1.35, 1.397, 1.45])
def test_a_ring_with_equal_bonds_scores_exactly_100(bond_length):
    """V = 0 when every bond order is equal, so I = 100 whatever the length.

    THE INDEX IS INDIFFERENT TO HOW LONG THE BONDS ARE, only to how EQUAL
    they are -- which is precisely what separates it from HOMA, and why the
    three lengths here must all give 100 rather than a trend.
    """
    result = aromaticity.compute_bird(_planar_ring("c1ccccc1", bond_length))

    assert result.applicable
    assert result.rings[0].value == pytest.approx(100.0, abs=1e-9)
    assert result.rings[0].variation == pytest.approx(0.0, abs=1e-9)


def test_homa_disagrees_with_bird_on_the_same_rings():
    """The setup assertion for the claim above, and a real distinction.

    A ring at 1.45 A has perfectly equal bonds -- Bird 100 -- and sits far
    from HOMA's optimal 1.388, so HOMA scores it poorly. If the two indices
    ever agreed here, one of them would be computing the other's quantity.
    """
    stretched = _planar_ring("c1ccccc1", 1.45)

    assert aromaticity.compute_bird(stretched).rings[0].value == pytest.approx(100.0)
    assert aromaticity.compute_homa(stretched).rings[0].value < 0.5


def test_the_scale_is_linear_in_V_through_100_and_zero():
    """I = 100(1 - V/V_K): equal bonds give 100, and V = V_K would give 0.

    The localised-reference end is asserted through the RELATION rather than
    by building a Kekule geometry, because the paper states V_K without
    stating the bond lengths that produce it. Inventing a pair of lengths to
    hit V_K would be asserting against a geometry nobody published.
    """
    ring = aromaticity.compute_bird(_embedded("c1ccsc1")).rings[0]
    reference = aromaticity.kekule_reference(5)

    assert ring.value == pytest.approx(100.0 * (1.0 - ring.variation / reference))
    # ... and the relation really does send V = V_K to zero.
    assert 100.0 * (1.0 - reference / reference) == pytest.approx(0.0)


def test_gordys_relation_is_the_papers():
    """N = a/R^2 - b, hand-computable from Table 1."""
    a, b = PARAMETERS["bonds"]["C-C"]["a"], PARAMETERS["bonds"]["C-C"]["b"]
    assert (a, b) == (6.80, 1.71)
    assert aromaticity.bond_order(frozenset({"C"}), 1.397) == pytest.approx(
        6.80 / 1.397**2 - 1.71
    )
    # A shorter bond is a higher order, which is the relation's whole point.
    assert aromaticity.bond_order(frozenset({"C"}), 1.34) > aromaticity.bond_order(
        frozenset({"C"}), 1.45
    )


def test_the_kekule_references_are_the_papers_three():
    """35 for a five-ring, 33.3 for a six-ring, and nothing else published."""
    assert aromaticity.kekule_reference(5) == 35.0
    assert aromaticity.kekule_reference(6) == 33.3
    for size in (3, 4, 7, 8):
        assert aromaticity.kekule_reference(size) is None, size


def test_table_1_carries_every_bond_the_paper_prints():
    """13 bond types, and the one the text layer corrupted.

    `o-s 17.05 5.5a+` extracts with a LETTER where a digit belongs; the
    render says 5.58. Asserted by value so a re-transcription cannot quietly
    reintroduce it.
    """
    bonds = PARAMETERS["bonds"]
    assert len(bonds) == 13
    assert bonds["O-S"]["b"] == pytest.approx(5.58)
    for name, row in bonds.items():
        assert row["printed"], name
        assert row["source"] in {"*", "#", "+"}, name
        assert len(row["elements"]) == 2, name


# ---------------------------------------------------------------------------
# LAYER 2 -- the same-paper geometry-backed oracle
# ---------------------------------------------------------------------------

CASES = [(c["name"], c) for c in ORACLE["compounds"]]


@pytest.mark.parametrize("name,case", CASES, ids=[n for n, _ in CASES])
def test_katritzkys_experimental_index_reproduces(name, case):
    """Katritzky Tables 1-2 geometry in, Katritzky Table 6 `Exp.` value out.

    The reference tag is what confirms the pairing rather than row order:
    thiophene's geometry row is tagged `41b,m` and its index is `65.5(41b)m`.
    """
    mol = _ring_at(case["smiles"], case["bonds"])
    result = aromaticity.compute_bird(mol)

    assert result.applicable, aromaticity.refusal_text(result.refusal, result.detail)
    computed = result.rings[0].value
    assert computed == pytest.approx(case["index"]["Exp"], abs=0.2), (
        f"{name}: {computed:.2f} against a printed {case['index']['Exp']}"
    )


def test_the_oracle_reads_the_EXPERIMENTAL_column_and_not_another():
    """TABLE 6 HAS FIVE COLUMNS AND ONLY ONE IS AN EXPERIMENTAL GEOMETRY.

    `Exp.`, MNDO, AM1, MINDO/3 and 3-21G all sit side by side, and the
    optimised ones are plausible numbers that would validate nothing about
    this implementation -- they were computed from geometries this project
    does not have. A fixture accidentally keyed on AM1 would still look
    like a passing test.

    This asserts the columns are far enough apart to tell: if `Exp.` and
    AM1 ever agreed for every compound, the test above could not
    distinguish them and would be worth less than it appears.
    """
    disagreements = 0
    for _, case in CASES:
        expected = case["index"]["Exp"]
        for column, value in case["index"].items():
            if column == "Exp":
                continue
            if abs(value - expected) > 0.2:
                disagreements += 1
    assert disagreements >= 12, (
        "the non-experimental columns must differ from Exp., or the oracle "
        "cannot show which one it read"
    )

    # And the AM1 column really would fail the fixture above.
    thiophene = next(c for _, c in CASES if c["name"] == "thiophene")
    computed = aromaticity.compute_bird(
        _ring_at(thiophene["smiles"], thiophene["bonds"])
    ).rings[0].value
    assert abs(computed - thiophene["index"]["AM1"]) > 10


def test_the_oracle_covers_both_ring_sizes_and_several_bond_types():
    """The setup assertion, so the fixture set cannot quietly narrow."""
    sizes = {len(c["bonds"]) for _, c in CASES}
    assert sizes == {5, 6}

    pairs = {
        frozenset((a, b)) for _, c in CASES for a, b, _ in c["bonds"]
    }
    assert len(pairs) >= 5, pairs
    assert frozenset({"C"}) in pairs and frozenset({"N"}) in pairs


# ---------------------------------------------------------------------------
# LAYER 3 -- what is NOT claimed
# ---------------------------------------------------------------------------

def test_the_data_says_bird_1985s_own_values_are_not_reproduced():
    """Recorded in the shipped data, not only in a commit message.

    Bird 1985 prints indices and no bond lengths, so none of its values is
    reproducible from it. Somebody reading `citation_and_claim` on
    [source:katritzky1990] must not conclude Bird's table was reproduced.
    """
    note = PARAMETERS["_what_is_NOT_claimed"]
    assert "NO bond lengths" in note
    assert "katritzky1990" in note

    scope = ORACLE["_what_this_oracle_IS_NOT"]
    assert "pyrrole 59" in scope and "69.3" in scope


def test_the_two_papers_really_do_disagree_on_pyrrole():
    """The setup assertion for the scoping above.

    If Bird's 59 and Katritzky's 69.3 were the same number, the distinction
    the source entries draw would be pedantry rather than necessity.
    """
    pyrrole = next(c for _, c in CASES if c["name"] == "pyrrole")
    assert pyrrole["index"]["Exp"] == 69.3
    assert abs(69.3 - 59) > 10


# ---------------------------------------------------------------------------
# The subscript, the rings, and the refusals
# ---------------------------------------------------------------------------

def test_a_ring_carries_its_size_subscript():
    """p1411's own requirement, not a formatting choice.

    "It seems desirable to attach a guiding subscript as I5, I6 or I5,6, to
    discourage inappropriate comparisons." It matters more here than it
    would elsewhere: HOMA sits in the same panel section and DOES share one
    scale across ring sizes.
    """
    five = aromaticity.compute_bird(_embedded("c1ccsc1")).rings[0]
    six = aromaticity.compute_bird(_embedded("c1ccccc1")).rings[0]

    assert five.subscript == "I5"
    assert six.subscript == "I6"


def test_an_unsupported_ring_size_is_refused_rather_than_scaled():
    """A seven-membered ring has no published V_K, and none is invented."""
    result = aromaticity.compute_bird(_embedded("C1=CC=CC=CC1"))

    assert result.applicable
    ring = result.rings[0]
    assert not ring.applicable
    assert ring.refusal is GeometricAromaticityRefusal.UNSUPPORTED_RING_SIZE
    assert "5 and 6" in ring.detail


def test_a_bond_with_no_gordy_constants_refuses_that_ring():
    mol = _embedded("c1ccccc1[Si]1CCCC1", seed=11)
    result = aromaticity.compute_bird(mol)

    refused = [r for r in result.rings if not r.applicable]
    answered = [r for r in result.rings if r.applicable]
    assert refused and answered, "the fixture must have one of each"
    assert refused[0].refusal is GeometricAromaticityRefusal.UNPARAMETRISED_BOND


def test_bird_refuses_a_drawing_exactly_as_homa_does():
    """Both read real bond lengths, and both go through one shared gate."""
    flat = Chem.MolFromSmiles("c1ccccc1")
    AllChem.Compute2DCoords(flat)

    for result in (aromaticity.compute_bird(flat), aromaticity.compute_homa(flat)):
        assert result.refusal is GeometricAromaticityRefusal.NO_CONFORMER
        assert "not measurements" in result.detail

    assert aromaticity.compute_bird(None).refusal is (
        GeometricAromaticityRefusal.NOT_A_STRUCTURE
    )


def test_the_refusal_enum_is_shared_and_the_old_name_still_resolves():
    """One enum, because every reason is a property of the QUESTION.

    `HomaRefusal` is kept as an alias the way `AtomFact = Fact` was, so
    nothing importing the old name breaks.
    """
    assert aromaticity.HomaRefusal is GeometricAromaticityRefusal
    assert GeometricAromaticityRefusal.UNSUPPORTED_RING_SIZE.value


# ---------------------------------------------------------------------------
# The calculator
# ---------------------------------------------------------------------------

def _definition():
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    return next(
        d for d in CALCULATOR_DEFINITIONS if d.calculator_id == "bird_aromaticity"
    )


def test_the_calculator_runs_through_the_registry():
    from openchem.domain.common import CacheState

    result = _definition().execution.compute(
        _embedded("c1ccsc1"), "uuid-1", {"decimal_places": 2}
    )

    assert result.cache_state is CacheState.COMPLETED
    assert len(result.facts) == 1
    assert result.facts[0].label.startswith("I5 - ")
    assert len(result.facts[0].display_value.split(".")[1]) == 2


def test_the_label_carries_the_subscript_where_a_reader_sees_it():
    """Not only in provenance. The panel renders the LABEL.

    This project has twice shipped a result whose provenance was right while
    the screen showed two different things as one.
    """
    result = _definition().execution.compute(_embedded("c1ccc2ccccc2c1"), "u", {})

    assert len(result.facts) == 2
    for fact in result.facts:
        assert fact.label.startswith("I6 - ")
        assert any("not comparable" in limit.lower() for limit in fact.limitations)


def test_the_calculator_declines_a_total():
    from openchem.domain.common import TOTAL

    result = _definition().execution.compute(_embedded("c1ccsc1"), "u", {})
    declaration = result.provenance.parameters[TOTAL]

    assert declaration["declared"] is False
    assert "not necessarily comparable" in declaration["reason"]
