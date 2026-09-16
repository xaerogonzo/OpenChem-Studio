"""TRIAGE.md check 2.9: Wilmer et al. 2012's EQeq charges, on their own 12 MOFs.

    uv run --no-sync python benchmarks/charges/models/eqeq_check.py [--shells 2,3] [--factors 1,0.5]

Reads the structures from Sci Downloads (ACS accompanying files, not in the repository) and the
committed `tests/fixtures/charges/eqeq/ionization.csv`.

**THE PARAMETER TABLE IS A RECONSTRUCTION.** Wilmer's `ionizationData.dat` is not in the ACS
package, so the table is rebuilt from the two sources his SI cites (Moore 1970, Andersen 1999). A
per-atom miss therefore has two candidate causes, the implementation and the table, and 2.9's design
is what separates them: the distribution of |dq| is reported beside the pass count, and the paper's
own Table 2 (mean |Q - Q_REPEAT| per MOF) is an independent diagnostic that does not depend on our
table being theirs.

**Ewald is deliberately not implemented.** The 2pi convention of its reciprocal vectors is
unresolved (FEASIBILITY section 2), and the paper states that at 7x7x7 cells "charges from both
Ewald and direct summation methods were identical" -- so the direct sum at L = 3 is the paper's own
bridge between the two.
"""

from __future__ import annotations

import argparse
import collections
import csv
import io
import itertools
import math
import pathlib
import re
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]
HERE = pathlib.Path(__file__).resolve().parent
STRUCTURES = pathlib.Path(r"D:\Xaero Stuff\Documents\Sci Downloads\wilmer2012_si\jz3008485_si_002"
                          r"\CrystalStructuresWithCharges")
TABLE = ROOT / "tests" / "fixtures" / "charges" / "eqeq" / "ionization.csv"

#: The paper's own settings (p. 3 and SI S3), not chosen here.
DIELECTRIC = 1.67
#: Hydrogen's affinity is overridden, the paper's second ad hoc parameter ("the measured value is +0.754").
HYDROGEN_I0 = -2.0
#: Charge centres: neutral except the metals, at their oxidation states.
CHARGE_CENTRES = {"Mg": 2, "V": 4, "Co": 2, "Ni": 2, "Cu": 2, "Zn": 2, "Pd": 2}
#: K = 1/(4 pi eps_r eps_0) in eV angstrom.
COULOMB_EV_ANGSTROM = 14.399645
#: The printed charges carry 3 decimals.
TOLERANCE = 5e-4


def parameter_table() -> dict[str, dict]:
    text = "".join(line for line in TABLE.read_text(encoding="utf-8").splitlines(keepends=True)
                   if not line.startswith("#"))
    out: dict[str, dict] = {}
    for row in csv.DictReader(io.StringIO(text)):
        potentials = [float(row[f"I{stage}"]) for stage in range(1, 11) if row[f"I{stage}"]]
        out[row["element"]] = {
            "Z": int(row["Z"]),
            "affinity": float(row["electron_affinity_eV"]) if row["electron_affinity_eV"] else None,
            "affinity_as_printed": row["affinity_as_printed"],
            "potentials": potentials,
        }
    return out


def energies(element: str, table: dict[str, dict]) -> dict[int, float]:
    """I_n by n, with I_0 the electron affinity: the energy to go from a charge of -1 to 0."""
    entry = table[element]
    out = {stage: value for stage, value in enumerate(entry["potentials"], start=1)}
    affinity = HYDROGEN_I0 if element == "H" else entry["affinity"]
    if affinity is not None:
        out[0] = affinity
    return out


def electronegativity_and_hardness(element: str, centre: int, table: dict[str, dict]) -> tuple[float, float]:
    """SI eqs 57-58 about a charge centre Q*: chi = (I_{Q*+1} + I_{Q*})/2 and J = I_{Q*+1} - I_{Q*}."""
    available = energies(element, table)
    if centre not in available or centre + 1 not in available:
        missing = "the electron affinity" if centre == 0 else f"I{centre + 1}"
        raise KeyError(f"{element} at charge centre {centre:+d} needs {missing}, which the sources do not give")
    lower, upper = available[centre], available[centre + 1]
    return 0.5 * (upper + lower), upper - lower


# --- the structures -------------------------------------------------------------------------------


def read_structure(path: pathlib.Path) -> dict:
    """One RASPA listing: elements, Cartesian coordinates, charges and the cell.

    Despite the `.mol` extension these are not MDL molfiles; the cell prints at the end of the file
    under a "Fundcell_Info:" label, as lengths, angles, origin, and the lengths again.
    """
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    count = int(lines[2])
    elements, coordinates, charges = [], [], []
    for line in lines[3:3 + count]:
        fields = line.split()
        coordinates.append([float(fields[1]), float(fields[2]), float(fields[3])])
        elements.append(fields[4].replace("Mof_", ""))
        charges.append(float(fields[5]))
    # The cell prints under a "Fundcell_Info:" label as lengths, angles, origin, then lengths again --
    # read by that label, because taking the last three lines puts the angles where the lengths go.
    start = next(index for index, line in enumerate(lines) if "Fundcell_Info" in line)
    block = [list(map(float, line.split())) for line in lines[start + 1:start + 4]]
    lengths, angles, _origin = block
    return {"name": path.stem, "elements": elements, "coordinates": np.array(coordinates),
            "charges": np.array(charges), "angles": angles, "lengths": lengths}


