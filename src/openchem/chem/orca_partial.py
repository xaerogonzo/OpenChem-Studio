"""The geometry an ORCA optimization had reached when it was stopped.

ORCA rewrites ``job.xyz`` after every geometry cycle and appends the same frame to ``job_trj.xyz``. When a person stops a
long optimization and asks to keep what it has, this reads that geometry back, and only if it can be trusted: the right
number of atoms, the same elements in the same order as the input, every coordinate finite. A file that fails any of these
is not used and the trajectory's last COMPLETE frame is tried instead; if neither is sound the answer is None and nothing
is kept. It never falls back to the input geometry or to an older file, because keeping the wrong structure as "the
optimized one" is worse than keeping nothing.

The reader takes the scratch folder and the submitted molecule; it starts no process and touches nothing outside the folder.
"""

from __future__ import annotations

import math
from pathlib import Path

from rdkit import Chem
from rdkit.Geometry import Point3D

#: ORCA's names for the files it keeps current in the job's folder (named after the input, ``job.inp``).
FINAL_XYZ = "job.xyz"
#: Every cycle's frame, appended; the fallback when the final file is missing or unsound.
TRAJECTORY_XYZ = "job_trj.xyz"

Coordinates = list[tuple[float, float, float]]


def _frames(text: str) -> list[tuple[list[str], Coordinates]]:
    """Every COMPLETE xyz frame in `text` (a count line, a comment, then exactly that many atom rows), in order.

    A frame cut off by a killed process is dropped here, never returned half-read.
    """
    lines = text.splitlines()
    frames: list[tuple[list[str], Coordinates]] = []
    index = 0
    while index < len(lines):
        header = lines[index].strip()
        if not header:
            index += 1
            continue
        try:
            count = int(header)
        except ValueError:
            break  # not an xyz frame: stop rather than guess
        rows = lines[index + 2:index + 2 + count]
        if count <= 0 or len(rows) < count:
            break
        elements: list[str] = []
        coordinates: Coordinates = []
        try:
            for row in rows:
                parts = row.split()
                if len(parts) < 4:
                    raise ValueError(row)
                elements.append(parts[0])
                coordinates.append((float(parts[1]), float(parts[2]), float(parts[3])))
        except ValueError:
            break
        frames.append((elements, coordinates))
        index += 2 + count
    return frames


def _sound(frame: tuple[list[str], Coordinates], mol: Chem.Mol) -> bool:
    elements, coordinates = frame
    if len(elements) != mol.GetNumAtoms():
        return False
    if any(el.capitalize() != atom.GetSymbol() for el, atom in zip(elements, mol.GetAtoms())):
        return False
    return all(math.isfinite(value) for xyz in coordinates for value in xyz)


def read_partial_geometry(scratch_dir: Path, mol: Chem.Mol) -> Coordinates | None:
    """The coordinates to keep, or None when no sound geometry can be read from `scratch_dir`."""
    directory = Path(scratch_dir)
    for name in (FINAL_XYZ, TRAJECTORY_XYZ):
        try:
            text = (directory / name).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        frames = _frames(text)
        if frames and _sound(frames[-1], mol):
            return frames[-1][1]
    return None


def mol_with_coordinates(mol: Chem.Mol, coordinates: Coordinates) -> Chem.Mol:
    """A copy of `mol` carrying `coordinates` (Angstrom, in the input's atom order)."""
    result = Chem.Mol(mol)
    conformer = Chem.Conformer(result.GetNumAtoms())
    for index, (x, y, z) in enumerate(coordinates):
        conformer.SetAtomPosition(index, Point3D(x, y, z))
    result.RemoveAllConformers()
    result.AddConformer(conformer, assignId=True)
    return result
