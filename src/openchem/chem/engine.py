from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from rdkit import Chem
from rdkit.Chem import AllChem, rdMolTransforms

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


@dataclass(frozen=True)
class ConformerDrawing:
    """A drawing made from a conformer, and whether it kept its orientation.

    The flag is not a detail: when it is False the drawing is a correct
    depiction of the right molecule that says nothing about the conformer
    chosen, and the user pressed a button asking for exactly that. Saying
    so is the difference between "this molecule cannot show its geometry
    flat" and "the button did nothing".
    """

    molblock: str
    follows_geometry: bool


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

    def drawing_from_conformer(self, molblock: str) -> ConformerDrawing:
        """A 2D drawing of a 3D conformer: heavy atoms, laid out to match it.

        A conformer cannot simply BE a drawing, for two measured reasons.

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
        heavy = Chem.RemoveHs(self.mol_from_molblock(molblock))

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
            return ConformerDrawing(Chem.MolToMolBlock(plain), follows_geometry=False)

        readable = _closest_approach(plain)
        if _closest_approach(oriented) < READABLE_LAYOUT_FRACTION * readable:
            logger.info(
                "The conformer's orientation cannot be drawn without overlap; "
                "using a plain layout instead."
            )
            return ConformerDrawing(Chem.MolToMolBlock(plain), follows_geometry=False)
        return ConformerDrawing(Chem.MolToMolBlock(oriented), follows_geometry=True)

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
