"""Score the ab initio ESP against the point-charge ESP on the same
conformer, and locate where they disagree.

THE QUESTION THIS ANSWERS. `chem/scalar_field.py` computes an
electrostatic potential by summing point-charge Coulomb terms, and its
docstring states the limitation plainly: "A point charge has no shape: it
cannot represent a lone pair's directionality or a sigma hole". README.md
repeats it as a caveat. Both claims were reasoned from the form of the
equation, never measured. This measures them.

Agreement alone would prove nothing -- two methods that both put negative
potential near oxygen will correlate whatever their shape. So the score
has two halves and the second is the real one:

  1. **Gross agreement**, as a correlation over molecular-surface points.
     Establishes that the QM path is reading the right molecule and is not
     simply noise.
  2. **The specific disagreement**, at exactly the two features the
     caveat names. A sigma hole is a POSITIVE cap on a halogen that is
     negative everywhere else; a point charge, having one sign, cannot
     produce a sign change around a single atom. If the QM surface shows
     one and the point-charge surface does not, that is the evidence --
     and it is falsifiable, because the hole must also deepen F < Cl < Br.

THE SURFACE. Points are taken where the electron density is near
0.002 e/Bohr^3, the standard isodensity definition of a molecular
surface. Whole-grid statistics would be dominated by the region near the
nuclei, where the potential is huge, both methods are meaningless, and
nothing is ever rendered.

Usage:
    python benchmarks/esp/score.py <work directory from generate.py>
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from rdkit import Chem, RDLogger
from rdkit.Geometry import Point3D

from openchem.chem.cube import read_cube
from openchem.chem.descriptor_providers import compute_gasteiger_charges
from openchem.chem.scalar_field import potential_at_points

RDLogger.DisableLog("rdApp.*")

#: Hartree/e -> kcal/(mol*e), so both methods are read in the units
#: `scalar_field` already uses. Exact by definition of the units.
HARTREE_TO_KCAL = 627.509474

#: The isodensity molecular surface, in e/Bohr^3 -- Bader's 0.002, the
#: value essentially every ESP-mapped surface in the literature uses.
SURFACE_DENSITY = 0.002
#: Half-width of the shell, as a fraction of `SURFACE_DENSITY`. A band
#: rather than an exact level because the grid samples the density at
#: fixed points and almost none of them land exactly on an isosurface.
SURFACE_BAND = 0.25

_HALOGENS = {"F", "Cl", "Br", "I"}


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    """Written out rather than imported, matching `benchmarks/ir/score.py`
    -- the benchmarks run on the project's own dependencies."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    a_centred = a - a.mean()
    b_centred = b - b.mean()
    denominator = math.sqrt(float((a_centred**2).sum()) * float((b_centred**2).sum()))
    return float((a_centred * b_centred).sum() / denominator) if denominator else 0.0


def _grid_points(field) -> np.ndarray:
    """Every grid point of a field, as (n, 3) in Angstrom, in the same
    order as `field.values.ravel()`."""
    counts = field.values.shape
    axes = [
        field.origin[axis] + np.arange(counts[axis]) * field.spacing[axis]
        for axis in range(3)
    ]
    return np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)


def _molecule_at_cube_geometry(directory: Path, cube) -> Chem.Mol:
    """The starting molecule, moved onto the geometry ORCA optimised.

    The cube's own atom block IS that geometry (already converted to
    Angstrom by the reader), so no second parse of `job.out` is needed.
    Bond orders come from `start.mol` because a cube has none, and
    Gasteiger charges are a function of bonding as much as of elements.
    """
    mol = Chem.MolFromMolFile(str(directory / "start.mol"), removeHs=False)
    if mol is None:
        raise SystemExit(f"could not read {directory / 'start.mol'}")
    if mol.GetNumAtoms() != len(cube.atoms):
        raise SystemExit(
            f"{directory.name}: {mol.GetNumAtoms()} atoms in start.mol but "
            f"{len(cube.atoms)} in the cube -- these are not the same molecule"
        )
    conformer = mol.GetConformer()
    for index, atom in enumerate(cube.atoms):
        if atom.atomic_number != mol.GetAtomWithIdx(index).GetAtomicNum():
            raise SystemExit(
                f"{directory.name}: atom {index} is "
                f"Z={mol.GetAtomWithIdx(index).GetAtomicNum()} in start.mol but "
                f"Z={atom.atomic_number} in the cube -- atom order differs"
            )
        conformer.SetAtomPosition(index, Point3D(*atom.position))
    return mol


def _surface_mask(density_values: np.ndarray) -> np.ndarray:
    low = SURFACE_DENSITY * (1.0 - SURFACE_BAND)
    high = SURFACE_DENSITY * (1.0 + SURFACE_BAND)
    return (density_values >= low) & (density_values <= high)


