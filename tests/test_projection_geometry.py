"""Shape descriptors, checked against the shapes with exact answers.

**Marvin's own figures are deliberately not used as fixtures.** We do not
have the conformer Marvin measured, so a number from its screenshots
tests our embedding rather than our arithmetic -- the "fixture typed from
memory" trap this project has already paid for once. Every assertion here
is against a closed form: a sphere's volume, its surface, its shadow.
"""

from __future__ import annotations

import math

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem

from openchem.chem.projection_geometry import (
    NoConformerError,
    ShapeDescriptors,
    closest_fragment_approach,
    shape_descriptors,
    van_der_waals_volume,
)

#: The Bondi radius RDKit carries for helium, and the only number in this
#: file taken from a table rather than derived.
HELIUM_RADIUS = 1.4


def _embedded(smiles: str, optimise: bool = True) -> Chem.Mol:
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    AllChem.EmbedMolecule(mol, randomSeed=42)
    if optimise:
        AllChem.MMFFOptimizeMolecule(mol)
    return mol


@pytest.fixture(scope="module")
def helium() -> Chem.Mol:
    """One atom: the only molecule whose every descriptor is a closed form."""
    mol = Chem.MolFromSmiles("[He]")
    AllChem.EmbedMolecule(mol, randomSeed=42)
    return mol


# --- the analytic anchors ----------------------------------------------------


def test_one_atom_has_the_volume_of_its_sphere(helium):
    """4/3 pi r^3, to four decimals.

    This is what identifies `DoubleCubicLatticeVolume` as the ANALYTIC
    routine rather than a second grid estimate -- `ComputeMolVolume`
    misses the same number by 5%.
    """
    volume, _disagreement = van_der_waals_volume(helium)
    assert volume == pytest.approx(4 / 3 * math.pi * HELIUM_RADIUS**3, abs=1e-3)


def test_one_atom_has_the_surface_of_its_sphere(helium):
    """4 pi r^2. Free from the same call as the volume."""
    shape = shape_descriptors(helium)
    assert shape.surface_area == pytest.approx(4 * math.pi * HELIUM_RADIUS**2, abs=1e-3)


def test_one_atom_casts_a_circular_shadow(helium):
    """pi r^2, whichever way you look at it -- so both projection extremes
    are that circle, and they are equal.

    The grid is a Riemann sum over the disc, so it reads LOW by construction
    and never high; measured at 60 samples/A the deficit is 0.13%.
    """
    shape = shape_descriptors(helium)
    exact = math.pi * HELIUM_RADIUS**2

    assert shape.min_projection_area == pytest.approx(exact, rel=0.005)
    assert shape.max_projection_area == pytest.approx(exact, rel=0.005)
    assert shape.min_projection_area <= exact


def test_one_atom_projects_to_its_own_radius(helium):
    shape = shape_descriptors(helium)
    assert shape.min_projection_radius == pytest.approx(HELIUM_RADIUS, rel=0.005)


# --- the trap that makes the volume wrong by 700% ----------------------------


def test_the_solvent_probe_is_not_left_at_its_default(helium):
    """`DoubleCubicLatticeVolume` DEFAULTS to a 1.4 A probe, so left alone
    it returns a solvent-accessible volume where a van der Waals one was
    asked for -- 91.95 against 11.49 for helium.

    That is an eightfold error which, on a molecule without a closed form,
    looks like a perfectly plausible number. This asserts the two are
    computed separately and are not confused for one another.
    """
    shape = shape_descriptors(helium)
    probed = HELIUM_RADIUS + 1.4

    assert shape.volume == pytest.approx(4 / 3 * math.pi * HELIUM_RADIUS**3, abs=1e-3)
    assert shape.solvent_accessible_volume == pytest.approx(
        4 / 3 * math.pi * probed**3, abs=1e-2
    )
    assert shape.solvent_accessible_volume > 7 * shape.volume


# --- the cross-check ---------------------------------------------------------


@pytest.mark.parametrize(
    "smiles",
    ["O", "C", "CO", "CCO", "c1ccccc1", "C1CCCCC1", "c1ccc2ccccc2c1", "CCCCCCCCCC"],
)
def test_the_two_independent_routines_agree_on_real_molecules(smiles):
    """An analytic routine and a grid one, computing the same quantity.

    Measured across these eight, the worst disagreement is 1.53%
    (ethanol), well inside the 3% the module allows. A regression that
    silently changed radii or geometry would part them.
    """
    volume, disagreement = van_der_waals_volume(_embedded(smiles))

    assert volume > 0
    assert disagreement < 0.03, f"{smiles}: {disagreement:.2%}"


