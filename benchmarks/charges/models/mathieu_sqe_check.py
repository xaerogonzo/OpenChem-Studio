"""TRIAGE.md check 2.4: Mathieu 2007 SQE model B against Table I's SQE rows.

    uv run --no-sync python benchmarks/charges/models/mathieu_sqe_check.py

Reads the frozen EQ and TS fixtures only. The linear system is derived from
eq 8, the model's energy, NOT from eq 13 as printed, which is its negative in
the eta and Coulomb block (TRIAGE.md 2.4a); `literal_eq13_diagnostic` keeps
the printed form for the record and is never used to produce charges.

Units: coordinates in angstrom; distances in bohr; every matrix and vector in
Hartree per e^2 (chi, eta and C divided by HARTREE_EV here, in this module);
charges in e.
"""

from __future__ import annotations

import csv
import io
import math
import pathlib
import sys
from dataclasses import dataclass, field

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

from openchem.chem import charge_equilibration as ce  # noqa: E402
import mathieu_eem_check as mec  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "charge_models"
SETS = {"EQ": FIXTURES / "mathieu2007_eq.csv", "TS": FIXTURES / "mathieu2007_ts.csv"}
METRICS = ("C", "H", "N", "O", "F", "All")
ELEMENTS = METRICS[:-1]

#: Table I caption.
C_EV = 115.0
LAMBDA = 0.816
#: Table II, angstrom.
R_COVALENT = {"C": 0.77, "H": 0.37, "N": 0.75, "O": 0.73, "F": 0.71}
R_VDW = {"C": 1.70, "H": 1.20, "N": 1.55, "O": 1.52, "F": 1.47}
#: Table II model B, eV: chi relative to H, and eta. Asserted equal to the shipped table.
TABLE_II_CHI_RELATIVE = {"C": 4.25, "H": 0.00, "N": 7.80, "O": 13.72, "F": 14.00}
TABLE_II_ETA = {"C": 9.00, "H": 17.95, "N": 9.39, "O": 14.34, "F": 19.77}

#: Table I, rows printed to 2 dp (R^2) and 4 dp (Delta-q).
PRINTED = {
    ("EEM", "EQ"): {"C": 0.96, "H": 0.81, "N": 0.95, "O": 0.66, "F": 0.36, "All": 0.97, "dq": 0.0668},
    ("EEM", "TS"): {"C": 0.96, "H": 0.86, "N": 0.93, "O": 0.86, "F": 0.36, "All": 0.96, "dq": 0.0847},
    ("SQE", "EQ"): {"C": 0.97, "H": 0.85, "N": 0.96, "O": 0.67, "F": 0.35, "All": 0.98, "dq": 0.0650},
    ("SQE", "TS"): {"C": 0.96, "H": 0.88, "N": 0.95, "O": 0.89, "F": 0.16, "All": 0.97, "dq": 0.0952},
}
TOLERANCE = 0.005
RCOND = 1e-10
RESIDUAL_LIMIT = 1e-9
SUM_LIMIT = 1e-12


@dataclass
class Parameters:
    c_ev: float = C_EV
    lam: float = LAMBDA
    chi_ev: dict[str, float] = field(default_factory=lambda: {e: v[0] for e, v in ce.EEM_BULTINCK2002_PART1.items()})
    eta_ev: dict[str, float] = field(default_factory=lambda: {e: v[1] for e, v in ce.EEM_BULTINCK2002_PART1.items()})
    r_covalent: dict[str, float] = field(default_factory=lambda: dict(R_COVALENT))
    r_vdw: dict[str, float] = field(default_factory=lambda: dict(R_VDW))


def pairs(elements: list[str], coords, params: Parameters) -> list[tuple[int, int, float]]:
    """(i, j, r in angstrom) for i < j with r strictly below the van der Waals sum (text above eq 8)."""
    xyz = np.asarray(coords, dtype=float)
    out = []
    for i in range(len(elements)):
        for j in range(i + 1, len(elements)):
            r = float(np.linalg.norm(xyz[i] - xyz[j]))
            if r < params.r_vdw[elements[i]] + params.r_vdw[elements[j]]:
                out.append((i, j, r))
    return out


