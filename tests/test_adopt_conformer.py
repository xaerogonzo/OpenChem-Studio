"""The way back from the 3D viewer to the 2D editor.

Structures only ever went one way -- "Send to 3D Viewer Tab" has existed
since the viewer did, and nothing came back. Reported as "there doesn't
seem to be an easy way to directly copy a conformer from our 3d viewer
back into the 2d editor still".

**Every test here is aimed at a defect that was MEASURED in a working
first version of the feature, not at restating the code.** The first
version pushed the conformer's molblock through `EditStructureCommand`,
which is the obvious implementation and is wrong three separate ways:

    aspirin as drawn                 13 atoms   CC(=O)Oc1ccccc1C(=O)O
    a conformer                      21 atoms   (embedded after AddHs)
    after adopting it naively        21 atoms   [H]OC(=O)c1c([H])c([H])...

    cholesterol, closest heavy-atom approach in the drawing
      proper depiction                1.500
      the conformer's own x,y         0.24      <- atoms on top of each other

    conformer count, pressing the button        1 -> 0

**READABILITY IS COMPARED AS A RATIO, NEVER AS AN ABSOLUTE.** See
`_PROJECTION_RATIO_SEEN` below: the projection's own value moves with
whatever conformer the embedder produced, and an absolute bound fitted on
one machine sits inside that spread on another.
"""

from __future__ import annotations

import math

import pytest
from rdkit import Chem

from openchem.bootstrap import build_service_container
from openchem.chem.calculation_input import canonical_conformer
from openchem.commands.conformer_commands import AdoptConformerCommand
from openchem.domain.conformer import ConformerModel
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus

#: Deliberately NOT flat. A planar molecule projects to a usable drawing
#: by accident, so a test built on aspirin alone passes against the naive
#: implementation and proves nothing about the one that shipped.
CHOLESTEROL = "CC(C)CCCC(C)C1CCC2C1(C)CCC1C2CC=C2CC(O)CCC12C"
ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"

#: The molecule this was reported broken on -- a benzobicyclo[2.2.2]
#: octane, C17H25NO2. Its two -CH2CH2- bridges superimpose exactly when
#: the drawing follows the 3D orientation.
REPORTED = "COc1cc(C[C@@H](C)N)c2c(c1OC)C1CCC2CC1"

# --- how readable is readable -------------------------------------------------
#
# **THE ABSOLUTE BOUND THAT USED TO LIVE HERE WAS INSIDE ITS OWN
# DISTRIBUTION.** `projected < 0.5` was fitted to whatever conformer this
# machine's embedder happened to produce, and it failed on the Linux CI
# job at 0.5237 -- read at first as a platform quirk. It is not: measured
# over 20 embedding seeds HERE, cholesterol's projection ranges 0.067 to
# 0.721 in molblock units, so 5 of those 20 seeds break that bound on this
# machine too. Linux merely drew one of them.
#
# Both numbers are ratios against the molecule's OWN ordinary depiction
# now, which removes the bond-length unit, and both thresholds sit in a
# measured GAP rather than being picked. Same instinct as the conformer
# de-duplication threshold: tabulate the distribution and look for the gap
# the threshold is supposed to sit in, and if there is no gap then no
# value of the constant is right.

#: Ratio of closest-approach to the plain depiction's, over 20 embedding
#: seeds. Recorded as DATA so the two thresholds can be checked against a
#: measurement rather than against taste -- `test_the_two_readability_`
#: `thresholds_sit_in_the_measured_gap` does exactly that.
#:
#:     the conformer's raw x,y   0.045 .. 0.480
#:     the laid-out drawing      0.940 .. 1.000
#:                               a gap 0.46 wide
#:
#: Linux's own failing value sits at 0.349, comfortably inside the first
#: band -- which is what says this spread describes that machine too.
_PROJECTION_RATIO_SEEN = (0.045, 0.480)
_LAYOUT_RATIO_SEEN = (0.940, 1.000)

#: A projection this much worse than the ordinary depiction is degenerate.
PROJECTION_IS_DEGENERATE_BELOW = 0.65
#: A layout at least this good is as readable as RDKit would have drawn it.
LAYOUT_IS_READABLE_ABOVE = 0.75


