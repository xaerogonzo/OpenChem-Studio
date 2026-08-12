from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass

from rdkit import Chem
from rdkit.Chem import AllChem, rdMolTransforms
from rdkit.Geometry import Point3D

from openchem.chem.camera_orientation import camera_to_model_transform, rotate
from openchem.chem.stereochemistry import (
    StereoChange,
    StereochemistryConflict,
    compare_stereochemistry,
)

from openchem.domain.molecule import MoleculeModel

logger = logging.getLogger("openchem.chemistry")

#: Grid spacing for the property heat map, in the depiction's own units.
#: The cost is quadratic in 1/spacing and it lands in the SVG as one path
#: per cell, so this is a file-size dial as much as a smoothness one.
#: Measured on p-nitroaniline at 420x360: 0.05 -> 845 KB, 0.10 -> 216 KB,
#: 0.20 -> 59 KB. 0.10 is the coarsest that still reads as a smooth
#: gradient rather than visible blocks at normal dialog sizes.
HEATMAP_GRID_RESOLUTION = 0.10

#: Standard deviation of each atom's Gaussian, in the same units. Wide
#: enough that neighbouring atoms blend into a field rather than staying
#: separate dots -- which is the entire difference from colouring atom
#: discs -- and narrow enough that a lone substituent stays localised.
HEATMAP_GAUSSIAN_WIDTH = 0.4

#: How far the grid extends beyond the atoms. Small, and NOT a lever for
#: the artifact below -- measured on p-nitroaniline, raising it from 0.5
#: to 10.0 never reached the canvas corner (RDKit rescales to keep both
#: the grid and the molecule in frame) while the SVG went from 940 KB to
#: 17.7 MB. It buys nothing and costs everything.
HEATMAP_GRID_PADDING = 0.5

#: Cells whose magnitude is below this FRACTION of the largest present are
#: left unpainted, so the page shows through where there is no signal.
#:
#: Without it the grid paints its whole rectangle, and the rectangle is
#: visible: seen in the running app as a hard-edged tinted box sitting
#: behind the molecule and stopping mid-pane. Worse, the box is not
#: neutral -- a per-atom charge dataset excludes implicit hydrogens and so
#: sums to a net negative, and the Gaussian tails carry that across the
#: whole grid, tinting empty space pink. The field being drawn is honest;
#: painting it over territory where it has decayed to nothing is not.
#:
#: 0.05 rather than a larger value because clipping real signal is the
#: worse error. Measured against no threshold at all: strongly-tinted
#: pixels went 5334 -> 5338 red and 2371 -> 2371 blue (noise), the empty
#: region went to pure white, and the SVG dropped 545 KB -> 307 KB.
HEATMAP_FILL_THRESHOLD = 0.05


#: How readable an orientation-following depiction has to be, as a
#: fraction of the closest approach in the plain depiction of the same
#: molecule, before it is preferred to the plain one.
#:
#: **Bracketed by measurement, not chosen by feel**, across 29 molecules
#: from benzene to strychnine. The ratio is sharply bimodal and the
#: threshold sits in the largest gap in the whole set:
#:
#:     0.000  bicyclo[2.2.2]octane, quinuclidine, DABCO, barrelene, and
#:            the benzobicyclo[2.2.2]octane this was reported on
#:     0.239  tropinone
#:     0.392  morphine
#:            <-- the gap, 0.41 wide
#:     0.799  camphor
#:     1.000  twenty others, norbornane / adamantane / cubane / strychnine
#:            among them
#:     1.388  sucrose, where the oriented layout is BETTER than the plain
#:
#: Anything in [0.40, 0.79] separates the two populations identically;
#: `test_the_readable_layout_threshold_sits_between_the_two_populations`
#: fails if it leaves that window.
READABLE_LAYOUT_FRACTION = 0.6

#: Closest approach, in molblock units, below which a projection is called
#: crowded. A normal bond is ~1.5, so a third of one means two atoms are
#: hard to tell apart. Reported to the user rather than repaired -- see
#: `ConformerDrawing.crowded`.
_CROWDED_APPROACH = 0.5


