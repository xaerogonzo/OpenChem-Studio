"""Amendment A12: Table IV geometry sensitivity for the adopted reading's remaining misses.

    uv run --no-sync python benchmarks/charges/rappe_goddard/table_iv_geometry.py

A diagnostic only. It perturbs one internal coordinate at a time, by a
deterministic Cartesian operation on each Harmony 1979 structure type (never a
rebuild), and writes table_iv_geometry.csv (every evaluation) and
table_iv_geometry_summary.csv (one row per cell and base). It changes no
adopted geometry and nothing in the solver.
"""

from __future__ import annotations

import csv
import itertools
import math
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from rdkit import Chem  # noqa: E402

from openchem.chem import charge_equilibration as ce  # noqa: E402
import qeq_geometries as geo  # noqa: E402

TOLERANCE = 0.01
BOND_STEPS = (-0.010, -0.005, 0.0, 0.005, 0.010)
ANGLE_STEPS = (-1.0, -0.5, 0.0, 0.5, 1.0)
#: (molecule, printed_order, column): the adopted reading's Table IV misses, SiH4 excluded (A12).
CELLS = (("H2NC(O)H", 2, "QEq"), ("H3COH", 1, "QEqHF"), ("H3COH", 3, "QEqHF"), ("H3COH", 5, "QEqHF"), ("H2NC(O)H", 3, "QEqHF"))
HYDROGEN = {"QEq": "experimental", "QEqHF": "hf"}
_TABLE = pathlib.Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "charges"


def _printed(molecule: str, order: int, column: str) -> float:
    lines = [l for l in (_TABLE / "rappe1991_table4.csv").read_text(encoding="utf-8").splitlines() if not l.startswith("#")]
    row = next(r for r in csv.DictReader(lines) if r["molecule"] == molecule and int(r["printed_order"]) == order)
    return float(row[column])


def structure_types(molecule: str) -> list[str]:
    rows = [r for r in geo._rows() if r["molecule"] == molecule]
    present = {r["structure_type"] for r in rows}
    return [t for t in geo.PREFERRED if t in present]


def bonds(elements: list[str], coords: np.ndarray) -> list[tuple[int, int]]:
    table = Chem.GetPeriodicTable()
    out = []
    for i, j in itertools.combinations(range(len(elements)), 2):
        limit = 1.2 * (table.GetRcovalent(elements[i]) + table.GetRcovalent(elements[j]))
        if np.linalg.norm(coords[i] - coords[j]) <= limit:
            out.append((i, j))
    return out


def fragment(bond_list: list[tuple[int, int]], cut: tuple[int, int], start: int) -> set[int]:
    """Atoms reachable from `start` once `cut` is removed; asserts the cut is not in a ring."""
    adjacency: dict[int, set[int]] = {}
    for i, j in bond_list:
        if {i, j} == set(cut):
            continue
        adjacency.setdefault(i, set()).add(j)
        adjacency.setdefault(j, set()).add(i)
    seen, stack = {start}, [start]
    while stack:
        for n in adjacency.get(stack.pop(), ()):
            if n not in seen:
                seen.add(n)
                stack.append(n)
    other = cut[0] if start == cut[1] else cut[1]
    assert other not in seen, f"bond {cut} is in a ring; A12 asserts none exists"
    return seen


def rotate(points: np.ndarray, origin: np.ndarray, axis: np.ndarray, degrees: float) -> np.ndarray:
    axis = axis / np.linalg.norm(axis)
    t = math.radians(degrees)
    v = points - origin
    return origin + v * math.cos(t) + np.cross(axis, v) * math.sin(t) + np.outer(v @ axis, axis) * (1 - math.cos(t))


def internal_coordinates(bond_list, coords) -> dict[str, float]:
    values = {f"r{i}-{j}": float(np.linalg.norm(coords[i] - coords[j])) for i, j in bond_list}
    neighbours: dict[int, list[int]] = {}
    for i, j in bond_list:
        neighbours.setdefault(i, []).append(j)
        neighbours.setdefault(j, []).append(i)
    for v, ns in neighbours.items():
        for a, b in itertools.combinations(sorted(ns), 2):
            u, w = coords[a] - coords[v], coords[b] - coords[v]
            values[f"a{a}-{v}-{b}"] = math.degrees(math.acos(np.clip(u @ w / (np.linalg.norm(u) * np.linalg.norm(w)), -1, 1)))
    return values