@pytest.fixture(scope="module")
def engine():
    return build_service_container().chemistry_engine


def _molecule(engine, smiles: str) -> MoleculeModel:
    molecule = MoleculeModel()
    engine.set_structure_from_smiles(molecule, smiles)
    return molecule


def _conformer_molblock(engine, molecule: MoleculeModel) -> str:
    """A real embedded conformer, with the explicit hydrogens it carries.

    Through the real provider rather than a fixture string, because the
    explicit hydrogens ARE the thing under test -- a hand-written
    heavy-atom molblock would quietly remove the defect.
    """
    from openchem.chem.conformer_providers import RDKitConformerProvider

    provider = RDKitConformerProvider(random_seed=0xC0FFEE)
    mol = engine.mol_from_molblock(molecule.molblock)
    results = provider.generate_conformers(mol, num_conformers=1, optimize=True)
    return engine.mol_to_molblock(results[0][0])


def _atom_count(molblock: str) -> int:
    return int(molblock.splitlines()[3][:3])


def _closest_approach(molblock: str) -> float:
    """Smallest x,y gap between any two atoms -- how readable the drawing is."""
    mol = Chem.MolFromMolBlock(molblock, removeHs=False)
    conf = mol.GetConformer()
    points = [conf.GetAtomPosition(i) for i in range(mol.GetNumAtoms())]
    return min(
        math.hypot(points[i].x - points[j].x, points[i].y - points[j].y)
        for i in range(len(points))
        for j in range(i + 1, len(points))
    )


# --- the drawing the conformer becomes ---------------------------------------


def test_the_drawing_does_not_gain_the_conformers_explicit_hydrogens(engine):
    """THE FIRST DEFECT. A conformer is embedded after `Chem.AddHs`, so
    aspirin's carries 21 atoms against the 13 that were drawn.

    Adopting those makes the drawing a different structure to everything
    that compares one -- and `select_calculation_input` records that
    eight of the 49 registered calculators return a different number for
    a molecule carrying explicit hydrogens.
    """
    molecule = _molecule(engine, ASPIRIN)
    conformer = _conformer_molblock(engine, molecule)
    assert _atom_count(conformer) == 21, "the fixture stopped carrying explicit hydrogens"

    drawing = engine.drawing_from_conformer(conformer)

    assert _atom_count(drawing.molblock) == 13


def test_the_canonical_smiles_survives_being_redrawn(engine):
    """The consequence of the above, stated as the thing that actually
    matters: the molecule must still be the same molecule.

    Asserted separately from the atom count because they can come apart
    -- a drawing could keep 13 atoms and still lose a bond order.
    """
    molecule = _molecule(engine, ASPIRIN)
    before = molecule.canonical_smiles

    drawing = engine.drawing_from_conformer(_conformer_molblock(engine, molecule))

    assert engine.molblock_to_smiles(drawing.molblock) == before


def test_the_drawing_is_laid_out_rather_than_projected(engine):
    """THE SECOND DEFECT, and the reason a flat molecule cannot test it.

    Taking the conformer's own x and y puts two of cholesterol's heavy
    atoms 0.219 units apart where a real depiction has 1.500 -- on top of
    each other, so the canvas is unusable for exactly the molecules whose
    3D geometry is worth having.

    Both assertions are against the molecule's OWN ordinary depiction
    rather than a constant: "as readable as RDKit would have drawn it
    anyway" is the claim, and a fixed threshold would silently encode
    aspirin's bond length instead.

    **THE FIRST ONE IS FIXTURE VALIDITY, and it used to be absolute.**
    It establishes that the raw projection really is unusable, without
    which the second assertion proves nothing -- a flat molecule projects
    to something fine by accident. As `projected < 0.5` it sat inside the
    projection's own spread and failed on CI's conformer; see
    `_PROJECTION_RATIO_SEEN`.
    """
    molecule = _molecule(engine, CHOLESTEROL)
    conformer = _conformer_molblock(engine, molecule)
    plain = _closest_approach(molecule.molblock)

    projected = _closest_approach(Chem.MolToMolBlock(Chem.RemoveHs(
        Chem.MolFromMolBlock(conformer, removeHs=False)
    )))
    drawn = engine.drawing_from_conformer(conformer)

    assert projected < plain * PROJECTION_IS_DEGENERATE_BELOW, (
        f"cholesterol's projection stopped overlapping ({projected / plain:.3f} "
        f"of its own depiction) -- re-derive _PROJECTION_RATIO_SEEN rather than "
        f"widening the threshold, which is what made this platform-dependent"
    )
    assert _closest_approach(drawn.molblock) >= plain * LAYOUT_IS_READABLE_ABOVE
    assert drawn.follows_geometry