def penalty(elements: list[str], pair_list, params: Parameters) -> np.ndarray:
    """Eq 14 in Hartree per e^2, Theta(0) = 0. Only ever called on pairs inside the cutoff,
    so the denominator is strictly negative and never zero."""
    k = np.zeros(len(pair_list))
    for p, (i, j, r) in enumerate(pair_list):
        onset = params.lam * (params.r_covalent[elements[i]] + params.r_covalent[elements[j]])
        limit = params.r_vdw[elements[i]] + params.r_vdw[elements[j]]
        assert r < limit, (i, j, r, limit)
        if r > onset:
            k[p] = 2.0 * params.c_ev * ((r - onset) / (r - limit)) ** 2 / ce.HARTREE_EV
    return k


def atomic_hessian(elements: list[str], coords, params: Parameters) -> np.ndarray:
    """Eq 8's first two terms in atomic charges: 2 eta on the diagonal (eq 2), 1/R off it."""
    xyz = np.asarray(coords, dtype=float) / ce.EEM_BOHR_ANGSTROM
    n = len(elements)
    h = np.zeros((n, n))
    for a in range(n):
        h[a, a] = 2.0 * params.eta_ev[elements[a]] / ce.HARTREE_EV
        for b in range(n):
            if a != b:
                h[a, b] = 1.0 / float(np.linalg.norm(xyz[a] - xyz[b]))
    return h


def incidence(n: int, pair_list) -> np.ndarray:
    """dQ_k/dq_ij = delta_kj - delta_ki (eq 10): -1 in row i, +1 in row j."""
    m = np.zeros((n, len(pair_list)))
    for p, (i, j, _) in enumerate(pair_list):
        m[i, p] = -1.0
        m[j, p] = 1.0
    return m


def assemble(elements: list[str], coords, params: Parameters | None = None, *, use_penalty: bool = True) -> dict:
    """A = M^T H M + diag(K), b = -M^T chi. `use_penalty=False` is the EEM limit: every pair
    connected and K = 0, built explicitly rather than through an infinite radius in eq 14."""
    params = params or Parameters()
    n = len(elements)
    if use_penalty:
        pair_list = pairs(elements, coords, params)
        k = penalty(elements, pair_list, params)
    else:
        xyz = np.asarray(coords, dtype=float)
        pair_list = [(i, j, float(np.linalg.norm(xyz[i] - xyz[j]))) for i in range(n) for j in range(i + 1, n)]
        k = np.zeros(len(pair_list))
    h = atomic_hessian(elements, coords, params)
    m = incidence(n, pair_list)
    chi = np.array([params.chi_ev[e] for e in elements]) / ce.HARTREE_EV
    a = m.T @ h @ m + np.diag(k)
    return {"pairs": pair_list, "K": k, "H": h, "M": m, "A": a, "b": -m.T @ chi, "chi": chi}


def components(n: int, pair_list) -> list[list[int]]:
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j, _ in pair_list:
        parent[find(i)] = find(j)
    groups: dict[int, list[int]] = {}
    for a in range(n):
        groups.setdefault(find(a), []).append(a)
    return sorted(groups.values())


def _positive_on_neutral_subspace(h: np.ndarray, group: list[int]) -> bool:
    if len(group) < 2:
        return True
    sub = h[np.ix_(group, group)]
    # An orthonormal basis of {x : sum x = 0} in this component.
    basis = np.linalg.svd(np.ones((1, len(group))))[2][1:]
    return bool(np.linalg.eigvalsh(basis @ sub @ basis.T).min() > 0.0)


@dataclass
class Solution:
    charges: np.ndarray
    q: np.ndarray
    valid: bool
    reason: str
    diagnostics: dict


