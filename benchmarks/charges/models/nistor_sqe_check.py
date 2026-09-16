"""TRIAGE.md check 2.7: Nistor et al. 2006 split-charge equilibration, on recovered geometries.

    uv run --no-sync python benchmarks/charges/models/nistor_sqe_check.py

Reads `tests/fixtures/charge_models/nistor2006_si_molecules.csv` (the archived
supplement, check 2.1) and the supplement's parameter lists transcribed below.

THE GEOMETRY IS RECOVERED, NOT REBUILT (amendments 2.7-A2 and A3). The archived
tables print a coordinate column displaced against the atom rows. For the
molecules where rotating that column down one row gives a chemically
consistent structure, the rotation is the recovery; no coordinate is
invented and no hydrogen is chosen. Every other molecule is BLOCKED.

Units: angstrom, eV, e. The Slater kernel is `charge_equilibration`'s ns
two-centre Coulomb integral, with zeta converted to bohr^-1 and hartree to eV.
"""

from __future__ import annotations

import collections
import csv
import io
import math
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from openchem.chem import charge_equilibration as ce  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "charge_models" / "nistor2006_si_molecules.csv"
SIGMA_FIXTURE = ROOT / "tests" / "fixtures" / "charge_models" / "nistor2006_si_sigma.csv"
SYMBOL = {1: "H", 6: "C", 8: "O", 14: "Si"}
VALENCE = {"H": 1, "C": 4, "O": 2, "Si": 4}
#: Lange 15th ed. Table 4.7 single-bond radii, angstrom (`langes15`, as shipped in tsei_radii.json).
LANGE_RADII = {"H": 0.30, "C": 0.772, "O": 0.66, "Si": 1.17}
BOND_FACTOR = 1.25
#: Supplement p. 8: (n, zeta in 1/angstrom, printed normalisation A).
SLATER = {"H": (1, 2.315, 1.987), "C": (2, 1.618, 1.084), "O": (2, 1.842, 1.500), "Si": (3, 1.818, 0.964)}
METHODS = ("i", "ii", "iii", "iv")
READINGS = {"R_eq10": 1.0, "R_eq14": 0.5}  # amendment 2.7-A1: the bond-hardness energy coefficient
TOLERANCE = 5e-5
DISTANCE_EQUIVALENCE = 5e-3


def _atoms(rows: str) -> dict[str, tuple[float, float]]:
    out = {}
    for line in rows.strip().splitlines():
        element, kappa, chi = line.split()
        out[element] = (float(kappa), float(chi))
    return out


def _pairs(rows: str, width: int = 1) -> dict[str, tuple[float, ...] | float]:
    out = {}
    for line in rows.strip().splitlines():
        parts = line.split()
        values = tuple(float(v) for v in parts[1:1 + width])
        out[parts[0]] = values[0] if width == 1 else values
    return out