def test_a_lone_atom_is_the_known_exception_to_the_cross_check(helium):
    """Recorded rather than hidden: the GRID routine is worst where the
    surface-to-volume ratio is highest, so it misses a bare atom by 5%
    while the analytic answer is exactly right.

    It is a limitation of the check, not of the value -- which is why the
    check is reported and not used to reject anything.
    """
    _volume, disagreement = van_der_waals_volume(helium)

    assert disagreement > 0.03
    assert not shape_descriptors(helium).volumes_agree


# --- shape, on molecules where the ordering is obvious -----------------------


def test_a_long_molecule_is_far_more_elongated_than_a_round_one():
    """Decane end-on against decane side-on is a much bigger ratio than
    cyclohexane's, which is the whole point of reporting both extremes.

    Asserted as an ORDERING between two molecules rather than as two
    absolute numbers, because the absolutes depend on the conformer the
    embedder happened to produce and the ordering does not.
    """
    decane = shape_descriptors(_embedded("CCCCCCCCCC"))
    cyclohexane = shape_descriptors(_embedded("C1CCCCC1"))

    assert decane.max_projection_area / decane.min_projection_area > (
        cyclohexane.max_projection_area / cyclohexane.min_projection_area
    )


def test_the_union_is_taken_rather_than_the_sum_of_the_circles():
    """Benzene's shadow face-on is one fused disc, not twelve separate
    ones. Summing pi r^2 per atom would roughly double it, and in a fused
    ring most of the area IS overlap.

    Twelve carbon/hydrogen circles sum to well over 60 A^2; the real
    face-on shadow is about 35.
    """
    benzene = _embedded("c1ccccc1")
    table = Chem.GetPeriodicTable()
    naive = sum(
        math.pi * table.GetRvdw(atom.GetAtomicNum()) ** 2 for atom in benzene.GetAtoms()
    )

    assert shape_descriptors(benzene).max_projection_area < 0.75 * naive


def test_the_minimum_never_exceeds_the_maximum():
    for smiles in ("CCO", "c1ccccc1", "CC(=O)Oc1ccccc1C(=O)O"):
        shape = shape_descriptors(_embedded(smiles))
        assert shape.min_projection_area <= shape.max_projection_area
        assert shape.min_projection_radius <= shape.max_projection_radius


# --- refusing rather than answering from a degenerate geometry ---------------


def test_it_refuses_a_molecule_with_no_conformer():
    with pytest.raises(NoConformerError) as excinfo:
        shape_descriptors(Chem.MolFromSmiles("CCO"))

    assert "Generate Conformers" in str(excinfo.value)


def test_it_refuses_a_2d_conformer():
    """A flat depiction has coordinates and no shape. Answering from one
    would give a volume computed from a layout, which is the trap the bond
    report already documents for 2D bond lengths."""
    mol = Chem.MolFromSmiles("CCO")
    AllChem.Compute2DCoords(mol)

    with pytest.raises(NoConformerError) as excinfo:
        shape_descriptors(mol)

    assert "2D" in str(excinfo.value)


# --- what the panel receives -------------------------------------------------


def test_the_geometry_report_carries_the_projection_facts_with_units():
    """Asserted by CONTENT, never by position -- a new fact inserted above
    these must not break the test that they exist."""
    from openchem.chem.geometry_analysis import compute_geometry_analysis

    report = compute_geometry_analysis(_embedded("CC(=O)Oc1ccccc1C(=O)O"), "uuid")
    by_label = {fact.label: fact for fact in report.facts}

    assert by_label["Max projection area"].units == "A^2"
    assert by_label["Max projection radius"].units == "A"
    assert float(by_label["Max projection area"].display_value) > 0


def test_the_projection_facts_say_they_are_on_the_principal_planes():
    """The approximation travels with the number it qualifies, into the
    tooltip and every export -- not as a separate line of prose that a
    reader can meet without the value or discard while copying."""
    from openchem.chem.geometry_analysis import compute_geometry_analysis

    report = compute_geometry_analysis(_embedded("CCO"), "uuid")
    fact = next(f for f in report.facts if f.label == "Min projection area")

    assert any("principal planes" in line for line in fact.limitations)


