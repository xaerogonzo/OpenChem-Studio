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
        mol = Chem.MolFromMolBlock(molblock)
        if mol is None:
            raise InvalidStructureError("Could not parse molblock")
        return mol

    def mol_to_molblock(self, mol: Chem.Mol) -> str:
        return Chem.MolToMolBlock(mol)

    def mol_from_smiles(self, smiles: str) -> Chem.Mol:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise InvalidStructureError(f"Could not parse SMILES: {smiles!r}")
        return mol

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