#: Supplement pp. 3-7, transcribed from the text layer. All 206 rows were re-parsed from a fresh pymupdf dump
#: and compared in order (2026-09-15, 0 mismatches); p. 3 was also checked against a render.
#: Atom rows: element, kappa [eV/e^2], chi [eV/e]. Method ii: pair, q-bar [e]. Methods iii/iv: pair,
#: kappa_s [eV/e^2]. Method iv deltas: ORDERED pair "A-B" (for an A bonded to B), d-kappa, d-chi.
PARAMETER_SETS = {
    "all41": {
        "i": _atoms("H 17.3351 5.0780\nC 8.6530 5.3039\nO 14.1631 8.3440\nSi 7.8226 4.4264"),
        "ii": _pairs("H-C 0.0908\nH-O 0.3775\nH-Si -0.0770\nC-C 0.0000\nC-O 0.2918\nC-Si -0.1897\nO-Si -0.2986\nSi-Si 0.0000"),
        "iii": (_atoms("H 16.1954 5.0780\nC 8.1313 5.2086\nO 12.4062 8.5220\nSi 6.7348 4.3850"),
                _pairs("H-C 1.2698\nH-O 0.0627\nH-Si 2.1629\nC-C 1.4719\nC-O 4.9727\nC-Si 2.7455\nO-Si 4.0194\nSi-Si 4.9988")),
        "iv": (_atoms("H 17.4830 5.0780\nC 8.3056 5.2381\nO 14.5976 8.9139\nSi 7.0924 4.6577"),
               _pairs("H-C 0.7718\nH-O 0.0030\nH-Si 1.2460\nC-C 1.1497\nC-O 4.8913\nC-Si 3.2162\nO-Si 4.0068\nSi-Si 0.0006"),
               _pairs("H-C 0.2306 -0.0135\nH-O -0.4915 -0.4921\nH-Si 0.0826 0.3885\nC-H -0.0329 0.0118\nC-C 0.0270 -0.0725\n"
                      "C-O 0.0359 -0.1134\nC-Si -0.3076 -0.0897\nO-H -0.0365 0.4035\nO-C 0.4956 0.4415\nO-Si -0.4035 0.4553\n"
                      "Si-H -0.0601 0.0380\nSi-C -0.1605 -0.0499\nSi-O 0.1689 -0.2514\nSi-Si 0.1131 -0.0498", width=2)),
    },
    "SiOH": {
        "i": _atoms("H 13.0752 5.0780\nO 16.1054 10.0716\nSi 7.8583 4.6493"),
        "ii": _pairs("H-O 0.4142\nH-Si -0.0769\nO-Si -0.2911\nSi-Si 0.0000"),
        "iii": (_atoms("H 15.0135 5.0780\nO 19.4465 13.4975\nSi 6.8884 4.0218"),
                _pairs("H-O 0.4904\nH-Si 4.7771\nO-Si 4.9955\nSi-Si 4.9824")),
        "iv": (_atoms("H 16.5241 5.0780\nO 14.1651 9.8085\nSi 6.8856 4.5246"),
               _pairs("H-O 0.1556\nH-Si 3.1231\nO-Si 4.8503\nSi-Si 0.0014"),
               _pairs("H-O 0.1424 -0.4859\nH-Si -0.1973 0.1428\nO-H 0.0273 -0.4075\nO-Si -0.4150 0.1056\n"
                      "Si-H -0.1330 0.0285\nSi-O 0.1305 -0.1688\nSi-Si -0.0478 -0.1323", width=2)),
    },
    "COH": {
        "i": _atoms("H 17.7661 5.0780\nC 8.5955 5.3239\nO 39.9778 20.247"),
        "ii": _pairs("H-C 0.0886\nH-O 0.3544\nC-C 0.0000\nC-O 0.2990"),
        "iii": (_atoms("H 16.1954 5.0780\nC 8.1313 5.1946\nO 12.4062 8.9714"),
                _pairs("H-C 1.279\nH-O 0.0002\nC-C 1.5368\nC-O 4.7892")),
        "iv": (_atoms("H 17.1194 5.0780\nC 7.9202 5.2828\nO 22.6975 13.9493"),
               _pairs("H-C 1.8723\nH-O 0.0017\nC-C 2.2412\nC-O 4.9621"),
               _pairs("H-C 0.1545 0.0563\nH-O -0.3591 -0.4856\nC-H -0.0457 0.0183\nC-C 0.0590 -0.0640\nC-O -0.0129 -0.0496\n"
                      "O-H -0.0103 0.1895\nO-C 0.4992 0.4568", width=2)),
    },
    "ESP": {
        "i": _atoms("H 13.4008 5.0780\nC 9.3202 5.1378\nO 14.8888 8.8285\nSi 8.3574 4.5347"),
        "ii": _pairs("H-C 0.0451\nH-O 0.3687\nH-Si -0.0821\nC-C 0.0000\nC-O 0.1871\nC-Si -0.0769\nO-Si -0.2091\nSi-Si 0.0000"),
        "iii": (_atoms("H 6.1676 5.0780\nC 7.5714 5.1909\nO 23.3706 16.5493\nSi 5.8899 3.1652"),
                _pairs("H-C 7.3305\nH-O 5.6777\nH-Si 14.9090\nC-C 3.6631\nC-O 4.1025\nC-Si 11.8874\nO-Si 9.5642\nSi-Si 14.9736")),
        "iv": (_atoms("H 10.0485 5.0780\nC 15.6026 4.7040\nO 21.1063 13.7676\nSi 16.7587 -0.0599"),
               _pairs("H-C 4.8515\nH-O 3.8416\nH-Si 1.4485\nC-C 3.2010\nC-O 3.8509\nC-Si 2.7465\nO-Si 4.6145\nSi-Si 13.1324"),
               _pairs("H-C 0.5614 0.4664\nH-O 1.3626 0.1542\nH-Si 1.4405 1.1988\nC-H 0.4479 1.2716\nC-C 0.6829 -1.1118\n"
                      "C-O 1.3289 -1.3416\nC-Si -1.2930 1.2333\nO-H -1.1742 -0.2640\nO-C 1.2469 1.0616\nO-Si -0.7838 0.6702\n"
                      "Si-H -0.2752 0.7383\nSi-C 0.3059 -0.7586\nSi-O 0.7646 -1.4710\nSi-Si 1.3694 1.3878", width=2)),
    },
    "Mulliken": {
        "i": _atoms("H 16.6640 5.0780\nC 9.4234 5.6020\nO 16.0979 9.7151\nSi 7.7254 4.4616"),
        "ii": _pairs("H-C 0.1058\nH-O 0.3070\nH-Si -0.0778\nC-C 0.0000\nC-O 0.2265\nC-Si -0.1866\nO-Si -0.3098\nSi-Si 0.0000"),
        "iii": (_atoms("H 26.2512 5.0780\nC 8.5752 6.4058\nO 13.5321 14.8450\nSi 6.5818 3.4600"),
                _pairs("H-C 0.4867\nH-O 5.0636\nH-Si 3.5424\nC-C 14.9457\nC-O 14.6860\nC-Si 8.2404\nO-Si 14.7686\nSi-Si 3.6638")),
        "iv": (_atoms("H 17.9676 5.0780\nC 9.5485 5.7524\nO 15.4104 10.2436\nSi 7.1665 4.3670"),
               _pairs("H-C 1.1167\nH-O 0.4147\nH-Si 1.1311\nC-C 11.2524\nC-O 1.4617\nC-Si 3.1207\nO-Si 4.7786\nSi-Si 0.1760"),
               _pairs("H-C 0.6728 -0.1609\nH-O 0.7572 -0.3863\nH-Si 0.7804 0.0765\nC-H -0.0567 0.0304\nC-C -0.0753 -0.0236\n"
                      "C-O -0.0428 -0.0613\nC-Si -0.1703 0.0552\nO-H 0.6876 -0.1029\nO-C -0.2168 0.0541\nO-Si -1.1525 0.0880\n"
                      "Si-H 0.0071 0.0195\nSi-C 0.0039 -0.0406\nSi-O 0.1619 -0.2327\nSi-Si -0.1397 -0.0349", width=2)),
    },
}