def solve(elements: list[str], coords, params: Parameters | None = None, *, use_penalty: bool = True, rcond: float = RCOND) -> Solution:
    system = assemble(elements, coords, params, use_penalty=use_penalty)
    a, b, m = system["A"], system["b"], system["M"]
    n = len(elements)
    asymmetry = float(np.abs(a - a.T).max()) if a.size else 0.0
    assert asymmetry <= 1e-14, asymmetry
    a = 0.5 * (a + a.T)
    if a.size:
        q, *_ = np.linalg.lstsq(a, b, rcond=rcond)
        sv = np.linalg.svd(a, compute_uv=False)
        retained = sv[sv > rcond * sv[0]] if sv[0] > 0 else sv[:0]
        residual = float(np.abs(a @ q - b).max())
    else:
        q, sv, retained, residual = np.zeros(0), np.zeros(0), np.zeros(0), 0.0
    charges = m @ q
    groups = components(n, system["pairs"])
    sums = [float(charges[g].sum()) for g in groups]
    positive = all(_positive_on_neutral_subspace(system["H"], g) for g in groups)
    diagnostics = {
        "pairs": len(system["pairs"]), "components": len(groups), "component_sums": sums,
        "sigma_max": float(sv[0]) if sv.size else 0.0,
        "sigma_min_retained": float(retained[-1]) if retained.size else 0.0,
        "condition": float(sv[0] / retained[-1]) if retained.size else math.inf,
        "discarded": int(sv.size - retained.size),
        "cycle_dimension": len(system["pairs"]) - n + len(groups),
        "residual_hartree": residual, "residual_ev": residual * ce.HARTREE_EV,
        "h_positive_on_neutral_subspace": positive,
    }
    reasons = []
    if residual > RESIDUAL_LIMIT:
        reasons.append(f"residual {residual:.2e} Hartree/e")
    if any(abs(s) > SUM_LIMIT for s in sums):
        reasons.append(f"component sum {max(abs(s) for s in sums):.2e} e")
    if not positive:
        reasons.append("H not positive definite on a neutral subspace")
    return Solution(charges, q, not reasons, "; ".join(reasons), diagnostics)


def literal_eq13_diagnostic(elements: list[str], coords, params: Parameters | None = None) -> dict:
    """Eqs 12 and 13 exactly as printed, element by element. A record of the source, never a solver."""
    params = params or Parameters()
    pair_list = pairs(elements, coords, params)
    k = penalty(elements, pair_list, params)
    xyz = np.asarray(coords, dtype=float) / ce.EEM_BOHR_ANGSTROM
    n = len(elements)
    coulomb = np.zeros((n, n))
    for a in range(n):
        for c in range(n):
            if a != c:
                coulomb[a, c] = 1.0 / float(np.linalg.norm(xyz[a] - xyz[c]))
    eta = [params.eta_ev[e] / ce.HARTREE_EV for e in elements]
    delta = lambda x, y: 1.0 if x == y else 0.0  # noqa: E731
    size = len(pair_list)
    matrix = np.zeros((size, size))
    for p, (i, j, _) in enumerate(pair_list):
        for r, (kk, l, _) in enumerate(pair_list):
            matrix[p, r] = (2 * eta[i] * (delta(i, l) - delta(i, kk)) - 2 * eta[j] * (delta(j, l) - delta(j, kk))
                            + (coulomb[i, l] + coulomb[j, kk] - coulomb[j, l] - coulomb[i, kk]) + k[p] * delta(p, r))
    rhs = np.array([(params.chi_ev[elements[j]] - params.chi_ev[elements[i]]) / ce.HARTREE_EV for i, j, _ in pair_list])
    report = {"matrix": matrix, "B": rhs, "pairs": pair_list}
    if size:
        eig = np.linalg.eigvalsh(0.5 * (matrix + matrix.T))
        q, *_ = np.linalg.lstsq(matrix, rhs, rcond=RCOND)
        eq8 = assemble(elements, coords, params)
        report.update(negative_eigenvalues=int((eig < 0).sum()), eigenvalue_min=float(eig.min()), eigenvalue_max=float(eig.max()),
                      condition=float(np.linalg.cond(matrix)), eq8_stationarity=float(np.abs(eq8["A"] @ q - eq8["b"]).max()))
    return report


# --- corpus ----------------------------------------------------------------------------------


def population(fixture: pathlib.Path) -> list[dict]:
    """One entry per structure, atoms in source order; shared by the EEM and SQE arms."""
    out = []
    for name, atoms in mec.molecules(fixture).items():
        out.append({"file": name, "atoms": [int(a["atom"]) for a in atoms], "elements": [a["element"] for a in atoms],
                    "coords": np.array([[float(a["x"]), float(a["y"]), float(a["z"])] for a in atoms]),
                    "mulliken": [float(a["mulliken"]) for a in atoms], "raw_mulliken": [a["mulliken"] for a in atoms]})
    keys = [(s["file"], i) for s in out for i in s["atoms"]]
    assert len(keys) == len(set(keys)), "duplicate (file, atom) keys"
    return out


def r_squared(predicted, reference) -> float:
    return mec.r_squared(list(predicted), list(reference))