def _sigma_hole_profile(
    mol: Chem.Mol, points: np.ndarray, qm: np.ndarray, pc: np.ndarray
) -> dict | None:
    """ESP as a function of angle from the C-X bond axis, around a halogen.

    Zero degrees is the extension of the C-X bond BEYOND the halogen --
    the sigma hole's location. Ninety degrees is the equatorial belt. A
    point-charge model puts one charge on the halogen, so its potential
    around that atom is monotonic in distance and cannot change sign with
    angle; that is the whole prediction being tested.
    """
    halogen = next(
        (atom for atom in mol.GetAtoms() if atom.GetSymbol() in _HALOGENS), None
    )
    if halogen is None:
        return None
    neighbours = halogen.GetNeighbors()
    if len(neighbours) != 1:
        return None

    conformer = mol.GetConformer()
    x_position = np.array(list(conformer.GetAtomPosition(halogen.GetIdx())))
    c_position = np.array(list(conformer.GetAtomPosition(neighbours[0].GetIdx())))
    axis = x_position - c_position
    axis /= np.linalg.norm(axis)

    offsets = points - x_position
    distances = np.linalg.norm(offsets, axis=1)
    # Only the halogen's own patch of surface: points closer to this atom
    # than to any other, so the ring's potential is not folded in.
    all_positions = np.array(
        [list(conformer.GetAtomPosition(i)) for i in range(mol.GetNumAtoms())]
    )
    nearest = np.argmin(
        np.linalg.norm(points[:, None, :] - all_positions[None, :, :], axis=2), axis=1
    )
    own = nearest == halogen.GetIdx()
    if not own.any():
        return None

    cosines = (offsets[own] @ axis) / distances[own]
    angles = np.degrees(np.arccos(np.clip(cosines, -1.0, 1.0)))

    bins = [(0, 30), (30, 60), (60, 90), (90, 120)]
    profile = []
    for low, high in bins:
        selected = (angles >= low) & (angles < high)
        if selected.sum() < 3:
            profile.append((low, high, None, None, int(selected.sum())))
            continue
        profile.append(
            (
                low,
                high,
                float(qm[own][selected].mean()),
                float(pc[own][selected].mean()),
                int(selected.sum()),
            )
        )
    return {"symbol": halogen.GetSymbol(), "profile": profile}