def test_the_two_readability_thresholds_sit_in_the_measured_gap():
    """A guard on the CONSTANTS, not on the code.

    The two populations are bimodal with a gap 0.46 wide, and the whole
    reason the thresholds are trustworthy is that they sit inside it
    rather than inside either band. Widening one until a failure goes
    away is exactly what produced the platform-dependent bound this
    replaced, so it fails here naming the measurement instead.

    Cheap and derived: it compares each threshold against the recorded
    spread, so it cannot be satisfied by moving the thresholds alone.
    """
    projection_max = _PROJECTION_RATIO_SEEN[1]
    layout_min = _LAYOUT_RATIO_SEEN[0]

    assert projection_max < PROJECTION_IS_DEGENERATE_BELOW, (
        "the degenerate-projection threshold is inside the range projections "
        "were actually measured at, so a legitimate conformer can break it"
    )
    assert LAYOUT_IS_READABLE_ABOVE < layout_min, (
        "the readable-layout threshold is inside the range layouts were "
        "actually measured at"
    )
    assert PROJECTION_IS_DEGENERATE_BELOW <= LAYOUT_IS_READABLE_ABOVE, (
        "a drawing could satisfy both 'degenerate' and 'readable' at once, "
        "which makes the pair of them say nothing"
    )


# --- the shape that has no flat orientation ----------------------------------


def test_a_symmetric_bridge_falls_back_to_a_readable_layout(engine):
    """THE DEFECT REPORTED FROM THE RUNNING APP, as "it didn't really do
    anything" on a benzobicyclo[2.2.2]octane.

    Viewed down the bridgehead-to-bridgehead axis of a bicyclo[2.2.2]
    system the two bridges superimpose EXACTLY, so a depiction that
    follows the 3D orientation draws the bridge underneath itself. The
    structure then reads as a plain fused bicyclic, and RDKit logs
    "ambiguous stereochemistry - overlapping neighbors" -- which is what
    named this in the user's log.

    Measured closest approach of the oriented layout: **0.000**. Two
    atoms at identical coordinates.
    """
    molecule = _molecule(engine, REPORTED)
    conformer = _conformer_molblock(engine, molecule)

    drawing = engine.drawing_from_conformer(conformer)

    assert not drawing.follows_geometry, "the degenerate layout was accepted"
    # And what came back is genuinely readable, not merely flagged.
    assert _closest_approach(drawing.molblock) > 0.5


def test_the_degenerate_layout_really_is_degenerate(engine):
    """Asserts the DEFECT, so this stops being a workaround if RDKit ever
    starts laying these out sensibly -- the same reason the Open Babel
    element test asserts Open Babel's own bug.

    Without it, the guard above would keep passing on a fallback that had
    become unnecessary, and nobody would know.
    """
    from rdkit.Chem import AllChem

    molecule = _molecule(engine, REPORTED)
    heavy = Chem.RemoveHs(
        Chem.MolFromMolBlock(_conformer_molblock(engine, molecule), removeHs=False)
    )
    oriented = Chem.Mol(heavy)
    AllChem.GenerateDepictionMatching3DStructure(oriented, heavy)

    assert _closest_approach(Chem.MolToMolBlock(oriented)) < 0.01