# --- data -----------------------------------------------------------------------------------------


def molecules() -> dict[int, dict]:
    text = FIXTURE.read_text(encoding="utf-8")
    rows = list(csv.DictReader(io.StringIO("".join(l for l in text.splitlines(keepends=True) if not l.startswith("#")))))
    grouped = collections.defaultdict(list)
    for r in rows:
        grouped[int(r["index"])].append(r)
    out = {}
    for index, atoms in sorted(grouped.items()):
        out[index] = {
            "index": index, "name": atoms[0]["name"], "code": atoms[0]["code"],
            "elements": [SYMBOL[int(a["Z"])] for a in atoms],
            "printed_coords": [(float(a["x"]), float(a["y"]), float(a["z"])) for a in atoms],
            "charges": {col: [float(a[col]) for a in atoms] for col in ("esp", *METHODS)},
            "raw": {col: [a[col] for a in atoms] for col in ("esp", *METHODS)},
        }
    return out


def printed_sigma() -> dict[int, dict[str, float]]:
    text = SIGMA_FIXTURE.read_text(encoding="utf-8")
    rows = csv.DictReader(io.StringIO("".join(l for l in text.splitlines(keepends=True) if not l.startswith("#"))))
    return {int(r["index"]): {m: float(r[m]) for m in METHODS} for r in rows}


# --- recovery ------------------------------------------------------------------------------------


def bond_list(elements: list[str], coords, factor: float = BOND_FACTOR) -> list[tuple[int, int]]:
    out = []
    for i in range(len(elements)):
        for j in range(i + 1, len(elements)):
            if math.dist(coords[i], coords[j]) < factor * (LANGE_RADII[elements[i]] + LANGE_RADII[elements[j]]):
                out.append((i, j))
    return out