def _lone_pair_profile(
    mol: Chem.Mol, points: np.ndarray, qm: np.ndarray, pc: np.ndarray
) -> dict | None:
    """ESP by angle out of the H-O-H plane, on the side away from the H's.

    Water's lone pairs sit above and below the molecular plane. A
    three-point-charge model is symmetric about that plane and has no
    feature there at all, so its potential can only fall off smoothly;
    if the QM potential has its minimum OUT of plane, the two disagree in
    exactly the way the caveat claims.
    """
    oxygens = [atom for atom in mol.GetAtoms() if atom.GetSymbol() == "O"]
    if len(oxygens) != 1:
        return None
    oxygen = oxygens[0]
    hydrogens = [n.GetIdx() for n in oxygen.GetNeighbors() if n.GetSymbol() == "H"]
    if len(hydrogens) != 2:
        return None

    conformer = mol.GetConformer()
    o_position = np.array(list(conformer.GetAtomPosition(oxygen.GetIdx())))
    bonds = [
        np.array(list(conformer.GetAtomPosition(h))) - o_position for h in hydrogens
    ]
    bonds = [bond / np.linalg.norm(bond) for bond in bonds]
    # Away from both hydrogens: the lone-pair side.
    bisector = -(bonds[0] + bonds[1])
    bisector /= np.linalg.norm(bisector)
    normal = np.cross(bonds[0], bonds[1])
    normal /= np.linalg.norm(normal)

    offsets = points - o_position
    distances = np.linalg.norm(offsets, axis=1)
    directions = offsets / distances[:, None]
    lone_pair_side = (directions @ bisector) > 0.3
    if lone_pair_side.sum() < 10:
        return None

    # Angle out of the molecular plane, unsigned: the two lone pairs are
    # mirror images and folding them together doubles the sample.
    out_of_plane = np.degrees(np.arcsin(np.clip(np.abs(directions @ normal), 0.0, 1.0)))

    bins = [(0, 15), (15, 30), (30, 45), (45, 60), (60, 90)]
    profile = []
    for low, high in bins:
        selected = lone_pair_side & (out_of_plane >= low) & (out_of_plane < high)
        if selected.sum() < 3:
            profile.append((low, high, None, None, int(selected.sum())))
            continue
        profile.append(
            (
                low,
                high,
                float(qm[selected].mean()),
                float(pc[selected].mean()),
                int(selected.sum()),
            )
        )
    return {"profile": profile}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("work", type=Path)
    args = parser.parse_args()

    manifest_path = args.work / "manifest.json"
    if not manifest_path.is_file():
        print(f"no manifest at {manifest_path} -- run generate.py first", file=sys.stderr)
        return 2
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    print("SURFACE AGREEMENT  (isodensity 0.002 e/Bohr^3, kcal/(mol*e))")
    print(f"{'molecule':16s} {'n':>7s} {'r':>8s} {'QM min':>9s} {'QM max':>9s} "
          f"{'PC min':>9s} {'PC max':>9s}")

    sigma_holes: list[tuple[str, str, float, float]] = []
    details: list[str] = []

    for name, entry in manifest.items():
        directory = args.work / name
        esp_cube = read_cube(directory / entry["esp_cube"], units="Hartree/e")
        density_cube = read_cube(directory / entry["density_cube"], units="e/Bohr^3")

        if esp_cube.field.values.shape != density_cube.field.values.shape:
            print(f"{name}: ESP and density grids differ in shape -- skipped", file=sys.stderr)
            continue
        if not np.allclose(esp_cube.field.origin, density_cube.field.origin, atol=1e-6):
            print(f"{name}: ESP and density grids have different origins -- skipped", file=sys.stderr)
            continue

        mol = _molecule_at_cube_geometry(directory, esp_cube)
        charges = compute_gasteiger_charges(mol)
        conformer = mol.GetConformer()
        positions = [tuple(conformer.GetAtomPosition(i)) for i in range(mol.GetNumAtoms())]
        charge_list = [charges[i] for i in range(mol.GetNumAtoms())]

        points = _grid_points(esp_cube.field)
        mask = _surface_mask(density_cube.field.values.ravel())
        if mask.sum() < 50:
            print(f"{name}: only {mask.sum()} surface points -- skipped", file=sys.stderr)
            continue

        surface_points = points[mask]
        qm = esp_cube.field.values.ravel()[mask] * HARTREE_TO_KCAL
        pc = potential_at_points(surface_points, positions, charge_list)

        r = _pearson(qm, pc)
        print(f"{name:16s} {mask.sum():7d} {r:+8.3f} {qm.min():9.1f} {qm.max():9.1f} "
              f"{pc.min():9.1f} {pc.max():9.1f}")

        hole = _sigma_hole_profile(mol, surface_points, qm, pc)
        if hole is not None:
            details.append(f"\nSIGMA HOLE -- {name} ({hole['symbol']}), ESP by angle from the C-X axis")
            details.append(f"  {'angle':>10s} {'QM':>9s} {'point charge':>14s} {'n':>7s}")
            first_qm = None
            belt_qm = None
            for low, high, qm_mean, pc_mean, count in hole["profile"]:
                if qm_mean is None:
                    details.append(f"  {low:3d}-{high:3d} deg {'--':>9s} {'--':>14s} {count:7d}")
                    continue
                details.append(
                    f"  {low:3d}-{high:3d} deg {qm_mean:+9.2f} {pc_mean:+14.2f} {count:7d}"
                )
                if low == 0:
                    first_qm = qm_mean
                if low == 60:
                    belt_qm = qm_mean
            if first_qm is not None and belt_qm is not None:
                sigma_holes.append((name, hole["symbol"], first_qm, belt_qm))

        lone_pair = _lone_pair_profile(mol, surface_points, qm, pc)
        if lone_pair is not None:
            details.append(f"\nLONE PAIRS -- {name}, ESP by angle out of the H-O-H plane")
            details.append(f"  {'angle':>10s} {'QM':>9s} {'point charge':>14s} {'n':>7s}")
            for low, high, qm_mean, pc_mean, count in lone_pair["profile"]:
                if qm_mean is None:
                    details.append(f"  {low:3d}-{high:3d} deg {'--':>9s} {'--':>14s} {count:7d}")
                    continue
                details.append(
                    f"  {low:3d}-{high:3d} deg {qm_mean:+9.2f} {pc_mean:+14.2f} {count:7d}"
                )

    for line in details:
        print(line)

    if sigma_holes:
        print("\nSIGMA-HOLE SUMMARY  (cap = ESP at 0-30 deg, belt = at 60-90 deg)")
        print(f"  {'molecule':16s} {'X':>3s} {'cap':>9s} {'belt':>9s} {'cap-belt':>10s}")
        for name, symbol, cap, belt in sigma_holes:
            print(f"  {name:16s} {symbol:>3s} {cap:+9.2f} {belt:+9.2f} {cap - belt:+10.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