@dataclass(frozen=True)
class ConformerDrawing:
    """A drawing made from a conformer, and what it managed to keep.

    Neither flag is a detail. `follows_geometry` False means the drawing is
    a correct depiction of the right molecule that says nothing about the
    conformer chosen, and the user pressed a button asking for exactly
    that -- saying so is the difference between "this molecule cannot show
    its geometry flat" and "the button did nothing".

    `crowded` means atoms are drawn close enough to be hard to tell apart.
    It is reported rather than repaired: when the orientation came from the
    user's own camera, quietly substituting a different one would be the
    same silent-substitution failure in a new place, and "rotate the view a
    little and try again" is something they can act on.
    """

    molblock: str
    follows_geometry: bool
    crowded: bool = False
    #: What this geometry did to the structure's stereochemistry, when a
    #: reference drawing was given to compare against. `None` means
    #: nobody asked, not that nothing happened.
    stereo: StereoChange | None = None


def _claim_absolute_stereochemistry(mol: Chem.Mol) -> None:
    """Mark the drawing as ONE enantiomer, when it has a defined centre.

    The molfile chiral flag is what says whether a drawing means "this
    exact enantiomer" or "this relative arrangement, either hand". RDKit
    writes 0 by default, and Ketcher renders 0 as **"AND Enantiomer"** and
    1 as **"ABS"** -- so a drawing derived from a conformer silently
    stopped claiming which enantiomer it was, while its SMILES kept the
    @ and every calculator went on treating it as resolved.

    Only when there is something to claim: flagging a molecule with no
    defined stereocentre as absolute would be asserting more than the
    structure says.
    """
    if Chem.FindMolChiralCenters(mol, useLegacyImplementation=False):
        mol.SetProp("_MolFileChiralFlag", "1")


def _cip_labels(mol: Chem.Mol) -> tuple[tuple[int, str], ...]:
    """Every assigned CIP code, by atom index.

    Compared before and after orienting, because a rotation must not
    change one. NOT a sufficient check for a reflection on its own -- a
    mirror can leave particular assignments intact -- which is why
    `camera_to_model_transform` is separately held to det(R) = +1.
    """
    return tuple(
        (atom.GetIdx(), atom.GetProp("_CIPCode"))
        for atom in mol.GetAtoms()
        if atom.HasProp("_CIPCode")
    )


def _closest_approach(mol: Chem.Mol) -> float:
    """Smallest distance between any two atoms in the 2D layout.

    How readable a depiction is, in one number. A normal bond is 1.5 in
    these units; two atoms at 0.0 are drawn on top of each other.
    """
    conformer = mol.GetConformer()
    points = [conformer.GetAtomPosition(i) for i in range(mol.GetNumAtoms())]
    return min(
        (
            math.hypot(points[i].x - points[j].x, points[i].y - points[j].y)
            for i in range(len(points))
            for j in range(i + 1, len(points))
        ),
        default=0.0,
    )


class InvalidStructureError(ValueError):
    """Raised when a molblock/SMILES cannot be parsed into a valid RDKit Mol."""