def test_the_readable_layout_threshold_sits_between_the_two_populations(engine):
    """A constant with two measured bounds is not a taste question.

    Across 29 molecules the ratio is sharply bimodal: five symmetric
    bridges at 0.000, then tropinone 0.239 and morphine 0.392, then a
    0.41-wide gap, then camphor 0.799 and twenty at 1.000. Any value in
    [0.40, 0.79] separates them identically, so leaving that window is a
    decision rather than a tweak -- and this fails naming it.
    """
    from openchem.chem.engine import READABLE_LAYOUT_FRACTION

    assert 0.40 <= READABLE_LAYOUT_FRACTION <= 0.79


def test_a_fused_polycycle_still_keeps_its_orientation(engine):
    """The fallback must not swallow the feature.

    A test that only checked the bridged case would pass just as happily
    against a `drawing_from_conformer` that had given up and always
    returned a plain layout -- which is the whole feature gone. Morphine
    and strychnine are polycyclic and NOT degenerate; cholesterol keeps
    its orientation at ratio 1.000.
    """
    molecule = _molecule(engine, CHOLESTEROL)

    drawing = engine.drawing_from_conformer(_conformer_molblock(engine, molecule))

    assert drawing.follows_geometry


# --- the command -------------------------------------------------------------


def test_adopting_keeps_the_conformers(engine):
    """THE THIRD DEFECT, and the one that was visible in the running app.

    `EditStructureCommand` clears the conformer set on redo, correctly,
    because a structure edit invalidates geometries computed for the old
    structure. Adopting edits no structure. Measured on the first
    version, which used it: the count went 1 -> 0, and
    `MoleculeViewer3DWidget._refresh_view` answers an empty list by
    clearing the backend and disabling the button -- so the control
    blanked the viewer it lives in and discarded the set the user had
    just generated.
    """
    molecule = _molecule(engine, ASPIRIN)
    conformer = ConformerModel(molblock=_conformer_molblock(engine, molecule), energy=1.0)
    molecule.conformers = [conformer]

    AdoptConformerCommand(engine, molecule, conformer.molblock, EventBus()).redo()

    assert molecule.conformers == [conformer]


def test_adopting_is_undoable_back_to_the_original_drawing(engine):
    molecule = _molecule(engine, ASPIRIN)
    before = molecule.molblock
    command = AdoptConformerCommand(
        engine, molecule, _conformer_molblock(engine, molecule), EventBus()
    )

    command.redo()
    changed = molecule.molblock
    command.undo()

    assert changed != before, "redo did not change the drawing at all"
    assert molecule.molblock == before


def test_redo_after_undo_restores_the_same_drawing(engine):
    """An undo/redo pair must not hand back a different layout from the
    one the user accepted -- a change nobody asked for, arriving through
    the undo stack of all places.

    **What this catches is the SOURCE, not the timing**, and the
    difference was established by mutation rather than assumed. Deriving
    the drawing inside `redo` from `self._molecule.molblock` -- i.e. from
    whatever is current, which after an undo is the ORIGINAL drawing --
    is caught here. Deriving it inside `redo` from the conformer is an
    equivalent mutation: RDKit's depiction is deterministic for a fixed
    input, so it produces the identical bytes and no test can tell the
    two apart. Building it in the constructor is therefore a statement
    of intent rather than something this guards.
    """
    molecule = _molecule(engine, ASPIRIN)
    command = AdoptConformerCommand(
        engine, molecule, _conformer_molblock(engine, molecule), EventBus()
    )

    command.redo()
    first = molecule.molblock
    command.undo()
    command.redo()

    assert molecule.molblock == first


def test_adopting_does_not_change_which_geometry_a_calculation_uses(engine):
    """Stated as a test because "adopt" reads like it should mean more.

    `canonical_conformer` picks the LOWEST MMFF energy, not a position in
    the list, and export and every `GEOMETRY` calculator go through it.
    So the answer is the same before and after -- and if that ever stops
    being true, it is a policy change that should be made deliberately
    rather than discovered.
    """
    molecule = _molecule(engine, ASPIRIN)
    conformer_molblock = _conformer_molblock(engine, molecule)
    low = ConformerModel(molblock=conformer_molblock, energy=1.0)
    high = ConformerModel(molblock=conformer_molblock, energy=99.0)
    molecule.conformers = [low, high]

    # Adopt the one that is NOT the lowest, which is the case that could
    # tell a position-based policy from an energy-based one.
    AdoptConformerCommand(engine, molecule, high.molblock, EventBus()).redo()

    assert canonical_conformer(molecule) is low


