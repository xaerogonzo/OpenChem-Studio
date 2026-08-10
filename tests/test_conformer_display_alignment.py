"""Conformers are put in a common frame for display, and nothing else changes.

`EmbedMolecule` leaves every conformer in its own arbitrary frame, so
stepping between them in the 3D viewer changes the orientation as much as
the shape. Reported as: *"It is extremely difficult to compare different
conformers. I arranged the first conformer in 1 row, then in the second
conformer I moved it a certain way, then moved back to the first conformer,
and it was once again in a different way."*

**The tests here are invariants, and each names a way to be plausibly
wrong.** A rigid superposition that is subtly a reflection, or that is
applied relative to an already-transformed frame, or that quietly changes a
bond length, all produce output that looks entirely correct.
"""

from __future__ import annotations

import itertools
import math

import pytest
from rdkit import Chem
from rdkit.Chem import AllChem, rdMolTransforms

from openchem.chem.alignment import align_conformers_for_display

#: Flexible enough to have genuinely different conformers.
HEXANOL = "CCCCCCO"
#: A rotatable methyl, for the no-jump case.
TOLUENE = "Cc1ccccc1"
#: Highly symmetric, where a least-squares fit is closest to degenerate.
CUBANE = "C12C3C4C1C1C4C3C21"


def _conformers(smiles: str, count: int = 4, seed: int = 0xC0FFEE) -> list[str]:
    """Real embedded conformers, each in its own arbitrary frame."""
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    params = AllChem.ETKDGv3()
    params.randomSeed = seed
    AllChem.EmbedMultipleConfs(mol, numConfs=count, params=params)
    AllChem.MMFFOptimizeMoleculeConfs(mol)
    return [Chem.MolToMolBlock(mol, confId=c.GetId()) for c in mol.GetConformers()]


def _positions(molblock: str) -> list[tuple[float, float, float]]:
    mol = Chem.MolFromMolBlock(molblock, removeHs=False, sanitize=False)
    conformer = mol.GetConformer()
    return [
        (p.x, p.y, p.z)
        for p in (conformer.GetAtomPosition(i) for i in range(mol.GetNumAtoms()))
    ]


def _distances(molblock: str) -> list[float]:
    points = _positions(molblock)
    return [math.dist(a, b) for a, b in itertools.combinations(points, 2)]


def _max_deviation(a: list[str], b: list[str]) -> float:
    """Largest single-atom displacement between two sets of molblocks."""
    return max(
        math.dist(pa, pb)
        for mb_a, mb_b in zip(a, b)
        for pa, pb in zip(_positions(mb_a), _positions(mb_b))
    )


#: Molblock coordinates are written to four decimals, so a serialise/reparse
#: round trip is only ever exact to about this. Asserting bitwise equality
#: would fail on -71.502381 against -71.502379 and teach nobody anything.
MOLBLOCK_PRECISION = 5e-4


# --- it actually aligns ------------------------------------------------------


def test_conformers_come_back_in_a_common_frame(qapp=None):
    """The defect itself. Independently embedded conformers start far
    apart in space; after this they are superimposed.

    **The raw set is asserted to be scattered first**, or a fixture that
    happened to embed everything in one frame would make this pass while
    the function did nothing.

    Measured on HEAVY-ATOM centroids, because that is what the fit
    superimposes. The all-atom centroid legitimately still differs by
    ~0.17 A afterwards -- hexanol carries fourteen hydrogens whose
    positions are exactly what varies between conformers -- so measuring
    that would be asserting the absence of a conformational difference
    rather than the presence of a common frame.
    """
    raw = _conformers(HEXANOL)

    def centroid_gap(molblocks) -> float:
        reference = _centroid(_heavy_positions(molblocks[0]))
        return max(
            math.dist(_centroid(_heavy_positions(molblock)), reference)
            for molblock in molblocks[1:]
        )

    assert centroid_gap(raw) > 0.5, "the fixture is already aligned; it proves nothing"

    aligned = align_conformers_for_display(raw)

    assert centroid_gap(aligned) < MOLBLOCK_PRECISION
    assert len(aligned) == len(raw)


def _centroid(points) -> tuple[float, float, float]:
    n = len(points)
    return (
        sum(p[0] for p in points) / n,
        sum(p[1] for p in points) / n,
        sum(p[2] for p in points) / n,
    )


def test_the_first_conformer_is_the_reference_and_does_not_move(qapp=None):
    """It is the lowest-energy one by the caller's ordering, and the frame
    everything else is expressed in. If it moved, the whole set would drift
    every time the view was rebuilt."""
    raw = _conformers(HEXANOL)

    aligned = align_conformers_for_display(raw)

    assert aligned[0] == raw[0]


# --- the invariants ----------------------------------------------------------


def test_alignment_changes_no_internal_geometry(qapp=None):
    """**A COORDINATE-FRAME OPERATION, NOT A CHEMICAL ONE.**

    Every pairwise interatomic distance must survive, which is what makes
    it a rigid motion rather than a distortion. A test on the centroid
    alone would pass against a transform that scaled or sheared the
    molecule into place.

    Compared within molblock precision rather than bitwise -- the
    coordinates go through a four-decimal text format on the way.
    """
    raw = _conformers(HEXANOL)

    aligned = align_conformers_for_display(raw)

    for before, after in zip(raw, aligned):
        deltas = [abs(x - y) for x, y in zip(_distances(before), _distances(after))]
        assert max(deltas) < MOLBLOCK_PRECISION, f"largest change {max(deltas)}"