def perturbations(molecule: str, elements, coords):
    """(coordinate label, step, new coordinates) for every A12 operation."""
    bond_list = bonds(elements, coords)
    for i, j in bond_list:
        moved = sorted(fragment(bond_list, (i, j), j))
        unit = (coords[j] - coords[i]) / np.linalg.norm(coords[j] - coords[i])
        for step in BOND_STEPS:
            new = coords.copy()
            new[moved] += step * unit
            yield f"r{i}-{j}", step, new
    neighbours: dict[int, list[int]] = {}
    for i, j in bond_list:
        neighbours.setdefault(i, []).append(j)
        neighbours.setdefault(j, []).append(i)
    for v, ns in sorted(neighbours.items()):
        for a, b in itertools.combinations(sorted(ns), 2):
            moved = sorted(fragment(bond_list, (v, b), b))
            normal = np.cross(coords[a] - coords[v], coords[b] - coords[v])
            for step in ANGLE_STEPS:
                new = coords.copy()
                new[moved] = rotate(coords[moved], coords[v], normal, step)
                yield f"a{a}-{v}-{b}", step, new
    if molecule == "H3COH":
        # Hydroxyl H (index 0) about the C(2)-O(1) axis: the H-O-C-H torsion.
        for step in ANGLE_STEPS:
            new = coords.copy()
            new[[0]] = rotate(coords[[0]], coords[1], coords[1] - coords[2], step)
            yield "torsion H0-O1-C2-H", step, new


def run(cells: tuple = CELLS) -> tuple[list[list], list[list]]:
    evaluations, summary = [], []
    for molecule in sorted({c[0] for c in cells}):
        for kind in structure_types(molecule):
            elements, base, mapping, used = geo.build(molecule, order=(kind,) + geo.PREFERRED)
            base = np.asarray(base, dtype=float)
            bond_list = bonds(elements, base)
            reference = internal_coordinates(bond_list, base)
            chosen = [c for c in cells if c[0] == molecule]
            values: dict[tuple[int, str], list[tuple[float, str, float]]] = {(o, col): [] for _, o, col in chosen}
            for label, step, new in perturbations(molecule, elements, base):
                changed = internal_coordinates(bond_list, new)
                side = [k for k in changed if k != label and abs(changed[k] - reference[k]) > 1e-6]
                for column in sorted({col for _, _, col in chosen}):
                    result = ce.qeq_charges(elements, new, 0.0, hydrogen=HYDROGEN[column], readings=ce.ADOPTED)
                    for _, order, col in chosen:
                        if col != column:
                            continue
                        if result.status != "converged":
                            evaluations.append([molecule, kind, order, column, label, step, result.status, "", ";".join(side)])
                            continue
                        q = float(np.mean(result.charges[mapping[order]]))
                        values[(order, column)].append((q, label, step))
                        evaluations.append([molecule, kind, order, column, label, step, "converged", f"{q:.6f}", ";".join(side)])
            for _, order, column in chosen:
                target = _printed(molecule, order, column)
                got = values[(order, column)]
                nominal = next(q for q, _, s in got if s == 0.0)
                lo, hi = min(q for q, _, _ in got), max(q for q, _, _ in got)
                best = min(got, key=lambda t: abs(t[0] - target))
                min_error = abs(best[0] - target)
                if min_error <= TOLERANCE + 1e-12:
                    klass = "geometry-compatible"
                elif hi - lo >= TOLERANCE:
                    klass = "geometry-sensitive"
                else:
                    klass = "geometry-insensitive"
                types_used = ";".join(sorted(set(used.values())))
                summary.append([molecule, order, column, kind, types_used, f"{target:.2f}", f"{nominal:.6f}", f"{lo:.6f}", f"{hi:.6f}",
                                f"{hi - lo:.6f}", f"{min_error:.6f}", best[1], best[2], klass])
    return evaluations, summary


def main() -> None:
    evaluations, summary = run()
    with open(HERE / "table_iv_geometry.csv", "w", newline="", encoding="utf-8") as handle:
        handle.write("# Amendment A12: every perturbed evaluation. side_effects lists other bond lengths/angles moved by > 1e-6.\n")
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["molecule", "base_type", "printed_order", "column", "coordinate", "step", "status", "charge", "side_effects"])
        writer.writerows(evaluations)
    with open(HERE / "table_iv_geometry_summary.csv", "w", newline="", encoding="utf-8") as handle:
        handle.write("# Amendment A12: one row per cell and Harmony base structure type. Diagnostic only; nothing is adopted.\n")
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["molecule", "printed_order", "column", "base_type", "types_used", "printed", "nominal", "min", "max",
                         "range", "min_abs_error", "best_coordinate", "best_step", "class"])
        writer.writerows(summary)
    for row in summary:
        print(",".join(str(x) for x in row))


if __name__ == "__main__":
    main()
