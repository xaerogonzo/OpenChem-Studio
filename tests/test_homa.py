"""HOMA must reproduce Krygowski's own numbers from a real geometry.

`[source:krygowski1993]`.

THE ORACLE IS ONE SENTENCE ON p73, AND IT IS A THREE-POINT ONE: "values for
benzene itself 0.969 for electron diffraction geometry, 0.979 for MW
geometry, and 0.996 for X-ray geometry". Each back-solves to a real benzene
C-C length, so a perfect hexagon at each length is an exact test of the
parameters AND the formula together -- a wrong R_opt or a wrong alpha misses
all three, and a formula error misses them differently.

Geometries are BUILT rather than embedded for those three, deliberately. An
MMFF conformer's bond lengths are the force field's, not the paper's, so a
test against an embedded benzene would be asserting what MMFF happens to
produce. Where a real conformer IS the point -- the refusals, the ring walk
-- the tests embed one and say so.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem import aromaticity
from openchem.chem.aromaticity import HomaRefusal

PARAMETERS = json.loads(
    (Path(aromaticity.__file__).parent / "data" / "homa_parameters.json").read_text(
        encoding="utf-8"
    )
)


def _planar_ring(smiles: str, bond_length: float) -> Chem.Mol:
    """A regular polygon of the given side, in the xy plane.

    The only way to test the parameters against a PRINTED value: the paper's
    benzene numbers are for specific experimental C-C lengths, and no force
    field reproduces those on request.
    """
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
# The paper's own benzene numbers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "geometry,bond_length,printed",
    [
        ("electron diffraction", 1.399, 0.969),
        ("microwave", 1.397, 0.979),
        ("X-ray", 1.392, 0.996),
    ],
)
def test_benzene_reproduces_the_papers_value(geometry, bond_length, printed):
    """p73, one sentence, three geometries.

    A three-point oracle from a single source is worth more than three
    scattered ones: the same parameters and the same formula have to hit all
    of them, and the spread across geometries is itself the point the
    limitation text makes.
    """
    result = aromaticity.compute_homa(_planar_ring("c1ccccc1", bond_length))

    assert result.applicable
    assert len(result.rings) == 1
    assert result.rings[0].value == pytest.approx(printed, abs=6e-4)


def test_the_three_benzene_values_really_do_differ():
    """The setup assertion: the oracle is three points, not one repeated.

    Without this, a HOMA that ignored bond length entirely would pass all
    three above if it happened to return 0.98.
    """
    values = [
        aromaticity.compute_homa(_planar_ring("c1ccccc1", length)).rings[0].value
        for length in (1.399, 1.397, 1.392)
    ]
    assert len(set(round(v, 3) for v in values)) == 3


# ---------------------------------------------------------------------------
# The parameter table
# ---------------------------------------------------------------------------

def test_r_opt_follows_the_papers_own_equation_6():
    """R_opt = (R_s + 2 R_d)/3, checked row by row.

    TWO ROWS ARE NAMED EXCEPTIONS, and they are the paper's inconsistency
    rather than a transcription error -- CO's printed R_opt is 1.265 where
    Eq. 6 gives 1.2670, and CS is 0.0007 out, which is rounding. The printed
    values ship because the printed alpha is consistent with them.
    """
    known = {"CO", "CS"}
    for name, row in PARAMETERS["bonds"].items():
        derived = (row["R_s"] + 2 * row["R_d"]) / 3
        if name in known:
            continue
        assert derived == pytest.approx(row["R_opt"], abs=5e-4), name

    assert "CO" in PARAMETERS["_internal_inconsistencies"]
    assert "1.2670" in PARAMETERS["_internal_inconsistencies"]["CO"]


def test_alpha_follows_the_papers_own_equation_7():
    """alpha = 2/((R_s - R_opt)^2 + (R_d - R_opt)^2), from the printed R_opt.

    EVERY ROW RECONCILES EXCEPT ONE, and that one is the row the paper's own
    footnote tells you not to use. That coincidence is the reason the
    deprecated set is excluded from the lookup rather than merely flagged.
    """
    failures = []
    for name, row in PARAMETERS["bonds"].items():
        derived = 2.0 / (
            (row["R_s"] - row["R_opt"]) ** 2 + (row["R_d"] - row["R_opt"]) ** 2
        )
        if abs(derived - row["alpha"]) > 0.05:
            failures.append(name)
    assert failures == ["CC_alt"], failures
    assert PARAMETERS["bonds"]["CC_alt"]["deprecated"] is True


def test_the_deprecated_parameter_set_is_unreachable():
    """Footnote i: 'it is recommended now to use parameters CCa'.

    Kept in the JSON for provenance and excluded from the lookup, because
    two rows claiming the same element pair would make the answer depend on
    dict ordering.
    """
    table = aromaticity._by_elements()
    carbon_carbon = table[frozenset({"C"})]

    assert carbon_carbon["name"] == "CC"
    assert carbon_carbon["R_opt"] == pytest.approx(1.388)
    assert carbon_carbon["alpha"] == pytest.approx(257.7)
    assert not any(row.get("deprecated") for row in table.values())


def test_every_shipped_row_says_where_it_came_from():
    """Source row identity, as `tsei_radii.json` keeps its printed symbol."""
    for name, row in PARAMETERS["bonds"].items():
        assert row["printed"], name
        assert row["reference"], name
        assert len(row["elements"]) == 2, name


# ---------------------------------------------------------------------------
# Rings, and what the index means
# ---------------------------------------------------------------------------

def test_a_heterocycle_mixes_bond_parameter_sets():
    """Eq. 8: each bond takes ITS OWN type's parameters, weighted equally.

    Pyridine is four CC bonds and two CN, and a single-parameter-set
    implementation would use CC for all six -- which produces a plausible
    number, not an error.
    """
    result = aromaticity.compute_homa(_embedded("c1ccncc1"))

    assert len(result.rings) == 1
    assert result.rings[0].bond_types == {"CC": 4, "CN": 2}
    assert result.rings[0].value > 0.9


def test_each_ring_is_reported_separately():
    """PER RING, because fusing changes local aromatic character.

    The paper's Figure 3 gives perylene's rings 0.448 to 0.952; one number
    for the molecule would average exactly that away.
    """
    result = aromaticity.compute_homa(_embedded("c1ccc2ccccc2c1"))

    assert len(result.rings) == 2
    for ring in result.rings:
        assert len(ring.atom_indices) == 6


def test_a_saturated_ring_goes_well_below_zero():
    """There is NO lower bound, and cyclohexane demonstrates it.

    0 is the reference Kekule structure, not a floor. A consumer clamping
    this at 0 would turn a strong statement into a meaningless one.
    """
    result = aromaticity.compute_homa(_embedded("C1CCCCC1"))

    assert result.rings[0].value < -1.0


def test_an_aromatic_ring_scores_far_above_a_saturated_one():
    """The discriminating claim, stated as a comparison rather than a bound."""
    aromatic = aromaticity.compute_homa(_embedded("c1ccccc1")).rings[0].value
    saturated = aromaticity.compute_homa(_embedded("C1CCCCC1")).rings[0].value

    assert aromatic > 0.9
    assert aromatic - saturated > 4.0


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------

def test_a_molecule_with_no_conformer_is_refused():
    """The load-bearing refusal.

    A 2D layout's bond lengths are not measurements -- every bond in one
    comes out about the same length whatever its order, so HOMA computed on
    a drawing reports near-perfect aromaticity for anything at all.
    """
    result = aromaticity.compute_homa(Chem.MolFromSmiles("c1ccccc1"))

    assert not result.applicable
    assert result.refusal is HomaRefusal.NO_CONFORMER


def test_a_two_dimensional_conformer_is_refused_too():
    """The narrow half: HAVING a conformer is not having a 3D one.

    `GetNumConformers() > 0` is true for any molecule built from a molblock,
    which this project already records as useless as a check.
    """
    mol = Chem.MolFromSmiles("c1ccccc1")
    AllChem.Compute2DCoords(mol)

    assert mol.GetNumConformers() == 1
    assert not mol.GetConformer().Is3D()

    result = aromaticity.compute_homa(mol)
    assert result.refusal is HomaRefusal.NO_CONFORMER
    assert "not measurements" in result.detail


def test_a_molecule_with_no_rings_is_refused():
    result = aromaticity.compute_homa(_embedded("CCO"))

    assert result.refusal is HomaRefusal.NO_RINGS


def test_a_ring_bond_with_no_parameters_refuses_that_ring_alone():
    """A silicon or boron ring has no HOMA parameters, and says so.

    Refused per RING rather than per molecule, so a parametrised ring in the
    same structure still gets its answer.
    """
    mol = _embedded("c1ccccc1[Si]1CCCC1", seed=11)
    result = aromaticity.compute_homa(mol)

    assert result.applicable
    refused = [r for r in result.rings if not r.applicable]
    answered = [r for r in result.rings if r.applicable]
    assert refused and answered, "the fixture must have one of each"
    assert refused[0].refusal is HomaRefusal.UNPARAMETRISED_BOND
    assert "Si" in refused[0].detail


def test_an_unreadable_structure_refuses_rather_than_raising():
    assert aromaticity.compute_homa(None).refusal is HomaRefusal.NOT_A_STRUCTURE


# ---------------------------------------------------------------------------
# The calculator
# ---------------------------------------------------------------------------

def test_the_calculator_runs_through_the_registry():
    """The registry hands a PARAMETER DICT, not a value.

    Written otherwise this passes every direct test and raises the moment the
    button is pressed -- measured on `hansen_solubility` one commit ago.
    """
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
    from openchem.domain.common import CacheState

    definition = next(
        d for d in CALCULATOR_DEFINITIONS if d.calculator_id == "homa_aromaticity"
    )
    result = definition.execution.compute(
        _embedded("c1ccncc1"), "uuid-1", {"decimal_places": 4}
    )

    assert result.cache_state is CacheState.COMPLETED
    assert len(result.facts) == 1
    assert result.facts[0].label == "6-membered C5N"
    assert len(result.facts[0].display_value.split(".")[1]) == 4


def test_the_calculator_declines_a_total():
    """Averaging rings erases the local character the index exists to show."""
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
    from openchem.domain.common import TOTAL

    definition = next(
        d for d in CALCULATOR_DEFINITIONS if d.calculator_id == "homa_aromaticity"
    )
    result = definition.execution.compute(_embedded("c1ccc2ccccc2c1"), "u", {})

    declaration = result.provenance.parameters[TOTAL]
    assert declaration["declared"] is False
    assert "PER RING" in declaration["reason"]


def test_a_fact_highlights_the_ring_it_is_about():
    """`highlight`, bounds-checked by consumers, is how the panel paints it."""
    from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS

    definition = next(
        d for d in CALCULATOR_DEFINITIONS if d.calculator_id == "homa_aromaticity"
    )
    mol = _embedded("c1ccccc1")
    result = definition.execution.compute(mol, "u", {})

    highlight = result.facts[0].highlight
    assert len(highlight) == 6
    assert max(highlight) < mol.GetNumAtoms(), "an out-of-range index crashes the viewer"