def test_alignment_preserves_handedness(qapp=None):
    """**A REFLECTION IS THE DANGER AND DISTANCES CANNOT SEE IT.**

    A mirror image preserves every interatomic distance exactly, so the
    test above passes against one. Chirality is what tells them apart:
    the signed volume of any four non-coplanar atoms must keep its sign.
    """
    raw = _conformers(HEXANOL)

    aligned = align_conformers_for_display(raw)

    for before, after in zip(raw, aligned):
        assert _signed_volume(before) * _signed_volume(after) > 0, (
            "the alignment mirrored the molecule"
        )


def _signed_volume(molblock: str) -> float:
    """Signed volume of the first four heavy atoms -- positive or negative
    according to handedness, and unchanged by any proper rotation."""
    mol = Chem.MolFromMolBlock(molblock, removeHs=False, sanitize=False)
    conformer = mol.GetConformer()
    heavy = [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() > 1][:4]
    p = [conformer.GetAtomPosition(i) for i in heavy]
    u = (p[1].x - p[0].x, p[1].y - p[0].y, p[1].z - p[0].z)
    v = (p[2].x - p[0].x, p[2].y - p[0].y, p[2].z - p[0].z)
    w = (p[3].x - p[0].x, p[3].y - p[0].y, p[3].z - p[0].z)
    cross = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    return cross[0] * w[0] + cross[1] * w[1] + cross[2] * w[2]


def test_alignment_is_idempotent(qapp=None):
    """`align(align(raw)) == align(raw)`.

    Enforces the architectural promise mechanically: the display copy is
    always DERIVED from what it is given, never accumulated on top of a
    previous transform. An implementation that composed transforms would
    drift a little further every time the viewer rebuilt.
    """
    raw = _conformers(HEXANOL)

    once = align_conformers_for_display(raw)
    twice = align_conformers_for_display(once)

    assert _max_deviation(once, twice) < MOLBLOCK_PRECISION


def test_a_conformers_orientation_does_not_depend_on_its_neighbours(qapp=None):
    """Each conformer is aligned to THE reference, not to the one before it.

    Chaining -- align 2 to 1, 3 to 2, 4 to 3 -- also produces a common
    frame, is also idempotent, and also distorts nothing, so every other
    invariant in this file passes against it. A mutation proved exactly
    that. What it breaks is subtler: a conformer's orientation then depends
    on which others happen to be in the list.

    **That matters because the gallery pages through SUBSETS.** Showing
    conformers 1-6 and then 7-12 must not re-orient anything, or the
    comparison the gallery exists for is undermined by the act of scrolling.
    """
    raw = _conformers(HEXANOL, count=5)

    everything = align_conformers_for_display(raw)
    a_subset = align_conformers_for_display([raw[0], raw[4]])

    assert _max_deviation([everything[4]], [a_subset[1]]) < MOLBLOCK_PRECISION


def test_alignment_is_deterministic_on_a_symmetric_molecule(qapp=None):
    """A fixed atom correspondence does not by itself guarantee a
    well-determined rigid-body fit -- on a highly symmetric shape several
    rotations score almost identically, and an implementation that let the
    solver pick between them would flicker.

    Cubane, because it is as symmetric as anything gets.
    """
    raw = _conformers(CUBANE, count=3)

    first = align_conformers_for_display(raw)
    second = align_conformers_for_display(raw)

    assert _max_deviation(first, second) == 0.0


def test_a_rotating_methyl_does_not_swing_the_whole_molecule(qapp=None):
    """The fit is on heavy atoms, so three hydrogens spinning around a bond
    cannot drag the ring they hang off.

    Two conformers of toluene differ only in the methyl rotation, so their
    HEAVY atoms should superimpose essentially exactly. A fit that included
    hydrogens would compromise between the ring and the methyl and leave
    the ring visibly rotated -- the same class of jump this whole feature
    exists to remove.
    """
    raw = _conformers(TOLUENE, count=4)

    aligned = align_conformers_for_display(raw)

    reference = _heavy_positions(aligned[0])
    for molblock in aligned[1:]:
        worst = max(math.dist(a, b) for a, b in zip(reference, _heavy_positions(molblock)))
        assert worst < 0.15, f"heavy atoms moved {worst:.3f} A between conformers"


def _heavy_positions(molblock: str) -> list[tuple[float, float, float]]:
    mol = Chem.MolFromMolBlock(molblock, removeHs=False, sanitize=False)
    conformer = mol.GetConformer()
    return [
        (conformer.GetAtomPosition(a.GetIdx()).x,
         conformer.GetAtomPosition(a.GetIdx()).y,
         conformer.GetAtomPosition(a.GetIdx()).z)
        for a in mol.GetAtoms()
        if a.GetAtomicNum() > 1
    ]


# --- it declines rather than guessing ----------------------------------------


@pytest.mark.parametrize(
    "molblocks",
    [
        pytest.param([], id="nothing"),
        pytest.param(["only one"], id="a single conformer"),
    ],
)
def test_nothing_to_align_is_returned_unchanged(molblocks):
    assert align_conformers_for_display(molblocks) == molblocks


def test_structures_that_are_not_conformers_of_one_molecule_are_left_alone():
    """Different atom counts mean there is no identity correspondence, so
    there is nothing this function can honestly do. Returning them
    unchanged beats aligning the first N atoms of each and producing a
    confident, meaningless overlay."""
    ethanol = _conformers("CCO", count=1)[0]
    hexanol = _conformers(HEXANOL, count=1)[0]

    assert align_conformers_for_display([ethanol, hexanol]) == [ethanol, hexanol]