class ChemistryEngine:
    """The sole RDKit touchpoint for MoleculeModel <-> rdkit.Chem.Mol conversion
    and canonical identity (SMILES/InChI/InChIKey).

    Nothing outside `openchem.chem` should import `rdkit` directly — everything
    else works with `MoleculeModel` and calls through here.
    """

    def mol_from_model(self, model: MoleculeModel) -> Chem.Mol:
        if not model.molblock:
            raise InvalidStructureError(f"Molecule {model.uuid} has no molblock")
        return self.mol_from_molblock(model.molblock)

    def mol_from_molblock(self, molblock: str) -> Chem.Mol:
        # `removeHs=False` -- RDKit's default (True) converts any EXPLICIT
        # hydrogen atom into implicit H-count on its neighbor, which keeps
        # the molecular formula correct but silently discards that
        # hydrogen's own 3D position entirely. Confirmed live: a conformer
        # molblock built via Chem.AddHs() + embedding (RDKitConformerProvider,
        # the normal path for real 3D geometry) round-tripped through the
        # default here came back as a BARE HEAVY-ATOM-ONLY mol with no
        # hydrogen positions at all -- for water, an oxygen atom with none
        # of its two hydrogens, which OrcaQuantumEngineProvider.build_input
        # then sent to ORCA as-is, silently computing the wrong molecule's
        # energy instead of failing loudly.
        mol = Chem.MolFromMolBlock(molblock, removeHs=False)
        if mol is None:
            raise InvalidStructureError("Could not parse molblock")
        return mol

    def mol_to_molblock(self, mol: Chem.Mol) -> str:
        return Chem.MolToMolBlock(mol)

    def molblock_with_explicit_hydrogens(self, molblock: str) -> str:
        """The same structure with its implicit hydrogens made into atoms.

        For a view that has to DEPICT a dataset computed on `AddHs(mol)` --
        the Calculator Inspector's "Explicit hydrogens" mode. Without it the
        depiction is still the heavy-atom drawing, `render_2d_svg`'s
        `drawable()` guard drops every hydrogen index as out of range, and
        the pane shows 13 labelled atoms beside a header describing 21.

        It lives here rather than in the dialog because `ui/` may not import
        RDKit (`tests/test_layering.py`), and the rule earns its keep: the
        two facts below are chemistry, not presentation.

        **A PURE ADDITION -- it moves nothing.** Measured on aspirin and
        caffeine, in 2D and on a real conformer, the heavy atoms come back
        at exactly their original coordinates (0.00e+00 displacement), with
        0 overlapping pairs in the 2D layout and real non-zero z on the new
        hydrogens in 3D. That matters because a depiction that silently
        re-laid-out the skeleton would read as a different conformer, which
        is a worse bug than the one this exists to fix.

        **`AddHs` APPENDS**, so heavy-atom indices 0..n-1 are untouched and
        a caller's existing per-atom keys still address the same atoms.
        """
        mol = self.mol_from_molblock(molblock)
        return Chem.MolToMolBlock(Chem.AddHs(mol, addCoords=True))

    def drawing_from_conformer(
        self,
        molblock: str,
        view: Sequence[float] | None = None,
        reference: str | None = None,
    ) -> ConformerDrawing:
        """A drawing of a 3D conformer: heavy atoms, oriented as asked.

        **With a `view`, this keeps the 3D geometry and simply turns it.**
        That is the whole point of the feature -- reported as "the
        structure is not in a *literal* 3d shape, which is the entire point
        of what I'm trying to do", against a MarvinSketch screenshot of
        buckminsterfullerene drawn in perspective inside a 2D editor. The
        molblock stays 3D and the editor draws its x/y, so crossing bonds
        are not a defect: they are what the projection of a real geometry
        looks like. Ketcher holds those coordinates through an edit --
        measured, see `tests/test_ketcher_holds_3d_coordinates.py`.

        Without a `view` it falls back to a flat depiction laid out to
        match the conformer, which is what shipped before a camera was
        available. Everything below is about that path.

        A conformer cannot simply BE a flat drawing, for two measured
        reasons.

        **Its hydrogens are explicit.** Conformers are embedded after
        `Chem.AddHs`, so aspirin's is 21 atoms against the 13 that were
        drawn -- and handing those to the drawing changes the canonical
        SMILES to `[H]OC(=O)c1c([H])c([H])...`, which is a different
        structure to everything that compares one. Eight of the 49
        registered calculators return a different number for a molecule
        carrying explicit hydrogens, which is exactly why `DRAWING` is
        the default in `select_calculation_input` rather than a fallback.

        **Its x and y are a projection, not a layout.** Taking the
        conformer's own coordinates puts two of cholesterol's heavy atoms
        0.219 units apart where a real depiction has 1.500 -- on top of
        each other, so the canvas would be unusable for exactly the
        molecules a 3D geometry matters most for.
        `GenerateDepictionMatching3DStructure` lays out a proper drawing
        whose orientation still follows the 3D one, which is the point of
        bringing it across at all.

        **AND THAT LAYOUT IS ITSELF DEGENERATE FOR A SYMMETRIC BRIDGE,
        which is why the result is checked rather than trusted.** Viewed
        down the bridgehead-to-bridgehead axis of a bicyclo[2.2.2]
        system the two bridges superimpose EXACTLY, and a depiction that
        follows the 3D orientation reproduces that faithfully: measured
        closest approach **0.000** -- two atoms at identical coordinates
        -- for bicyclo[2.2.2]octane, quinuclidine, DABCO and barrelene.
        Reported from the running app on a benzobicyclo[2.2.2]octane,
        where the bridge was drawn underneath itself so the structure
        read as a plain fused bicyclic, and RDKit logged "ambiguous
        stereochemistry - overlapping neighbors" twice.

        So the oriented layout is used only when it is about as readable
        as the plain one, and `follows_geometry` says which was used. It
        is NOT a "bridged" test -- norbornane, adamantane, cubane and
        strychnine all keep their orientation; it is the symmetric
        two-bridge case that collapses.

        **ROTATING THE REFERENCE FIRST DOES NOT HELP**, which is the
        obvious idea and was measured before the fallback was accepted:
        the degeneracy looks like a viewpoint problem, since a
        bicyclo[2.2.2] only superimposes seen down its bridge axis.
        `GenerateDepictionMatching3DStructure` normalises orientation
        internally, so all 25 combinations of rotating the conformer by
        0-90 degrees about two axes returned byte-identical layouts --
        0.000 every time, for all five degenerate cases. The fallback is
        the only answer this function leaves.
        """
        if view is not None:
            return self._oriented_drawing(molblock, view, reference)

        heavy = Chem.RemoveHs(self.mol_from_molblock(molblock))
        _claim_absolute_stereochemistry(heavy)

        plain = Chem.Mol(heavy)
        AllChem.Compute2DCoords(plain)

        oriented = Chem.Mol(heavy)
        try:
            AllChem.GenerateDepictionMatching3DStructure(oriented, heavy)
        except (ValueError, RuntimeError):
            # A plain depiction is still a correct drawing of the same
            # structure -- it just no longer echoes the 3D orientation.
            # Refusing here would mean the button did nothing, which this
            # line of work keeps finding to be the worse failure.
            logger.warning(
                "Could not orient the drawing to the conformer; laying it out plainly.",
                exc_info=True,
            )
            return ConformerDrawing(
                Chem.MolToMolBlock(plain),
                follows_geometry=False,
                stereo=self._stereo_change(reference, plain),
            )

        readable = _closest_approach(plain)
        if _closest_approach(oriented) < READABLE_LAYOUT_FRACTION * readable:
            logger.info(
                "The conformer's orientation cannot be drawn without overlap; "
                "using a plain layout instead."
            )
            return ConformerDrawing(
                Chem.MolToMolBlock(plain),
                follows_geometry=False,
                stereo=self._stereo_change(reference, plain),
            )
        return ConformerDrawing(
            Chem.MolToMolBlock(oriented),
            follows_geometry=True,
            stereo=self._stereo_change(reference, oriented),
        )

    def _oriented_drawing(
        self, molblock: str, view: Sequence[float], reference: str | None = None
    ) -> ConformerDrawing:
        """The conformer turned to face the camera, still in 3D.

        Stereo is perceived before the hydrogens come off. **That ordering
        turns out NOT to be load-bearing, and saying so is the point.**
        The worry was that a hydrogen is frequently the fourth ligand of a
        tetrahedral centre, so removing it first would leave the answer
        depending on how RDKit reconstructs the implicit H. Measured on
        alanine, with the tags wiped first so neither run could inherit an
        earlier assignment:

            wiped -> RemoveHs -> perceive     (1, 'R')
            wiped -> perceive -> RemoveHs     (1, 'R')

        Three heavy neighbours and their coordinates already determine the
        fourth direction. The call stays because it makes the CIP
        comparison below meaningful whatever produced the molblock -- a 2D
        one would otherwise give an empty `before` and compare nothing --
        not because the sequence is delicate.

        **Keeping z preserves the GEOMETRY, not the stereochemistry.**
        Stereo is an annotation on the graph; z only makes it derivable.
        So it is re-perceived and then CHECKED against the source, because
        the useful invariant is that turning the camera can never turn R
        into S -- and a rotation that quietly mirrored the molecule would
        do exactly that while preserving every bond length.

        The centroid is subtracted before rotating and not added back:
        rotation is about the origin, and a molecule centred on it is what
        the editor wants anyway.
        """
        source = self.mol_from_molblock(molblock)
        Chem.AssignStereochemistryFrom3D(source)
        before = _cip_labels(source)

        turned = Chem.Mol(source)
        conformer = turned.GetConformer()
        points = [conformer.GetAtomPosition(i) for i in range(turned.GetNumAtoms())]
        centre = (
            sum(p.x for p in points) / len(points),
            sum(p.y for p in points) / len(points),
            sum(p.z for p in points) / len(points),
        )
        rotated = rotate(
            [(p.x - centre[0], p.y - centre[1], p.z - centre[2]) for p in points],
            camera_to_model_transform(view),
        )
        for index, (x, y, z) in enumerate(rotated):
            conformer.SetAtomPosition(index, Point3D(x, y, z))

        drawing = Chem.RemoveHs(turned)
        Chem.AssignStereochemistryFrom3D(drawing)
        after = _cip_labels(drawing)
        if before and after != before:
            # Loud, because it means the geometry and the graph now
            # disagree about what molecule this is -- and every other
            # symptom of that is invisible.
            logger.warning(
                "Orienting the conformer changed its stereochemistry: %s -> %s",
                before,
                after,
            )
        _claim_absolute_stereochemistry(drawing)
        return ConformerDrawing(
            Chem.MolToMolBlock(drawing),
            follows_geometry=True,
            crowded=_closest_approach(drawing) < _CROWDED_APPROACH,
            stereo=self._stereo_change(reference, drawing),
        )

    def _stereo_change(self, reference: str | None, drawing: Chem.Mol):
        """What the geometry did to the structure's stereochemistry.

        `None` when no reference was given -- "nobody asked" is different
        from "nothing happened", and a caller that cannot tell them apart
        would report silence as safety.
        """
        if reference is None:
            return None
        try:
            before = self.mol_from_molblock(reference)
        except InvalidStructureError:
            return None
        return compare_stereochemistry(before, drawing)

    def molblock_to_smiles(self, molblock: str) -> str:
        """Isomeric SMILES for a structure held as a molblock.

        Isomeric, not canonical-without-stereo: the first caller is the
        stereoisomer grid's copy action, where dropping the @/@@ would
        turn every isomer into the same string and make the copy useless.
        """
        return Chem.MolToSmiles(self.mol_from_molblock(molblock), isomericSmiles=True)

    def render_2d_svg(
        self,
        molblock: str,
        atom_colors: dict[int, str] | None = None,
        atom_labels: dict[int, str] | None = None,
        width: int = 360,
        height: int = 320,
    ) -> str:
        """Renders `molblock`'s existing 2D layout (never recomputed --
        this must match what's drawn in the 2D editor) as an SVG string,
        optionally highlighting atoms with `atom_colors` (atom index -> hex
        color), the same shape `ui.visualization.VisualizationLayer.atom_colors`
        already produces for the 3D viewer -- lets a caller (the Property
        Inspector dialog) feed the same color data into both renderings.
        `atom_labels` (atom index -> formatted text, Phase 18) sets RDKit's
        `atomNote` per atom -- confirmed live this renders as vector glyph
        paths near the atom (RDKit's SVG backend draws text as bezier
        paths, not literal `<text>` nodes, so verify by rendering, not by
        string-searching the SVG output)."""
        from rdkit.Chem.Draw import rdMolDraw2D

        mol = self.mol_from_molblock(molblock)
        atom_count = mol.GetNumAtoms()

        def drawable(idx: int) -> bool:
            """Whether `idx` addresses an atom this depiction actually has.

            Callers legitimately hold data keyed to a DIFFERENT molecule than
            the one drawn: several calculators run on `Chem.AddHs(mol)` and
            return a value per hydrogen, while the depiction is the editor
            molblock, whose hydrogens are implicit and so have no index at
            all. Measured on ethanol: `compute_atomic_polarizability` (the
            registered "Polarizability (per atom)" calculator) yields 9
            values, indices 0-8, against 3 drawable atoms.

            The two arguments fail differently and both are silent about the
            real cause -- `atomNote` on a bad index raises straight out of
            RDKit, and an out-of-range highlight makes
            `PrepareAndDrawMolecule` reject the highlight list wholesale with
            `ValueError: list element larger than allowed value`, losing the
            entire depiction rather than the surplus atoms.

            Out-of-range values are DROPPED, not folded onto the hydrogen's
            heavy parent the way `nmr_signals.depiction_atoms` does. That
            mapping is right for a 1H spectrum, where the proton's shift is
            the only value its carbon has; here the heavy atom already
            carries its own value at its own index, so painting a hydrogen's
            colour over it would replace real data with a different atom's.
            The hydrogen values are not lost to the user -- the Calculator
            Inspector's 3D pane sits next to this one and is drawn from an
            explicit-hydrogen conformer, which does have somewhere to put
            them.
            """
            return 0 <= idx < atom_count

        if atom_labels:
            for idx, label in atom_labels.items():
                if drawable(idx):
                    mol.GetAtomWithIdx(idx).SetProp("atomNote", label)
        drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
        highlighted = {idx: color for idx, color in (atom_colors or {}).items() if drawable(idx)}
        highlight_atoms = list(highlighted)
        highlight_colors = {idx: self._hex_to_rgb_fraction(color) for idx, color in highlighted.items()}
        rdMolDraw2D.PrepareAndDrawMolecule(
            drawer, mol, highlightAtoms=highlight_atoms, highlightAtomColors=highlight_colors
        )
        drawer.FinishDrawing()
        return drawer.GetDrawingText()

    def render_2d_heatmap_svg(
        self,
        molblock: str,
        values: dict[int, float],
        colour_map: list[tuple[float, float, float]],
        atom_labels: dict[int, str] | None = None,
        width: int = 360,
        height: int = 320,
        grid_resolution: float = HEATMAP_GRID_RESOLUTION,
        gaussian_width: float = HEATMAP_GAUSSIAN_WIDTH,
    ) -> str:
        """The same depiction, painted with a CONTINUOUS field instead of
        discrete per-atom highlights.

        The flat counterpart to the 3D scalar-field surface, and the same
        argument for existing: a property defined over the molecule varies
        between the atoms as much as on them, and colouring atom discs
        turns that into a step function. This lays a Gaussian at each atom
        and contours the sum, which is the standard similarity/property
        map rendering.

        `colour_map` is REQUIRED and comes from the caller rather than
        being defaulted here, so this cannot drift into a second,
        independently-chosen palette beside the one the atom colouring and
        the 3D surface already share. `chem/` also must not import `ui/`,
        which is where that palette is defined.

        SIGN IS HANDLED, and was checked rather than assumed. RDKit's
        colour map is centred on zero and scaled by the largest magnitude
        present -- measured on a decane chain with weights of -0.1 and
        +0.9, the zero-weight atoms rendered neutral (R-B = -0.4) while
        the faint negative stayed faintly red (+11.6) against the strong
        positive's -116.4. So an asymmetric property does not shift the
        white point off zero, and a single-signed property honestly reads
        as all one colour rather than being stretched across the full
        diverging range.

        WHAT A BLANK REGION MEANS. An atom with no entry in `values`
        contributes nothing, and nothing reads as ZERO here, not as
        "unknown" -- the two are indistinguishable once drawn. Hand in a
        complete map, or accept that the gaps assert a value.
        """
        from rdkit.Chem.Draw import rdMolDraw2D
        from rdkit.Geometry import Point2D

        mol = self.mol_from_molblock(molblock)
        atom_count = mol.GetNumAtoms()
        if atom_labels:
            for idx, label in atom_labels.items():
                if 0 <= idx < atom_count:
                    mol.GetAtomWithIdx(idx).SetProp("atomNote", label)

        # Surplus indices are dropped for the reason `render_2d_svg`'s
        # `drawable` documents at length: several calculators run on
        # `Chem.AddHs(mol)` and return a value per hydrogen, while this
        # depiction's hydrogens are implicit and have no index.
        conformer = mol.GetConformer()
        locations = [
            Point2D(conformer.GetAtomPosition(i).x, conformer.GetAtomPosition(i).y)
            for i in range(atom_count)
        ]
        weights = [float(values.get(i, 0.0)) for i in range(atom_count)]
        widths = [gaussian_width] * atom_count

        params = rdMolDraw2D.ContourParams()
        params.fillGrid = True
        params.gridResolution = grid_resolution
        params.extraGridPadding = HEATMAP_GRID_PADDING
        params.setColourMap(colour_map)
        # Leaves the page bare where the field has decayed to nothing,
        # rather than painting the grid's whole rectangle -- see the
        # constant, which records the visible box this removes.
        params.useFillThreshold = True
        params.fillThresholdIsFraction = True
        params.fillThreshold = HEATMAP_FILL_THRESHOLD

        drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
        drawer.ClearDrawing()
        # `nContours=0` leaves the fill without isolines. The rings are a
        # spectroscopy convention (see `ui/contours.py`); on a property map
        # they read as boundaries in a quantity that has none.
        rdMolDraw2D.ContourAndDrawGaussians(
            drawer, locations, weights, widths, 0, [], params, mol
        )
        # Without this the molecule's own background wipes the field it was
        # just drawn over -- the structure must be composited ON TOP.
        drawer.drawOptions().clearBackground = False
        rdMolDraw2D.PrepareAndDrawMolecule(drawer, mol)
        drawer.FinishDrawing()
        return drawer.GetDrawingText()

    @staticmethod
    def _hex_to_rgb_fraction(color: str) -> tuple[float, float, float]:
        return tuple(int(color[i : i + 2], 16) / 255.0 for i in (1, 3, 5))

    def mol_from_smiles(self, smiles: str) -> Chem.Mol:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise InvalidStructureError(f"Could not parse SMILES: {smiles!r}")
        return mol

    def formal_charge(self, model: MoleculeModel) -> int:
        """Sum of RDKit formal charges — used as a sensible default charge
        for a quantum-chemistry job (6.5), never guessed in the UI layer
        since only this module ever imports rdkit."""
        return Chem.GetFormalCharge(self.mol_from_model(model))

    def canonicalize(self, model: MoleculeModel) -> MoleculeModel:
        """Recompute canonical_smiles/inchi/inchikey from model.molblock, in place."""
        mol = self.mol_from_model(model)
        model.canonical_smiles = Chem.MolToSmiles(mol)
        inchi = Chem.MolToInchi(mol)
        model.inchi = inchi or None
        model.inchikey = Chem.InchiToInchiKey(inchi) if inchi else None
        return model

    def rescale_like(self, molblock: str, reference: str) -> tuple[str, float]:
        """Put `molblock` back on `reference`'s scale, returning the residual.

        **KETCHER NORMALISES BOND LENGTHS TO ITS OWN UNIT AND WRITES THAT
        OUT.** Measured against the real vendored bundle, a cyclohexane
        loaded with C-C at 1.5301 A comes back from `getMolfile` at 1.0702
        -- a uniform x0.6994 on every bond. For a 2D drawing that is
        meaningless (a layout is not a measurement), which is why nothing
        noticed for as long as the editor only ever held layouts. For a
        rotated 3D structure it is a 30% error in every bond length, and
        it is invisible to atom order, to the CIP labels and to the
        oriented volume -- a uniform scale changes none of them. Only an
        energy or a length sees one.

        The factor is fitted by least squares over EVERY pairwise
        distance rather than read off one bond: a single bond is one
        rounding error away from the answer, and a molblock carries four
        decimal places at a scale ~0.7, so the error is amplified by ~1.43
        on the way back.

        The residual comes back with it -- the largest distance still
        disagreeing after rescaling -- because that is the number that
        says whether the motion was rigid at all. A caller that meant to
        apply a rotation can refuse on it; nothing here decides that.

        Returns `(molblock, inf)` unchanged when the two cannot be
        compared at all (different atom counts, no conformer), because
        "cannot tell" must not read as "verified".
        """
        mol = self.mol_from_molblock(molblock)
        ref = self.mol_from_molblock(reference)
        if (
            mol.GetNumAtoms() != ref.GetNumAtoms()
            or not mol.GetNumConformers()
            or not ref.GetNumConformers()
        ):
            return molblock, math.inf
        conformer, ref_conformer = mol.GetConformer(), ref.GetConformer()
        points = [tuple(conformer.GetAtomPosition(i)) for i in range(mol.GetNumAtoms())]
        ref_points = [tuple(ref_conformer.GetAtomPosition(i)) for i in range(ref.GetNumAtoms())]
        pairs = [(i, j) for i in range(len(points)) for j in range(i + 1, len(points))]
        here = sum(math.dist(points[i], points[j]) ** 2 for i, j in pairs)
        there = sum(math.dist(ref_points[i], ref_points[j]) ** 2 for i, j in pairs)
        if here <= 0.0 or there <= 0.0:
            return molblock, math.inf
        factor = math.sqrt(there / here)
        centre = [sum(axis) / len(points) for axis in zip(*points)]
        for i, point in enumerate(points):
            conformer.SetAtomPosition(
                i, tuple(centre[k] + (point[k] - centre[k]) * factor for k in range(3))
            )
        scaled = [tuple(conformer.GetAtomPosition(i)) for i in range(mol.GetNumAtoms())]
        residual = max(
            abs(math.dist(scaled[i], scaled[j]) - math.dist(ref_points[i], ref_points[j]))
            for i, j in pairs
        )
        return Chem.MolToMolBlock(mol), residual

    def set_structure_from_molblock(self, model: MoleculeModel, molblock: str) -> MoleculeModel:
        mol = self.mol_from_molblock(molblock)
        model.molblock = Chem.MolToMolBlock(mol)
        return self.canonicalize(model)

    def set_structure_from_smiles(self, model: MoleculeModel, smiles: str) -> MoleculeModel:
        mol = self.mol_from_smiles(smiles)
        model.molblock = Chem.MolToMolBlock(mol)
        return self.canonicalize(model)

    def bond_length(self, molblock: str, atom_idx_1: int, atom_idx_2: int) -> float:
        """Distance (Angstroms) between two atoms in a 3D conformer molblock."""
        conf = self.mol_from_molblock(molblock).GetConformer()
        return rdMolTransforms.GetBondLength(conf, atom_idx_1, atom_idx_2)

    def bond_angle(self, molblock: str, atom_idx_1: int, atom_idx_2: int, atom_idx_3: int) -> float:
        """Angle (degrees) atom1-atom2-atom3 in a 3D conformer molblock."""
        conf = self.mol_from_molblock(molblock).GetConformer()
        return rdMolTransforms.GetAngleDeg(conf, atom_idx_1, atom_idx_2, atom_idx_3)

    def dihedral_angle(
        self, molblock: str, atom_idx_1: int, atom_idx_2: int, atom_idx_3: int, atom_idx_4: int
    ) -> float:
        """Dihedral angle (degrees) atom1-atom2-atom3-atom4 in a 3D conformer molblock."""
        conf = self.mol_from_molblock(molblock).GetConformer()
        return rdMolTransforms.GetDihedralDeg(conf, atom_idx_1, atom_idx_2, atom_idx_3, atom_idx_4)