# --- the drawing follows the camera ------------------------------------------

#: A stereocentre whose FOURTH SUBSTITUENT IS AN EXPLICIT HYDROGEN, which
#: is the case that makes the perceive-then-remove ordering matter.
ALANINE = "C[C@@H](N)C(=O)O"

_HALF = math.sqrt(0.5)
#: 90 degrees about y, and the same rotation from a panned, zoomed camera.
VIEW_Y90 = [0.0, 0.0, 0.0, 0.0, 0.0, _HALF, 0.0, _HALF]
VIEW_Y90_ZOOMED = [9.0, -3.0, 1.5, 88.0, 0.0, _HALF, 0.0, _HALF]
VIEW_X40 = [0.0, 0.0, 0.0, 0.0, 0.342, 0.0, 0.0, 0.940]


def _z_spread(molblock: str) -> float:
    zs = [z for _x, _y, z in _xyz(molblock)]
    return max(zs) - min(zs)


def _xyz(molblock: str) -> list[tuple[float, float, float]]:
    mol = Chem.MolFromMolBlock(molblock, removeHs=False, sanitize=False)
    conformer = mol.GetConformer()
    return [
        (p.x, p.y, p.z)
        for p in (conformer.GetAtomPosition(i) for i in range(mol.GetNumAtoms()))
    ]


def test_an_oriented_drawing_keeps_its_third_dimension(engine):
    """THE FEATURE ITSELF: "the structure is not in a *literal* 3d shape,
    which is the entire point of what I'm trying to do".

    The molblock stays 3D and the editor draws its x/y, so what lands on
    the canvas is a projection of the real geometry -- which is what
    MarvinSketch shows for buckminsterfullerene. Ketcher holds those
    coordinates through an edit; that was gated before this was written.
    """
    molecule = _molecule(engine, CHOLESTEROL)
    conformer = _conformer_molblock(engine, molecule)

    drawing = engine.drawing_from_conformer(conformer, view=VIEW_Y90)

    assert _z_spread(drawing.molblock) > 1.0
    assert drawing.follows_geometry


def test_an_oriented_drawing_still_drops_the_hydrogens(engine):
    """The original defect does not come back through the new path.
    Aspirin's conformer is 21 atoms; the drawing must be 13."""
    molecule = _molecule(engine, ASPIRIN)

    drawing = engine.drawing_from_conformer(
        _conformer_molblock(engine, molecule), view=VIEW_Y90
    )

    assert _atom_count(drawing.molblock) == 13
    assert engine.molblock_to_smiles(drawing.molblock) == molecule.canonical_smiles


def test_turning_the_camera_never_turns_R_into_S(engine):
    """**THE INVARIANT WORTH HAVING**, and the reason the stereo is
    perceived before the hydrogens come off.

    Alanine's stereocentre has an explicit hydrogen as its fourth ligand,
    so perceiving after removal would make the answer depend on how RDKit
    reconstructs it rather than on the geometry that is present.

    Checked across several cameras, because a transform that mirrored the
    molecule would flip the assignment while preserving every bond length
    and angle -- invisible to any geometric check. (A mutation mirroring
    the matrix through z fails ten tests, this among them.)

    **The perceive-before-remove ORDERING is not what this catches**, and
    a mutation deleting the explicit perception survived. Measured on this
    molecule with the tags wiped first, both orders give (1, 'R') -- three
    heavy neighbours and their coordinates already determine the fourth
    direction. The invariant is still worth having; the mechanism behind
    it was not what it was assumed to be.
    """
    molecule = _molecule(engine, ALANINE)
    conformer = _conformer_molblock(engine, molecule)
    expected = molecule.canonical_smiles
    assert "@" in expected, "the fixture lost its stereocentre"

    for view in (None, VIEW_Y90, VIEW_X40, VIEW_Y90_ZOOMED):
        drawing = engine.drawing_from_conformer(conformer, view=view)
        assert engine.molblock_to_smiles(drawing.molblock) == expected, f"view={view}"


