from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from rdkit import Chem

# Heavy-atom-to-heavy-atom distance heuristic for a "polar contact" --
# deliberately NOT a true donor-H...acceptor angle check: the receptor has
# no experimental hydrogen positions (they'd have to be added
# geometrically, same as receptor prep already does for docking itself),
# so an angle computed from placed-not-observed hydrogens would look more
# precise than it actually is. This is the same simplification common
# quick-analysis tools (e.g. PyMOL's default polar contacts) use -- a
# heavy-atom distance cutoff, no angle, symmetric on both sides (doesn't
# try to distinguish donor from acceptor).
HBOND_DISTANCE_CUTOFF = 3.5  # Angstrom
CLASH_TOLERANCE = 0.4  # Angstrom subtracted from summed van der Waals radii
_POLAR_ELEMENTS = {"N", "O", "F"}

# Bondi van der Waals radii (Angstrom) for elements likely to appear in a
# docking receptor/ligand -- anything else falls back to
# _DEFAULT_VDW_RADIUS.
_VDW_RADII = {
    "H": 1.10, "C": 1.70, "N": 1.55, "O": 1.52, "S": 1.80, "P": 1.80,
    "F": 1.47, "CL": 1.75, "BR": 1.85, "I": 1.98, "ZN": 1.39, "MG": 1.73,
    "CA": 2.31, "FE": 1.56, "NA": 2.27, "K": 2.75,
}
_DEFAULT_VDW_RADIUS = 1.70

Position = tuple[float, float, float]


@dataclass(slots=True)
class ReceptorAtom:
    element: str
    position: Position
    residue_name: str
    residue_number: int


def receptor_atoms_from_structure(structure_text: str, source_format: str) -> list[ReceptorAtom]:
    """Plain (position, element, residue) data for the receptor, via Open
    Babel -- already this codebase's receptor parser
    (chem/docking_providers.py), format-agnostic across PDB/mmCIF, unlike
    RDKit's own `MolFromPDBBlock` (PDB only -- the installed RDKit version
    has no mmCIF block reader, confirmed directly). Parse once per docking
    job and reuse across every pose, not once per pose.
    """
    from openbabel import pybel

    table = Chem.GetPeriodicTable()
    mol = pybel.readstring(source_format, structure_text)
    atoms = []
    for atom in mol.atoms:
        if atom.atomicnum == 0:
            continue
        residue = atom.residue
        atoms.append(
            ReceptorAtom(
                element=table.GetElementSymbol(atom.atomicnum).upper(),
                position=atom.coords,
                residue_name=residue.name.strip() if residue else "",
                residue_number=residue.idx if residue else 0,
            )
        )
    return atoms


def _ligand_heavy_atoms(pose_molblock: str) -> list[tuple[str, Position]]:
    mol = Chem.MolFromMolBlock(pose_molblock, sanitize=False, removeHs=False)
    if mol is None or mol.GetNumConformers() == 0:
        return []
    conformer = mol.GetConformer()
    atoms = []
    for atom in mol.GetAtoms():
        symbol = atom.GetSymbol().upper()
        if symbol == "H":
            continue
        pos = conformer.GetAtomPosition(atom.GetIdx())
        atoms.append((symbol, (pos.x, pos.y, pos.z)))
    return atoms


def _vdw_radius(element: str) -> float:
    return _VDW_RADII.get(element, _DEFAULT_VDW_RADIUS)


def analyze_pose(pose_molblock: str, receptor_atoms: list[ReceptorAtom]) -> dict[str, Any]:
    """Returns `{"hbonds": [...], "clashes": [...]}` for one docked pose
    against an already-parsed receptor atom list (see
    `receptor_atoms_from_structure`). Each entry is a plain dict (not a
    dataclass) since this lands directly in `DockingPoseModel.metadata`,
    an open `dict[str, Any]` meant for JSON-serializable data.
    """
    hbonds: list[dict[str, Any]] = []
    clashes: list[dict[str, Any]] = []

    for ligand_element, ligand_position in _ligand_heavy_atoms(pose_molblock):
        ligand_radius = _vdw_radius(ligand_element)
        ligand_is_polar = ligand_element in _POLAR_ELEMENTS
        for receptor_atom in receptor_atoms:
            distance = math.dist(ligand_position, receptor_atom.position)
            contact = {
                "ligand_element": ligand_element,
                "receptor_element": receptor_atom.element,
                "receptor_residue": f"{receptor_atom.residue_name}{receptor_atom.residue_number}",
                "distance": round(distance, 2),
            }
            if (
                ligand_is_polar
                and receptor_atom.element in _POLAR_ELEMENTS
                and distance <= HBOND_DISTANCE_CUTOFF
            ):
                hbonds.append(contact)
            receptor_radius = _vdw_radius(receptor_atom.element)
            if distance < (ligand_radius + receptor_radius - CLASH_TOLERANCE):
                clashes.append(contact)

    return {"hbonds": hbonds, "clashes": clashes}