def valences_hold(elements: list[str], bonds) -> bool:
    degree = [0] * len(elements)
    for i, j in bonds:
        degree[i] += 1
        degree[j] += 1
    return all(degree[k] == VALENCE[e] for k, e in enumerate(elements))


def rotated(coords, k: int = 1, reverse: bool = False) -> list[tuple[float, float, float]]:
    """The coordinate column rotated DOWN by k rows (row n-1 -> row 0 for k = 1), optionally reversed first."""
    seq = list(coords)[::-1] if reverse else list(coords)
    return seq[-k:] + seq[:-k] if k else seq


def distance_matrix(coords) -> np.ndarray:
    x = np.asarray(coords, dtype=float)
    return np.linalg.norm(x[:, None, :] - x[None, :, :], axis=-1)


def method_ii_charges(elements: list[str], bonds, pairs: dict) -> list[float]:
    """Eq 14: a fixed q-bar per bond type. A pair "A-B" puts +v on A and -v on B."""
    q = [0.0] * len(elements)
    for i, j in bonds:
        a, b = elements[i], elements[j]
        if f"{a}-{b}" in pairs:
            v = pairs[f"{a}-{b}"]
            q[i] += v
            q[j] -= v
        else:
            v = pairs[f"{b}-{a}"]
            q[j] += v
            q[i] -= v
    return q


def heavy_ii_consistent(molecule: dict, bonds, pairs: dict) -> bool:
    recomputed = method_ii_charges(molecule["elements"], bonds, pairs)
    degree = collections.Counter(k for bond in bonds for k in bond)
    return all(abs(recomputed[k] - molecule["charges"]["ii"][k]) <= TOLERANCE * degree[k] + 1e-12
               for k, e in enumerate(molecule["elements"]) if e != "H")


SYMMETRY_COLUMNS = ("esp", "i", "ii", "iii", "iv")


def symmetry_class(molecule: dict, atom: int) -> tuple:
    """Step 2's class: element plus the printed text of all five charge columns."""
    return (molecule["elements"][atom], *(molecule["raw"][col][atom] for col in SYMMETRY_COLUMNS))


def same_class_points(molecule: dict, coords_a, coords_b) -> bool:
    """Amendment A3: two assignments are equivalent when every symmetry class sits on the same set of points,
    so they differ only in labels that print identical values, and every per-atom comparison is the same."""
    classes = collections.defaultdict(lambda: (collections.Counter(), collections.Counter()))
    for atom in range(len(molecule["elements"])):
        a, b = classes[symmetry_class(molecule, atom)]
        a[tuple(coords_a[atom])] += 1
        b[tuple(coords_b[atom])] += 1
    return all(a == b for a, b in classes.values())


def recover(molecule: dict, pairs: dict, factor: float = BOND_FACTOR, symmetry_classes: bool = True) -> dict:
    """Amendment 2.7-A2's Step 2 for one molecule: RECOVERED-BY-ROTATION, AMBIGUOUS or BLOCKED."""
    elements = molecule["elements"]
    consistent = []
    for k in range(len(elements)):
        for reverse in (False, True):
            coords = rotated(molecule["printed_coords"], k, reverse)
            bonds = bond_list(elements, coords, factor)
            if valences_hold(elements, bonds):
                consistent.append((k, reverse, coords, bonds))
    base = next((c for c in consistent if c[0] == 1 and not c[1]), None)
    if base is None:
        return {"class": "BLOCKED", "reason": "no one-row rotation consistent with valence" if not consistent else
                f"consistent only at rotations {[(k, r) for k, r, *_ in consistent]}", "rotations": [(k, r) for k, r, *_ in consistent]}
    if not heavy_ii_consistent(molecule, base[3], pairs):
        return {"class": "BLOCKED", "reason": "heavy-atom method ii charges do not recompute", "rotations": [(k, r) for k, r, *_ in consistent]}
    reference = distance_matrix(base[2])
    differing = [(k, r) for k, r, coords, _ in consistent if (k, r) != (1, False)
                 and not (symmetry_classes and same_class_points(molecule, base[2], coords))
                 and np.abs(distance_matrix(coords) - reference).max() > DISTANCE_EQUIVALENCE]
    if differing:
        return {"class": "AMBIGUOUS", "reason": f"rotations {differing} give a different structure", "rotations": [(k, r) for k, r, *_ in consistent]}
    return {"class": "RECOVERED-BY-ROTATION", "coords": base[2], "bonds": base[3], "rotations": [(k, r) for k, r, *_ in consistent]}


