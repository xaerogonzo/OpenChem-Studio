from __future__ import annotations

import logging

from rdkit import Chem
from rdkit.Chem import rdMolTransforms

from openchem.domain.molecule import MoleculeModel

logger = logging.getLogger("openchem.chemistry")


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
        if atom_labels:
            for idx, label in atom_labels.items():
                if idx < mol.GetNumAtoms():
                    mol.GetAtomWithIdx(idx).SetProp("atomNote", label)
        drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
        highlight_atoms = list(atom_colors) if atom_colors else []
        highlight_colors = (
            {idx: self._hex_to_rgb_fraction(color) for idx, color in atom_colors.items()} if atom_colors else {}
        )
        rdMolDraw2D.PrepareAndDrawMolecule(
            drawer, mol, highlightAtoms=highlight_atoms, highlightAtomColors=highlight_colors
        )
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