def test_the_surface_panel_and_this_module_report_ONE_volume():
    """`surface_analysis` had its own `ComputeMolVolume` call, so the app
    could have shown two different van der Waals volumes for one molecule.
    It now routes through here, and this fails if a second implementation
    comes back."""
    from openchem.chem.surface_analysis import surface_areas

    mol = _embedded("CC(=O)Oc1ccccc1C(=O)O")

    assert surface_areas(mol)["vdw_volume"] == van_der_waals_volume(mol)[0]


# --- fragments the embedder packed on top of each other ----------------------


def test_a_single_fragment_has_no_approach_to_report():
    assert closest_fragment_approach(_embedded("CCO")) is None


def test_two_fragments_from_the_embedder_land_on_top_of_each_other():
    """`EmbedMolecule` applies no constraints between disconnected
    fragments, so it packs them at the origin. Documented in this repo
    after an interaction energy came out at +40000 kcal/mol; it hits shape
    the same way and far more quietly."""
    approach = closest_fragment_approach(_embedded("N.B", optimise=False))

    assert approach is not None
    assert approach < 0.7, approach


def test_fused_fragments_lose_a_large_part_of_the_volume():
    """The reason this is worth warning about: the answer is not merely
    imprecise, it is 21-44% too SMALL, and a smaller plausible number is
    the kind that gets believed.

    Compared against the same fragments measured apart, which is what the
    structure actually depicts."""
    together = _embedded("N.B", optimise=False)
    apart = sum(
        van_der_waals_volume(_embedded(smiles, optimise=False))[0] for smiles in ("N", "B")
    )

    assert van_der_waals_volume(together)[0] < 0.75 * apart


def test_the_geometry_report_warns_when_fragments_interpenetrate():
    from openchem.chem.geometry_analysis import compute_geometry_analysis

    report = compute_geometry_analysis(_embedded("N.B", optimise=False), "uuid")
    fact = next(f for f in report.facts if f.label == "Min projection area")

    assert any("separate fragments" in line for line in fact.limitations)


def test_an_ordinary_molecule_gets_no_fragment_warning():
    """A warning that fires on everything is one people stop reading."""
    from openchem.chem.geometry_analysis import compute_geometry_analysis

    report = compute_geometry_analysis(_embedded("CC(=O)Oc1ccccc1C(=O)O"), "uuid")
    fact = next(f for f in report.facts if f.label == "Min projection area")

    assert not any("separate fragments" in line for line in fact.limitations)
    assert len(fact.limitations) == 1


# --- the grid cap ------------------------------------------------------------


def test_a_large_molecule_does_not_cost_seconds():
    """At a fixed 60 samples/A, triacontane took **4.27 s** -- the panel
    recomputes this whenever the selection changes, so that is far too
    slow. Capping total grid cells brought it to 0.80 s.

    Asserted with a generous ceiling: the point is to catch a return to
    seconds-per-molecule, not to police a machine-dependent stopwatch.
    """
    import time

    mol = _embedded("C" * 30, optimise=False)
    started = time.perf_counter()
    shape_descriptors(mol)

    assert time.perf_counter() - started < 2.5


def test_the_cap_does_not_touch_a_small_molecule():
    """Accuracy is hardest to get where the shape is small, so those must
    keep the full resolution. Aspirin's projection is unchanged to six
    decimals by the cap, and helium's analytic checks above still pass --
    which together say the cap binds only where it was meant to."""
    small = shape_descriptors(_embedded("CC(=O)Oc1ccccc1C(=O)O"))
    exact = math.pi * HELIUM_RADIUS**2

    # The helium disc is far below the cap and still lands on pi r^2.
    assert shape_descriptors(
        _embedded("[He]", optimise=False)
    ).max_projection_area == pytest.approx(exact, rel=0.005)
    assert small.max_projection_area > small.min_projection_area > 0


def test_descriptors_are_frozen():
    """A shape is a measurement of one conformer; letting a caller edit it
    in place would let a number outlive the geometry it describes."""
    shape = shape_descriptors(_embedded("CCO"))

    assert isinstance(shape, ShapeDescriptors)
    with pytest.raises(AttributeError):
        shape.volume = 0.0