# --- kernel and solver ---------------------------------------------------------------------------


def slater_j_ev(element_a: str, element_b: str, r_angstrom: float) -> float:
    """Supplement p. 8's two-centre integral of normalised ns Slater densities, in eV."""
    n_a, zeta_a, _ = SLATER[element_a]
    n_b, zeta_b, _ = SLATER[element_b]
    bohr = ce.EEM_BOHR_ANGSTROM
    value = ce.coulomb_pair_integrals(n_a, n_b, [zeta_a * bohr], [zeta_b * bohr], [r_angstrom / bohr])[0]
    return float(value) * ce.HARTREE_EV


def printed_normalisation(element: str) -> float:
    n, zeta, _ = SLATER[element]
    return math.sqrt((2 * zeta) ** (2 * n + 1) / (4 * math.pi * math.factorial(2 * n)))


def atomic_parameters(elements, bonds, parameter_set: dict, method: str) -> tuple[np.ndarray, np.ndarray, dict]:
    if method == "i":
        atoms, kappa_s, deltas = parameter_set["i"], {}, None
    elif method == "iii":
        atoms, kappa_s = parameter_set["iii"]
        deltas = None
    elif method == "iv":
        atoms, kappa_s, deltas = parameter_set["iv"]
    else:
        raise ValueError(method)
    kappa = np.array([atoms[e][0] for e in elements])
    chi = np.array([atoms[e][1] for e in elements])
    if deltas is not None:
        for i, j in bonds:
            for a, b in ((i, j), (j, i)):
                d_kappa, d_chi = deltas[f"{elements[a]}-{elements[b]}"]  # ordered: KeyError, never a silent zero
                kappa[a] += d_kappa
                chi[a] += d_chi
    return kappa, chi, kappa_s


def solve(elements, coords, bonds, parameter_set: dict, method: str, reading: str = "R_eq10") -> np.ndarray:
    """Eq 9 on V = sum_i (kappa_i Q_i^2 / 2 + chi_i Q_i) + sum_bonds c kappa_s q^2 + sum_{i<j} Q_i Q_j J_ij.

    c is amendment A1's reading. Rank-deficient on rings: lstsq, and the atomic charges are the output."""
    n = len(elements)
    kappa, chi, kappa_s = atomic_parameters(elements, bonds, parameter_set, method)
    h = np.diag(kappa)
    for i in range(n):
        for j in range(i + 1, n):
            h[i, j] = h[j, i] = slater_j_ev(elements[i], elements[j], math.dist(coords[i], coords[j]))
    m = np.zeros((n, len(bonds)))
    bond_hardness = np.zeros(len(bonds))
    for b, (i, j) in enumerate(bonds):
        m[i, b], m[j, b] = 1.0, -1.0
        if method in ("iii", "iv"):
            key = f"{elements[i]}-{elements[j]}" if f"{elements[i]}-{elements[j]}" in kappa_s else f"{elements[j]}-{elements[i]}"
            bond_hardness[b] = kappa_s[key]
    a = m.T @ h @ m + np.diag(2.0 * READINGS[reading] * bond_hardness)
    q, *_ = np.linalg.lstsq(a, -(m.T @ chi), rcond=1e-12)
    return m @ q


def sigma(model, reference) -> float:
    """Check 2.1's identified form: 100 * sqrt(sum (Q - Q_esp)^2 / sum Q_esp^2)."""
    model, reference = np.asarray(model), np.asarray(reference)
    return float(100.0 * math.sqrt(np.sum((model - reference) ** 2) / np.sum(reference ** 2)))


def family(molecule: dict) -> str:
    present = set(molecule["elements"])
    return "Si-C-O-H" if {"Si", "C"} <= present else ("Si-O-H" if "Si" in present else "C-O-H")


# --- the check -----------------------------------------------------------------------------------


