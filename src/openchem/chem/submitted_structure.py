"""Identity of a submitted Quantum input, without coordinates.

Used by history compare so two jobs on the same molecule UUID are not treated
as the same structure after a rewrite. Canonical SMILES carries constitution,
formal charges, isotopes, and stereochemistry. Coordinates do not.
"""

from __future__ import annotations

from rdkit import Chem


def submitted_structure_identity(molblock: str) -> str:
    """Canonical SMILES of a run's `input_molblock`, or empty when it cannot be read.

    Empty is cannot-tell: two missing snapshots are not a match. Isotope labels
    stay in the SMILES; this is not `same_structure`, which treats a mass label
    as the same molecule.
    """
    if not molblock or not molblock.strip():
        return ""
    mol = Chem.MolFromMolBlock(molblock, removeHs=False)
    if mol is None:
        return ""
    try:
        if mol.GetNumConformers():
            Chem.AssignStereochemistryFrom3D(mol)
        return Chem.MolToSmiles(mol)
    except Exception:  # noqa: BLE001 - unreadable snapshot is cannot-tell
        return ""