def test_the_camera_changes_the_projection_and_nothing_else(engine):
    """Two cameras must give different x/y -- otherwise the button is not
    using the camera at all -- and identical 3D geometry, which is what
    catches an accidental flattening inside the projection step."""
    molecule = _molecule(engine, CHOLESTEROL)
    conformer = _conformer_molblock(engine, molecule)

    a = _xyz(engine.drawing_from_conformer(conformer, view=VIEW_Y90).molblock)
    b = _xyz(engine.drawing_from_conformer(conformer, view=VIEW_X40).molblock)

    assert max(math.dist(p[:2], q[:2]) for p, q in zip(a, b)) > 0.5, "the camera did nothing"

    for i in range(len(a)):
        for j in range(i + 1, len(a)):
            assert math.dist(a[i], a[j]) == pytest.approx(math.dist(b[i], b[j]), abs=5e-4)


def test_zoom_and_pan_do_not_reach_the_drawing(engine):
    """Asserted end to end as well as on the matrix, because this is the
    path where a rescaled or displaced structure would actually be
    written to disk."""
    molecule = _molecule(engine, ASPIRIN)
    conformer = _conformer_molblock(engine, molecule)

    plain = _xyz(engine.drawing_from_conformer(conformer, view=VIEW_Y90).molblock)
    zoomed = _xyz(engine.drawing_from_conformer(conformer, view=VIEW_Y90_ZOOMED).molblock)

    for p, q in zip(plain, zoomed):
        assert p == pytest.approx(q, abs=5e-4)


def test_a_crowded_projection_is_reported_rather_than_repaired(engine):
    """When the orientation came from the user's own camera, substituting
    a different one would be the silent-substitution failure this line of
    work keeps finding. It is flagged instead, so the app can say "rotate
    the view and try again" -- something they can act on.

    Both directions, or a flag that is always True would pass.
    """
    molecule = _molecule(engine, REPORTED)
    conformer = _conformer_molblock(engine, molecule)

    crowded = [
        engine.drawing_from_conformer(conformer, view=v).crowded
        for v in (VIEW_Y90, VIEW_X40, [0.0] * 4 + [0.0, 0.0, 0.0, 1.0])
    ]

    assert any(not flag for flag in crowded), "every angle was called crowded"
    # And whatever it reports, it still hands back the orientation asked for.
    assert all(
        engine.drawing_from_conformer(conformer, view=v).follows_geometry
        for v in (VIEW_Y90, VIEW_X40)
    )


def test_the_drawing_still_claims_a_single_enantiomer(engine):
    """A DRAWING THAT LOSES ITS CHIRAL FLAG SAYS SOMETHING DIFFERENT.

    The molfile chiral flag is what distinguishes "this exact enantiomer"
    from "this relative arrangement, either hand". RDKit writes 0 by
    default, and Ketcher renders 0 as **"AND Enantiomer"** against 1 as
    **"ABS"** -- seen in the running app, where an adopted drawing of a
    resolved molecule started describing a racemate while its SMILES kept
    the @ and every calculator went on treating it as resolved.

    Both paths, because the oriented one is new and the flat one had the
    same defect all along.
    """
    molecule = _molecule(engine, REPORTED)
    conformer = _conformer_molblock(engine, molecule)

    for view in (None, VIEW_Y90):
        drawing = engine.drawing_from_conformer(conformer, view=view)
        assert drawing.molblock.splitlines()[3][12:15].strip() == "1", f"view={view}"


def test_a_molecule_with_no_stereocentre_makes_no_such_claim(engine):
    """Flagging an achiral structure as absolute would assert more than
    the structure says. Benzene has nothing to be absolute about."""
    molecule = _molecule(engine, "c1ccccc1")

    drawing = engine.drawing_from_conformer(_conformer_molblock(engine, molecule))

    assert drawing.molblock.splitlines()[3][12:15].strip() == "0"