def cell_vectors(lengths, angles) -> np.ndarray:
    """The three lattice vectors. Every cell in this corpus is orthorhombic or cubic (all 90 degrees)."""
    a, b, c = lengths
    alpha, beta, gamma = (math.radians(value) for value in angles)
    vector_a = np.array([a, 0.0, 0.0])
    vector_b = np.array([b * math.cos(gamma), b * math.sin(gamma), 0.0])
    cx = c * math.cos(beta)
    cy = c * (math.cos(alpha) - math.cos(beta) * math.cos(gamma)) / math.sin(gamma)
    vector_c = np.array([cx, cy, math.sqrt(max(c * c - cx * cx - cy * cy, 0.0))])
    return np.array([vector_a, vector_b, vector_c])


# --- the model ------------------------------------------------------------------------------------


def orbital_overlap(hardness_pair: np.ndarray, distance: np.ndarray, coulomb: float) -> np.ndarray:
    """SI eq 64's damping, E_O(r), with J_km the geometric mean of the two hardnesses."""
    safe = np.where(np.isfinite(distance), distance, 1.0)  # the home-cell self pair is masked by the caller
    scaled = hardness_pair * safe / coulomb
    return np.exp(-(scaled ** 2)) * (hardness_pair / coulomb - hardness_pair ** 2 * safe / coulomb ** 2
                                     - 1.0 / safe)


def pair_matrix(structure: dict, hardness: np.ndarray, shells: int, coulomb: float) -> np.ndarray:
    """K [1/r + E_O(r)] summed over every periodic image within `shells`, self-image included.

    The home-cell self term is skipped ("m != k*" in the paper): an atom interacts with its own
    images but not with itself.
    """
    positions = structure["coordinates"]
    vectors = cell_vectors(structure["lengths"], structure["angles"])
    count = len(positions)
    geometric_mean = np.sqrt(np.abs(np.outer(hardness, hardness)))
    total = np.zeros((count, count))
    for u, v, w in itertools.product(range(-shells, shells + 1), repeat=3):
        shift = u * vectors[0] + v * vectors[1] + w * vectors[2]
        delta = positions[:, None, :] - positions[None, :, :] + shift
        distance = np.linalg.norm(delta, axis=-1)
        if u == v == w == 0:
            np.fill_diagonal(distance, np.inf)  # an atom does not interact with itself in the home cell
        contribution = coulomb / distance + coulomb * orbital_overlap(geometric_mean, distance, coulomb)
        total += np.where(np.isfinite(distance), contribution, 0.0)
    return total


def solve(structure: dict, table: dict[str, dict], shells: int, factor: float,
          pairs: np.ndarray | None = None) -> np.ndarray:
    """The equalisation system: chi_k + J_k (Q_k - Q*_k) + factor * sum_m A_km Q_m = X, with sum Q = 0.

    `pairs` lets a caller reuse one lattice sum across both readings of the factor, which is the
    expensive half: the sum does not depend on it.
    """
    elements = structure["elements"]
    centres = np.array([CHARGE_CENTRES.get(element, 0) for element in elements], dtype=float)
    parameters = [electronegativity_and_hardness(element, int(centre), table)
                  for element, centre in zip(elements, centres)]
    chi = np.array([value[0] for value in parameters])
    hardness = np.array([value[1] for value in parameters])
    coulomb = COULOMB_EV_ANGSTROM / DIELECTRIC
    count = len(elements)

    matrix = np.zeros((count + 1, count + 1))
    matrix[:count, :count] = factor * (pair_matrix(structure, hardness, shells, coulomb) if pairs is None else pairs)
    matrix[np.diag_indices(count)] += hardness
    matrix[:count, count] = -1.0
    matrix[count, :count] = 1.0
    rhs = np.zeros(count + 1)
    rhs[:count] = -chi + hardness * centres
    return np.linalg.solve(matrix, rhs)[:count]


# --- the check ------------------------------------------------------------------------------------


def structures() -> list[dict]:
    return [read_structure(path) for path in sorted(STRUCTURES.glob("*_EQeq.mol"))]