def identify_parameter_set(mols: dict, recovered: dict) -> dict[str, int]:
    """Step 1 on the recovered molecules: how many each set's method ii reproduces on EVERY atom."""
    counts = {}
    for name, ps in PARAMETER_SETS.items():
        hits = 0
        for index, rec in recovered.items():
            molecule = mols[index]
            try:
                q = method_ii_charges(molecule["elements"], rec["bonds"], ps["ii"])
            except KeyError:
                continue
            degree = collections.Counter(k for bond in rec["bonds"] for k in bond)
            if all(abs(q[k] - molecule["charges"]["ii"][k]) <= TOLERANCE * degree[k] + 1e-12 for k in range(len(q))):
                hits += 1
        counts[name] = hits
    return counts


def main() -> None:
    mols = molecules()
    all41 = PARAMETER_SETS["all41"]
    recovery = {i: recover(m, all41["ii"]) for i, m in mols.items()}
    recovered = {i: r for i, r in recovery.items() if r["class"] == "RECOVERED-BY-ROTATION"}
    sensitivity = {f: sum(1 for m in mols.values() if recover(m, all41["ii"], f)["class"] == "RECOVERED-BY-ROTATION") for f in (1.15, 1.35)}
    registered_a2 = collections.Counter(recover(m, all41["ii"], symmetry_classes=False)["class"] for m in mols.values())
    identified = identify_parameter_set(mols, recovered)
    print("amendment A2 as written (no symmetry classes):", registered_a2)
    print("recovery classes:", collections.Counter(r["class"] for r in recovery.values()), "sensitivity f->count:", sensitivity)
    print("parameter set identification (method ii on every atom of the recovered molecules):", identified)
    sigmas = printed_sigma()
    atom_rows, molecule_rows = [], []
    for index, rec in recovered.items():
        molecule = mols[index]
        for method in ("i", "iii", "iv"):
            for reading in (("R_eq10",) if method == "i" else READINGS):
                q = solve(molecule["elements"], rec["coords"], rec["bonds"], all41, method, reading)
                printed = molecule["charges"][method]
                deltas = [q[k] - printed[k] for k in range(len(q))]
                failed = [k + 1 for k, d in enumerate(deltas) if abs(d) > TOLERANCE]
                cls = "REPRODUCED-ON-RECOVERED-CORRESPONDENCE" if not failed else "PARTIAL"
                for k, d in enumerate(deltas):
                    atom_rows.append([index, molecule["name"], k + 1, molecule["elements"][k], method, reading if method != "i" else "",
                                      f"{q[k]:.6f}", molecule["raw"][method][k], f"{d:+.6f}", abs(d) <= TOLERANCE])
                molecule_rows.append([index, molecule["name"], family(molecule), method, reading if method != "i" else "", cls,
                                      len(failed), f"{max(abs(d) for d in deltas):.6f}", f"{sigma(q, molecule['charges']['esp']):.2f}",
                                      sigmas[index][method]])
                print(f"{index:2} {molecule['name']:24} {method:3} {reading if method != 'i' else '':7} {cls:40} "
                      f"failed {len(failed):2}/{len(q)} max|d| {max(abs(d) for d in deltas):.4f} sigma {sigma(q, molecule['charges']['esp']):.2f} "
                      f"(printed {sigmas[index][method]})")
    header = "# TRIAGE 2.7: Nistor SQE on geometries recovered by the one-row rotation (amendment A2), all-41 parameters.\n"
    for name, columns, rows in (
        ("nistor_sqe_atoms.csv", ["index", "molecule", "atom", "element", "method", "reading", "model", "printed", "delta", "reproduced"], atom_rows),
        ("nistor_sqe_molecules.csv", ["index", "molecule", "family", "method", "reading", "class", "failed_atoms", "max_abs_delta",
                                      "sigma_model", "sigma_printed"], molecule_rows),
        ("nistor_recovery.csv", ["index", "molecule", "family", "class", "consistent_rotations", "reason"],
         [[i, mols[i]["name"], family(mols[i]), r["class"], r["rotations"], r.get("reason", "")] for i, r in recovery.items()]),
    ):
        buffer = io.StringIO()
        csv.writer(buffer, lineterminator="\n").writerows([columns, *rows])
        (HERE / name).write_text(header + buffer.getvalue(), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