def match_by_position(target: dict, source: dict) -> np.ndarray:
    """source-atom index for each target atom, by minimum-image distance.

    **THE FOUR CHARGE FILES OF A MOF DO NOT SHARE AN ATOM ORDER**, and their coordinate lists are
    permutations of each other. Comparing them index by index compares unrelated atoms -- measured
    first as a mean |EQeq - REPEAT| of 0.47 on MIL-47 where the paper's Table 2 prints 0.11. Matched
    by position the same quantity is 0.112, and every one of the 12 then reproduces Table 2.
    """
    vectors = cell_vectors(target["lengths"], target["angles"])
    inverse = np.linalg.inv(vectors.T)
    delta = target["coordinates"][:, None, :] - source["coordinates"][None, :, :]
    fractional = delta @ inverse.T
    fractional -= np.round(fractional)
    distance = np.linalg.norm(fractional @ vectors, axis=-1)
    match = distance.argmin(axis=1)
    if len(set(match.tolist())) != len(match) or distance[np.arange(len(match)), match].max() > 1e-3:
        raise ValueError(f"{target['name']}: the two files' atoms do not correspond one to one")
    return match


def reference_deviation(name: str, charges: np.ndarray) -> float | None:
    """Mean |q - q_REPEAT| for one MOF: the paper's Table 2 column, on position-matched atoms."""
    path = STRUCTURES / f"{name.replace('_EQeq', '')}_REPEAT.mol"
    if not path.exists():
        return None
    target = read_structure(STRUCTURES / f"{name.replace('_EQeq', '')}_EQeq.mol")
    repeat = read_structure(path)
    if len(repeat["charges"]) != len(charges):
        return None
    return float(np.mean(np.abs(charges - repeat["charges"][match_by_position(target, repeat)])))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shells", default="2,3", help="lattice sums to run (2 is the paper's 5x5x5)")
    parser.add_argument("--factors", default="1,0.5", help="the two readings of eq 62's pair factor")
    parser.add_argument("--only", default="", help="run one MOF")
    arguments = parser.parse_args()

    table = parameter_table()
    rows, atom_rows = [], []
    for structure in structures():
        name = structure["name"].replace("_EQeq", "")
        if arguments.only and arguments.only.lower() not in name.lower():
            continue
        printed = structure["charges"]
        for shells in [int(value) for value in arguments.shells.split(",")]:
            cached = None
            for factor in [float(value) for value in arguments.factors.split(",")]:
                try:
                    if cached is None:
                        centres = [CHARGE_CENTRES.get(element, 0) for element in structure["elements"]]
                        hardness = np.array([electronegativity_and_hardness(element, centre, table)[1]
                                             for element, centre in zip(structure["elements"], centres)])
                        cached = pair_matrix(structure, hardness, shells, COULOMB_EV_ANGSTROM / DIELECTRIC)
                    charges = solve(structure, table, shells, factor, cached)
                except KeyError as exc:
                    rows.append([name, shells, factor, len(printed), "", "", "", "", "", f"REFUSED: {exc}"])
                    print(f"{name:14} L={shells} c={factor}: REFUSED {exc}")
                    continue
                delta = np.abs(charges - printed)
                within = [float(np.mean(delta <= bound)) for bound in (TOLERANCE, 5e-3, 5e-2)]
                verdict = "REPRODUCED" if np.all(delta <= TOLERANCE) else "PARTIAL"
                ours = reference_deviation(structure["name"], charges)
                theirs = reference_deviation(structure["name"], printed)
                rows.append([name, shells, factor, len(printed), f"{float(np.median(delta)):.2e}",
                             f"{float(delta.max()):.4f}", *[f"{value:.4f}" for value in within],
                             "" if ours is None else f"{ours:.3f}", "" if theirs is None else f"{theirs:.3f}",
                             f"{float(np.sum(charges)):+.2e}", verdict])
                print(f"{name:14} L={shells} c={factor:<4} median |dq| {np.median(delta):.2e} max {delta.max():.4f} "
                      f"within 5e-4 {within[0]:.3f} | mean|q-REPEAT| ours {ours:.3f} theirs {theirs:.3f} -> {verdict}")
                if shells == 2 and factor == 1.0:
                    for index in range(len(printed)):
                        atom_rows.append([name, index + 1, structure["elements"][index], f"{charges[index]:.6f}",
                                          f"{printed[index]:.3f}", f"{charges[index] - printed[index]:+.4f}"])

    header = ("# TRIAGE 2.9: EQeq on Wilmer's own 12 MOFs, under a RECONSTRUCTED parameter table\n"
              "# (Moore 1970 + Andersen 1999; his ionizationData.dat is not held). Direct lattice sum.\n")
    for filename, columns, data in (
        ("eqeq_mofs.csv", ["mof", "shells", "factor", "atoms", "median_abs_delta", "max_abs_delta",
                           "within_5e-4", "within_5e-3", "within_5e-2", "mean_abs_vs_repeat_ours",
                           "mean_abs_vs_repeat_theirs", "charge_sum", "verdict"], rows),
        ("eqeq_atoms.csv", ["mof", "atom", "element", "model_charge", "printed_charge", "delta"], atom_rows),
    ):
        buffer = io.StringIO()
        csv.writer(buffer, lineterminator="\n").writerows([columns, *data])
        (HERE / filename).write_text(header + buffer.getvalue(), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
