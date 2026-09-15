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


#: TRIAGE 2.6a: Table II model C, eV (chi relative to H; only differences enter, test 9).
MODEL_C = {"chi": {"C": 5.44, "H": 0.00, "N": 10.48, "O": 22.37, "F": 29.80},
           "eta": {"C": 8.93, "H": 18.86, "N": 10.06, "O": 20.55, "F": 45.74}, "lam": 0.695, "c_ev": 8.03}
#: TRIAGE 2.6d: the p. 6 and p. 7 prose values, eq 15 under a square root (2.5's form).
PROSE_EEM_DQ = 0.0695
PROSE_MODEL_B_DQ = 0.0670
PROSE_MODEL_C_DQ = 0.0583
PROSE_MODEL_C_R2 = 0.98
#: The shipped EEM's pooled sqrt(Delta-q) measured in section 3.5; the run stops unless it recurs.
EEM_POOLED_SQRT_DQ = 0.069395
#: 2.6e V1: an engineering factor, not a source value.
BOND_FACTOR = 1.3
VALENCE = {"H": 1, "C": 4, "N": 3, "O": 2, "F": 1}


@dataclass
class Parameters:
    c_ev: float = C_EV
    lam: float = LAMBDA
    chi_ev: dict[str, float] = field(default_factory=lambda: {e: v[0] for e, v in ce.EEM_BULTINCK2002_PART1.items()})
    eta_ev: dict[str, float] = field(default_factory=lambda: {e: v[1] for e, v in ce.EEM_BULTINCK2002_PART1.items()})
    r_covalent: dict[str, float] = field(default_factory=lambda: dict(R_COVALENT))
    r_vdw: dict[str, float] = field(default_factory=lambda: dict(R_VDW))
    #: "vdw" is 2.4's rule (text above eq 8); "bond_graph" is 2.6e's V1 reconstruction.
    pair_rule: str = "vdw"
    bond_factor: float = BOND_FACTOR
    #: "coulomb" is 1/R (2.4b); "ohno_klopman" is 2.6e's V2, oda2003 eq 17.
    kernel: str = "coulomb"


def model_c() -> Parameters:
    return Parameters(c_ev=MODEL_C["c_ev"], lam=MODEL_C["lam"], chi_ev=dict(MODEL_C["chi"]), eta_ev=dict(MODEL_C["eta"]))


def pairs(elements: list[str], coords, params: Parameters) -> list[tuple[int, int, float]]:
    """(i, j, r in angstrom) for i < j. V0: r strictly below the van der Waals sum (text above eq 8).
    V1: r below `bond_factor` times the covalent sum, which is always inside the van der Waals sum
    for these elements, so eq 14's denominator stays negative."""
    xyz = np.asarray(coords, dtype=float)
    out = []
    for i in range(len(elements)):
        for j in range(i + 1, len(elements)):
            r = float(np.linalg.norm(xyz[i] - xyz[j]))
            if params.pair_rule == "bond_graph":
                inside = r < params.bond_factor * (params.r_covalent[elements[i]] + params.r_covalent[elements[j]])
            else:
                inside = r < params.r_vdw[elements[i]] + params.r_vdw[elements[j]]
            if inside:
                out.append((i, j, r))
    return out


def valence_problems(elements: list[str], pair_list) -> list[str]:
    """V1's applicability check: every atom's graph degree equals its neutral valence."""
    degree = [0] * len(elements)
    for i, j, _ in pair_list:
        degree[i] += 1
        degree[j] += 1
    return [f"{elements[a]}{a + 1} degree {d}" for a, d in enumerate(degree) if d != VALENCE[elements[a]]]


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


def ohno_klopman(r_bohr: float, eta_i_hartree: float, eta_j_hartree: float) -> float:
    """oda2003 eq 17, J = 1/sqrt(R^2 + (1/(2 J_II) + 1/(2 J_JJ))^2), with Oda's J_II = d2E/dq2
    (his eqs 2-4). Bultinck's and Mathieu's energy is chi Q + eta Q^2, so J_II = 2 eta and the
    screening length is 1/(4 eta_i) + 1/(4 eta_j). Atomic units throughout."""
    screen = 1.0 / (4.0 * eta_i_hartree) + 1.0 / (4.0 * eta_j_hartree)
    return 1.0 / math.sqrt(r_bohr * r_bohr + screen * screen)


def atomic_hessian(elements: list[str], coords, params: Parameters) -> np.ndarray:
    """Eq 8's first two terms in atomic charges: 2 eta on the diagonal (eq 2), the kernel off it."""
    xyz = np.asarray(coords, dtype=float) / ce.EEM_BOHR_ANGSTROM
    n = len(elements)
    eta = [params.eta_ev[e] / ce.HARTREE_EV for e in elements]
    h = np.zeros((n, n))
    for a in range(n):
        # 2.4's operation order, kept so its committed outputs do not move by a rounding bit.
        h[a, a] = 2.0 * params.eta_ev[elements[a]] / ce.HARTREE_EV
        for b in range(n):
            if a != b:
                r = float(np.linalg.norm(xyz[a] - xyz[b]))
                h[a, b] = ohno_klopman(r, eta[a], eta[b]) if params.kernel == "ohno_klopman" else 1.0 / r
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


def _linear_solve(a: np.ndarray, b: np.ndarray, rcond: float, scaled: bool) -> tuple[np.ndarray, np.ndarray]:
    """(q, singular values of the matrix actually factorised). `scaled` is 2.6c's Jacobi arm:
    (D^-1/2 A D^-1/2) y = D^-1/2 b, q = D^-1/2 y, with the same lstsq and rcond. A relative rcond
    is relative to the largest singular value, which a near-cutoff penalty K inflates (2.4's
    pentylamine); scaling by the diagonal removes that before the cutoff is applied."""
    if not scaled:
        q, *_ = np.linalg.lstsq(a, b, rcond=rcond)
        return q, np.linalg.svd(a, compute_uv=False)
    s = 1.0 / np.sqrt(np.diag(a))
    a_scaled = a * s[:, None] * s[None, :]
    y, *_ = np.linalg.lstsq(a_scaled, b * s, rcond=rcond)
    return s * y, np.linalg.svd(a_scaled, compute_uv=False)


def solve(elements: list[str], coords, params: Parameters | None = None, *, use_penalty: bool = True, rcond: float = RCOND,
          scaled: bool = False) -> Solution:
    system = assemble(elements, coords, params, use_penalty=use_penalty)
    a, b, m = system["A"], system["b"], system["M"]
    n = len(elements)
    asymmetry = float(np.abs(a - a.T).max()) if a.size else 0.0
    assert asymmetry <= 1e-14, asymmetry
    a = 0.5 * (a + a.T)
    if a.size:
        q, sv = _linear_solve(a, b, rcond, scaled)
        retained = sv[sv > rcond * sv[0]] if sv[0] > 0 else sv[:0]
        # Judged in the original system under both arms (2.6b), so validity means the same thing.
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


#: 2.2's pinned EEM (EQ) values: the baseline 2.4 requires before any discrimination.
EEM_EQ_BASELINE = {"C": 0.9619, "H": 0.8139, "N": 0.9535, "O": 0.6641, "F": 0.3574, "All": 0.9727}
SMALL_N = 30


def atom_rows(set_name: str, params: Parameters | None = None, *, with_sqe: bool = True) -> tuple[list[dict], list[dict]]:
    """Per-atom rows (both arms on one population) and per-structure diagnostics."""
    rows, structures = [], []
    for s in population(SETS[set_name]):
        eem = ce.eem_charges(s["elements"], s["coords"], 0.0)
        reasons = [] if eem.status == "converged" else [f"EEM {eem.status}"]
        sqe = solve(s["elements"], s["coords"], params) if with_sqe else None
        if sqe is not None and not sqe.valid:
            reasons.append(f"SQE {sqe.reason}")
        structures.append({"set": set_name, "file": s["file"], "atoms": len(s["elements"]),
                           **({k: v for k, v in sqe.diagnostics.items() if k != "component_sums"} if sqe else {}),
                           "max_component_sum": max(abs(x) for x in sqe.diagnostics["component_sums"]) if sqe else 0.0,
                           "invalid_reason": "; ".join(reasons)})
        for k, atom in enumerate(s["atoms"]):
            rows.append({"set": set_name, "file": s["file"], "atom": atom, "element": s["elements"][k],
                         "mulliken": s["mulliken"][k], "raw_mulliken": s["raw_mulliken"][k],
                         "eem": float(eem.charges[k]) if eem.charges is not None else math.nan,
                         "sqe": float(sqe.charges[k]) if sqe is not None else math.nan,
                         "included": not reasons, "reason": "; ".join(reasons)})
    return rows, structures


def metric_values(rows: list[dict], arm: str) -> dict:
    """R^2 per metric ID over included atoms, plus the non-gating per-atom diagnostics."""
    included = [r for r in rows if r["included"]]
    out = {}
    for metric in METRICS:
        subset = included if metric == "All" else [r for r in included if r["element"] == metric]
        pred = np.array([r[arm] for r in subset])
        ref = np.array([r["mulliken"] for r in subset])
        err = pred - ref
        defined = len(subset) > 2 and np.std(pred) > 0 and np.std(ref) > 0
        out[metric] = {"n": len(subset), "r2": r_squared(pred, ref) if defined else math.nan,
                       "mean_signed_error": float(err.mean()), "mae": float(np.abs(err).mean()),
                       "rms": float(np.sqrt((err ** 2).mean())), "max_abs_error": float(np.abs(err).max())}
    present = [e for e in ELEMENTS if out[e]["n"]]
    dq = sum(out[e]["rms"] ** 2 for e in present) / len(present)
    out["dq"] = {"eq15_as_printed": dq, "sqrt": math.sqrt(dq)}
    return out


def small_subgroup(rows: list[dict], arm: str, element: str) -> dict:
    subset = [r for r in rows if r["included"] and r["element"] == element]
    pred = np.array([r[arm] for r in subset])
    ref = np.array([r["mulliken"] for r in subset])
    slope, intercept = np.polyfit(pred, ref, 1)
    loo = [r_squared(np.delete(pred, i), np.delete(ref, i)) for i in range(len(subset))]
    return {"n": len(subset), "reference_min": float(ref.min()), "reference_max": float(ref.max()),
            "sse": float(np.sum((ref - slope * pred - intercept) ** 2)), "sst": float(np.sum((ref - ref.mean()) ** 2)),
            "loo_r2_min": float(min(loo)), "loo_r2_max": float(max(loo))}


def in_interval(value: float, printed: float) -> bool:
    """Table I's two-decimal rounding interval [p - 0.005, p + 0.005)."""
    return (not math.isnan(value)) and printed - TOLERANCE <= value < printed + TOLERANCE


def gates(values: dict, printed: dict) -> dict[str, bool]:
    return {m: in_interval(values[m]["r2"], printed[m]) for m in METRICS}


def discrimination(recon: float, sqe_printed: float, eem_printed: float) -> str:
    if round(abs(sqe_printed - eem_printed), 6) < 0.01:
        return "not applicable"
    if abs(recon - sqe_printed) < abs(recon - eem_printed) and not in_interval(recon, eem_printed):
        return "STRICT"
    return "AMBIGUOUS"


def set_verdict(gate: dict[str, bool], classes: dict[str, str], invalid: int) -> str:
    passed = sum(gate.values())
    if passed == len(METRICS):
        if invalid or any(c == "AMBIGUOUS" for c in classes.values()):
            return "AMBIGUOUS" if not invalid else "PARTIAL"
        return "REPRODUCED"
    return "PARTIAL" if passed else "NOT REPRODUCED"


def eem_verdict(gate: dict[str, bool]) -> str:
    passed = sum(gate.values())
    return "REPRODUCED" if passed == len(METRICS) else ("PARTIAL" if passed else "NOT REPRODUCED")


def eem_check(set_name: str) -> dict:
    """The shipped EEM through `population()`: the 2.4 baseline on EQ, check 2.5 on TS."""
    rows, structures = atom_rows(set_name, with_sqe=False)
    values = metric_values(rows, "eem")
    gate = gates(values, PRINTED[("EEM", set_name)])
    return {"rows": rows, "structures": structures, "values": values, "gates": gate, "verdict": eem_verdict(gate),
            "excluded": [s["file"] for s in structures if s["invalid_reason"]]}


def baseline_holds(values: dict) -> bool:
    return all(abs(values[m]["r2"] - EEM_EQ_BASELINE[m]) <= 1e-4 for m in METRICS)


def prose_eq_ts() -> dict:
    """Sec. III.B's "EQ+TS, Delta-q=0.0695, R^2=0.97", recomputed for the shipped EEM: a diagnostic, never an oracle."""
    rows = [r for set_name in ("EQ", "TS") for r in atom_rows(set_name, with_sqe=False)[0]]
    values = metric_values(rows, "eem")
    return {"n": values["All"]["n"], "r2": values["All"]["r2"], **values["dq"]}


def sqe_check(set_name: str, params: Parameters | None = None) -> dict:
    rows, structures = atom_rows(set_name, params)
    sqe_values, eem_values = metric_values(rows, "sqe"), metric_values(rows, "eem")
    printed_sqe, printed_eem = PRINTED[("SQE", set_name)], PRINTED[("EEM", set_name)]
    gate = gates(sqe_values, printed_sqe)
    classes = {m: discrimination(sqe_values[m]["r2"], printed_sqe[m], printed_eem[m]) for m in METRICS}
    invalid = sum(1 for s in structures if s["invalid_reason"])
    return {"rows": rows, "structures": structures, "sqe": sqe_values, "eem": eem_values, "gates": gate,
            "classes": classes, "invalid": invalid, "verdict": set_verdict(gate, classes, invalid)}


def literal_eq13_summary(set_name: str) -> dict:
    negative, minimum, maximum, condition, stationarity, structures = 0, math.inf, -math.inf, 0.0, 0.0, 0
    for s in population(SETS[set_name]):
        report = literal_eq13_diagnostic(s["elements"], s["coords"])
        if "negative_eigenvalues" not in report:
            continue
        structures += 1
        negative += report["negative_eigenvalues"]
        minimum, maximum = min(minimum, report["eigenvalue_min"]), max(maximum, report["eigenvalue_max"])
        condition, stationarity = max(condition, report["condition"]), max(stationarity, report["eq8_stationarity"])
    return {"set": set_name, "structures": structures, "negative_eigenvalues": negative, "eigenvalue_min": minimum,
            "eigenvalue_max": maximum, "condition_max": condition, "eq8_stationarity_max": stationarity}


def rounding_variants() -> list[tuple[str, float, float, Parameters]]:
    base = Parameters()
    out = []
    for e in ("C", "N", "O", "F"):
        for d in (-0.005, 0.005):
            chi = dict(base.chi_ev); chi[e] += d
            out.append((f"chi_{e}-chi_H", TABLE_II_CHI_RELATIVE[e], TABLE_II_CHI_RELATIVE[e] + d, Parameters(chi_ev=chi)))
    for e in ELEMENTS:
        for d in (-0.005, 0.005):
            eta = dict(base.eta_ev); eta[e] += d
            out.append((f"eta_{e}", TABLE_II_ETA[e], TABLE_II_ETA[e] + d, Parameters(eta_ev=eta)))
    for d in (-0.0005, 0.0005):
        out.append(("lambda", LAMBDA, LAMBDA + d, Parameters(lam=LAMBDA + d)))
    for d in (-0.5, 0.5):
        out.append(("C", C_EV, C_EV + d, Parameters(c_ev=C_EV + d)))
    for dl in (-0.0005, 0.0005):
        for dc in (-0.5, 0.5):
            out.append(("lambda,C", float("nan"), float("nan"), Parameters(lam=LAMBDA + dl, c_ev=C_EV + dc)))
    return out


# --- 2.6: the named-cause test ---------------------------------------------------------------


class Prepared:
    """One structure with everything that does not depend on (C, lambda) built once.

    Pairs (V0: van der Waals sums; V1: covalent sums) and M^T H M depend only on radii, the
    kernel and eta, so a surface of thousands of (C, lambda) points rebuilds only K. `solve`
    must equal the module's `solve` exactly, which instrument test 2 holds."""

    def __init__(self, elements: list[str], coords, params: Parameters, *, scaled: bool, key=None, mulliken=None):
        self.key, self.elements, self.scaled = key, list(elements), scaled
        self.mulliken = None if mulliken is None else np.asarray(mulliken, dtype=float)
        self.params = params
        system = assemble(elements, coords, params)
        self.pair_list, self.m, self.b, self.h = system["pairs"], system["M"], system["b"], system["H"]
        self.base = system["M"].T @ system["H"] @ system["M"]
        rc = np.array([params.r_covalent[elements[i]] + params.r_covalent[elements[j]] for i, j, _ in self.pair_list])
        self.r = np.array([r for _, _, r in self.pair_list])
        self.rc = rc
        self.rw = np.array([params.r_vdw[elements[i]] + params.r_vdw[elements[j]] for i, j, _ in self.pair_list])
        self.groups = components(len(elements), self.pair_list)
        self.positive = all(_positive_on_neutral_subspace(self.h, g) for g in self.groups)

    def penalty(self, c_ev: float, lam: float) -> np.ndarray:
        onset = lam * self.rc
        k = np.zeros(len(self.r))
        on = self.r > onset
        k[on] = 2.0 * c_ev * ((self.r[on] - onset[on]) / (self.r[on] - self.rw[on])) ** 2 / ce.HARTREE_EV
        return k

    def solve(self, c_ev: float, lam: float, rcond: float = RCOND) -> tuple[np.ndarray, bool, float]:
        """(charges, valid, residual in Hartree/e) under 2.4b's predicate, judged in the original system."""
        n = len(self.elements)
        if not self.pair_list:
            return np.zeros(n), True, 0.0
        a = self.base + np.diag(self.penalty(c_ev, lam))
        a = 0.5 * (a + a.T)
        q, _ = _linear_solve(a, self.b, rcond, self.scaled)
        residual = float(np.abs(a @ q - self.b).max())
        charges = self.m @ q
        sums_ok = all(abs(float(charges[g].sum())) <= SUM_LIMIT for g in self.groups)
        return charges, residual <= RESIDUAL_LIMIT and sums_ok and self.positive, residual


def prepare_population(params: Parameters, *, scaled: bool, sets=("EQ", "TS")) -> list[Prepared]:
    """Canonical order (2.6b): EQ then TS, file name lexical, source atom order within a file."""
    out = []
    for set_name in sets:
        for s in sorted(population(SETS[set_name]), key=lambda s: s["file"]):
            out.append(Prepared(s["elements"], s["coords"], params, scaled=scaled, key=(set_name, s["file"], tuple(s["atoms"])),
                                mulliken=s["mulliken"]))
    return out


def delta_q(elements: list[str], predicted, reference) -> float:
    """Eq 15 as printed: mean squared deviation per element, averaged over the elements present. No root."""
    elements = np.asarray(elements)
    err = np.asarray(predicted, dtype=float) - np.asarray(reference, dtype=float)
    present = [e for e in ELEMENTS if (elements == e).any()]
    return float(sum(np.mean(err[elements == e] ** 2) for e in present) / len(present))


class Objective:
    """Pooled eq 15 over a population FIXED at construction (2.6b): an evaluation where any member
    fails the predicate is flagged, never re-populated, so the objective cannot jump."""

    def __init__(self, prepared: list[Prepared], members: list[int]):
        self.prepared, self.members = prepared, list(members)
        self.elements = [e for i in self.members for e in prepared[i].elements]
        self.reference = np.concatenate([prepared[i].mulliken for i in self.members])
        self.evaluations = 0

    def charges(self, c_ev: float, lam: float) -> tuple[np.ndarray, list[int]]:
        parts, violations = [], []
        for i in self.members:
            q, valid, _ = self.prepared[i].solve(c_ev, lam)
            parts.append(q)
            if not valid:
                violations.append(i)
        self.evaluations += 1
        return np.concatenate(parts), violations

    def __call__(self, c_ev: float, lam: float) -> tuple[float, bool]:
        q, violations = self.charges(c_ev, lam)
        return delta_q(self.elements, q, self.reference), bool(violations)


def valid_members(prepared: list[Prepared], c_ev: float, lam: float) -> list[int]:
    return [i for i, p in enumerate(prepared) if p.solve(c_ev, lam)[1]]


def rounding_delta(printed: float, half_unit: float = 5e-5) -> float:
    """2.6d step 5: the largest eq 15 change consistent with a printed sqrt(Delta-q), half-up."""
    return max((printed + half_unit) ** 2 - printed ** 2, printed ** 2 - (printed - half_unit) ** 2)


def prose_class(value: float, printed: float, near: float = 1.1e-4) -> str:
    """2.6d P: PASS inside [p - 5e-5, p + 5e-5); NEAR within twice the EEM analogue's own miss."""
    # 1e-12 absorbs the binary representation of p +/- 5e-5 (0.0695 - 5e-5 is a hair above 0.06945).
    if printed - 5e-5 - 1e-12 <= value < printed + 5e-5 - 1e-12:
        return "PASS"
    return "NEAR" if abs(value - printed) <= near else "MISS"


#: 2.6d step 2 and the scaled coordinates of step 4.
STEPS_C = (1.0, 0.5, 0.25)
STEPS_LAMBDA = (2e-3, 1e-3, 5e-4)
SCALE = np.array([C_EV, LAMBDA])
TRUST_CONDITION = 1e8


def fd_derivatives(f, point, h_c: float, h_l: float) -> tuple[np.ndarray, np.ndarray]:
    """Central-difference gradient and Hessian of a scalar f(C, lambda), physical units."""
    c, l = point
    f0 = f(c, l)
    fcp, fcm, flp, flm = f(c + h_c, l), f(c - h_c, l), f(c, l + h_l), f(c, l - h_l)
    g = np.array([(fcp - fcm) / (2 * h_c), (flp - flm) / (2 * h_l)])
    hcc = (fcp - 2 * f0 + fcm) / h_c ** 2
    hll = (flp - 2 * f0 + flm) / h_l ** 2
    hcl = (f(c + h_c, l + h_l) - f(c + h_c, l - h_l) - f(c - h_c, l + h_l) + f(c - h_c, l - h_l)) / (4 * h_c * h_l)
    return g, np.array([[hcc, hcl], [hcl, hll]])


def to_scaled(g: np.ndarray, hess: np.ndarray, scale=SCALE) -> tuple[np.ndarray, np.ndarray]:
    """Chain rule for x = s * u: dF/du = s dF/dx, d2F/du2 = s_i s_j d2F/dx2."""
    s = np.asarray(scale, dtype=float)
    return g * s, hess * np.outer(s, s)


def stationarity(f, point, delta: float) -> dict:
    """2.6d S at one point: the step study, the physical and scaled derivatives, and the class."""
    estimates = [fd_derivatives(f, point, hc, hl) for hc, hl in zip(STEPS_C, STEPS_LAMBDA)]
    grads = np.array([e[0] for e in estimates])
    spread = np.abs(grads - grads[1]).max(axis=0)
    gradient_ok = bool(np.all((spread <= 0.01 * np.abs(grads[1])) | (spread <= 1e-12)))
    g, hess = estimates[1]
    gs, hs = to_scaled(g, hess)
    eig = np.linalg.eigvalsh(hs)
    condition = float(eig.max() / eig.min()) if eig.min() > 0 else math.inf
    trusted = gradient_ok and eig.min() > 0 and condition <= TRUST_CONDITION
    predicted = float(0.5 * gs @ np.linalg.solve(hs, gs)) if eig.min() > 0 else math.nan
    g_tol = math.sqrt(2.0 * delta * eig.min()) if eig.min() > 0 else math.nan
    norm = float(np.linalg.norm(gs))
    if not trusted:
        label = "UNRELIABLE"
    elif norm <= g_tol and predicted < delta:
        label = "STATIONARY-AT-POINT"
    else:
        label = "NON-STATIONARY-AT-POINT"
    return {"point": tuple(point), "value": float(f(*point)), "gradient": g, "hessian": hess, "gradient_scaled": gs,
            "hessian_scaled": hs, "eigenvalues_scaled": eig, "condition_scaled": condition, "gradient_estimates": grads,
            "gradient_ok": gradient_ok, "trusted": bool(trusted), "predicted_improvement": predicted, "g_tol": g_tol,
            "gradient_norm_scaled": norm, "delta": delta, "class": label}


#: 2.6d surface: both axes contain the printed point exactly.
GRID_C = tuple(60.0 + 5.0 * k for k in range(29))
GRID_LAMBDA = tuple(round(0.6 + 0.024 * k, 6) for k in range(17))
BOX = ((1.0, 400.0), (0.3, 1.5))
DISTANT = ((60.0, 0.6), (200.0, 0.6), (60.0, 1.0), (200.0, 1.0))
NEIGHBOURHOOD = (2.0, 0.01)


def grid_minima(grid: dict) -> list[tuple[float, float]]:
    """Unflagged points no 8-neighbour of which is lower (ties count as minima)."""
    cs, ls = sorted({c for c, _ in grid}), sorted({l for _, l in grid})
    out = []
    for i, c in enumerate(cs):
        for j, l in enumerate(ls):
            value, flagged = grid[(c, l)]
            if flagged:
                continue
            neighbours = [grid[(cs[a], ls[b])] for a in range(i - 1, i + 2) for b in range(j - 1, j + 2)
                          if (a, b) != (i, j) and 0 <= a < len(cs) and 0 <= b < len(ls)]
            if all(value <= v for v, fl in neighbours if not fl):
                out.append((c, l))
    return out


def powell(f, start, *, box=BOX, scale=SCALE) -> dict:
    """scipy's Powell in scaled coordinates u = x / scale, with the box as bounds. Returns physical units."""
    from scipy.optimize import minimize

    s = np.asarray(scale, dtype=float)
    bounds = [(lo / s[k], hi / s[k]) for k, (lo, hi) in enumerate(box)]
    result = minimize(lambda u: f(*(u * s)), np.asarray(start, dtype=float) / s, method="Powell", bounds=bounds,
                      options={"xtol": 1e-8, "ftol": 1e-12, "maxfev": 2000})
    end = result.x * s
    return {"start": tuple(float(v) for v in start), "end": (float(end[0]), float(end[1])), "value": float(result.fun),
            "success": bool(result.success), "message": str(result.message), "nit": int(result.nit), "nfev": int(result.nfev)}


def label_basins(ends: list[tuple[float, float]], scale=SCALE, tol: float = 1e-3) -> list[int]:
    labels, reps = [], []
    for e in ends:
        u = np.asarray(e) / scale
        for k, r in enumerate(reps):
            if np.all(np.abs(u - r) < tol):
                labels.append(k)
                break
        else:
            reps.append(u)
            labels.append(len(reps) - 1)
    return labels


def within_neighbourhood(point, centre=(C_EV, LAMBDA), width=NEIGHBOURHOOD) -> bool:
    return abs(point[0] - centre[0]) <= width[0] and abs(point[1] - centre[1]) <= width[1]


def s_verdict(at_printed: str, verified_nearby: bool, verified_basin_values: list[float], delta: float) -> str:
    rival = sorted(verified_basin_values)
    several = len(rival) >= 2 and rival[1] - rival[0] <= delta
    if at_printed == "STATIONARY-AT-POINT" and verified_nearby and not several:
        return "STATIONARY"
    if at_printed == "NON-STATIONARY-AT-POINT" and not verified_nearby and not several:
        return "NON-STATIONARY"
    return "INCONCLUSIVE"


def table3_rows() -> list[dict]:
    path = FIXTURES / "mathieu2007_table3.csv"
    return list(csv.DictReader(line for line in path.read_text(encoding="utf-8").splitlines() if not line.startswith("#")))


def t_oracle(charges_by_atom: dict, rows: list[dict] | None = None) -> dict:
    """2.6d T: every identified Table III atom within 5e-4 of its printed SQE charge."""
    out = []
    for r in rows or table3_rows():
        key = (r["set"], r["file"], int(r["atom"]))
        if key not in charges_by_atom:
            out.append({**r, "model": None, "status": "not evaluable"})
            continue
        q = charges_by_atom[key]
        out.append({**r, "model": q, "status": "pass" if abs(q - float(r["q_printed"])) <= 5e-4 + 1e-12 else "fail"})
    evaluable = [o for o in out if o["status"] != "not evaluable"]
    return {"rows": out, "passed": bool(evaluable) and all(o["status"] == "pass" for o in evaluable),
            "failures": [(o["file"], o["atom"]) for o in out if o["status"] == "fail"],
            "not_evaluable": [(o["file"], o["atom"]) for o in out if o["status"] == "not evaluable"]}


def verdict_26(s: str, gates_all: bool, gates_any: bool, t_pass: bool, p: str) -> tuple[str, str]:
    """2.6f, rows top to bottom, first match. Returns (local class, universal status)."""
    if s == "STATIONARY" and gates_all and t_pass and p in ("PASS", "NEAR"):
        return "COMPATIBLE", "REPRODUCED"
    if gates_all and s != "STATIONARY":
        return "G-compatible, S-incompatible", "PARTIAL"
    if s == "STATIONARY" and not gates_all:
        return "S-stationary, G-incompatible", "PARTIAL"
    if gates_any or t_pass or p in ("PASS", "NEAR"):
        return "PARTIAL", "PARTIAL"
    if s == "NON-STATIONARY" and p == "MISS" and not t_pass:
        return "INCOMPATIBLE", "INCOMPATIBLE"
    return "INCONCLUSIVE", "INCONCLUSIVE"


def _write(path: pathlib.Path, header: str, columns: list[str], rows: list[list]) -> None:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    path.write_text(f"# {header}\n" + buffer.getvalue(), encoding="utf-8", newline="\n")


def _f(x: float) -> str:
    return "" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x + 0.0:.6f}".replace("-0.000000", "0.000000")


def main() -> None:
    eq_eem = eem_check("EQ")
    print("EEM baseline holds:", baseline_holds(eq_eem["values"]))
    if not baseline_holds(eq_eem["values"]):
        raise SystemExit("2.4 stops: the EEM baseline does not reproduce 2.2")
    results = {s: sqe_check(s) for s in ("EQ", "TS")}
    _write(HERE / "mathieu_sqe_atoms.csv", "TRIAGE 2.4: one row per deposited atom; every metric recomputes from this file alone.",
           ["set", "file", "atom", "element", "mulliken", "eem", "sqe", "included", "reason"],
           [[r["set"], r["file"], r["atom"], r["element"], r["raw_mulliken"], f"{r['eem']:.8f}", f"{r['sqe']:.8f}", r["included"], r["reason"]]
            for s in results.values() for r in s["rows"]])
    metric_rows = []
    for set_name, res in results.items():
        for m in METRICS:
            p_sqe, p_eem = PRINTED[("SQE", set_name)][m], PRINTED[("EEM", set_name)][m]
            v, e = res["sqe"][m], res["eem"][m]
            metric_rows.append([set_name, m, v["n"], p_sqe, f"{p_sqe - TOLERANCE:.3f}", f"{p_sqe + TOLERANCE:.3f}", p_eem,
                                _f(v["r2"]), _f(e["r2"]), _f(abs(v["r2"] - p_sqe)), _f(abs(v["r2"] - p_eem)),
                                res["gates"][m], res["classes"][m], _f(v["r2"] - e["r2"]),
                                _f(v["mean_signed_error"]), _f(v["mae"]), _f(v["rms"]), _f(v["max_abs_error"])])
    _write(HERE / "mathieu_sqe_metrics.csv", "TRIAGE 2.4: per set and metric. Interval is [low, high); gates on R^2 only.",
           ["set", "metric", "n", "printed_sqe", "interval_low", "interval_high", "printed_eem", "sqe_r2", "eem_r2",
            "abs_to_printed_sqe", "abs_to_printed_eem", "gate", "discrimination", "sqe_minus_eem", "mean_signed_error", "mae", "rms", "max_abs_error"],
           metric_rows)
    _write(HERE / "mathieu_sqe_structures.csv", "TRIAGE 2.4: per-structure solver diagnostics (Hartree/e residuals; singular values in Hartree).",
           ["set", "file", "atoms", "pairs", "components", "sigma_max", "sigma_min_retained", "condition", "discarded", "cycle_dimension",
            "residual_hartree", "max_component_sum", "h_positive_on_neutral_subspace", "invalid_reason"],
           [[s["set"], s["file"], s["atoms"], s["pairs"], s["components"], f"{s['sigma_max']:.6e}", f"{s['sigma_min_retained']:.6e}",
             f"{s['condition']:.6e}", s["discarded"], s["cycle_dimension"], f"{s['residual_hartree']:.3e}", f"{s['max_component_sum']:.3e}",
             s["h_positive_on_neutral_subspace"], s["invalid_reason"]] for res in results.values() for s in res["structures"]])
    for set_name, res in results.items():
        print(f"\n{set_name}: verdict {res['verdict']}, invalid {res['invalid']}")
        for m in METRICS:
            v = res["sqe"][m]
            print(f"  {m:3} n={v['n']:5} SQE {v['r2']:.4f} (printed {PRINTED[('SQE', set_name)][m]}) EEM {res['eem'][m]['r2']:.4f} "
                  f"gate {res['gates'][m]} {res['classes'][m]}")
        print("  dq", res["sqe"]["dq"], "printed", PRINTED[("SQE", set_name)]["dq"])
        for e in ELEMENTS:
            if res["sqe"][e]["n"] < SMALL_N:
                print("  small", e, small_subgroup(res["rows"], "sqe", e))
    eq13 = [literal_eq13_summary(s) for s in ("EQ", "TS")]
    _write(HERE / "mathieu_sqe_eq13.csv", "TRIAGE 2.4: the literal eq 12/13 system per set (Hartree). A source record, not a model.",
           list(eq13[0]), [[_f(v) if isinstance(v, float) else v for v in row.values()] for row in eq13])
    print("\nliteral eq 13:", eq13)
    rounding = []
    baseline = {s: {m: results[s]["sqe"][m]["r2"] for m in METRICS} for s in results}
    for name, base, perturbed, params in rounding_variants():
        for set_name in ("EQ", "TS"):
            rows, _ = atom_rows(set_name, params)
            values = metric_values(rows, "sqe")
            for m in METRICS:
                rounding.append([name, _f(base), _f(perturbed), f"lambda {params.lam:.4f} C {params.c_ev:.1f}" if name == "lambda,C" else "",
                                 set_name, m, _f(values[m]["r2"] - baseline[set_name][m])])
    _write(HERE / "mathieu_sqe_rounding.csv", "TRIAGE 2.4: one parameter at a time at its printed rounding, then the lambda x C corners.",
           ["parameter", "baseline", "perturbed", "corner", "set", "metric", "delta_r2"], rounding)
    worst = max(abs(float(r[-1])) for r in rounding)
    print(f"rounding: {len(rounding)} rows, max |delta R^2| {worst:.5f}")


# --- 2.6 driver ---------------------------------------------------------------------------------


class Tracked:
    """f(C, lambda) -> Delta-q for the finite-difference and Powell code, remembering whether any
    evaluation it made hit a population violation (2.6b: such points never classify anything)."""

    def __init__(self, objective: Objective):
        self.objective, self.flagged = objective, False

    def __call__(self, c_ev: float, lam: float) -> float:
        value, flagged = self.objective(c_ev, lam)
        self.flagged = self.flagged or flagged
        return value

    def fresh(self) -> "Tracked":
        return Tracked(self.objective)


def _rows_for(prepared: list[Prepared], members: list[int], charges: np.ndarray) -> list[dict]:
    rows, offset = [], 0
    for i in members:
        p = prepared[i]
        set_name, file, atoms = p.key
        for k, atom in enumerate(atoms):
            rows.append({"set": set_name, "file": file, "atom": atom, "element": p.elements[k], "mulliken": float(p.mulliken[k]),
                         "sqe": float(charges[offset + k]), "included": True})
        offset += len(atoms)
    return rows


def _stationarity_at(objective: Objective, point, delta: float) -> dict:
    f = Tracked(objective)
    report = stationarity(f, point, delta)
    if f.flagged:
        report["class"], report["trusted"] = "UNRELIABLE", False
    report["population_violation"] = f.flagged
    return report


def _verified(report: dict) -> bool:
    return report["class"] == "STATIONARY-AT-POINT" and bool(np.all(report["eigenvalues_scaled"] > 0))


def s_study(objective: Objective, arm: str, delta: float, surface_rows: list, powell_rows: list, stationarity_rows: list) -> dict:
    """2.6d S for one arm: the printed point, the surface, Powell from every start, the verdict."""
    printed = _stationarity_at(objective, (C_EV, LAMBDA), delta)
    stationarity_rows.append((arm, "printed", printed))
    grid = {}
    for c in GRID_C:
        for l in GRID_LAMBDA:
            grid[(c, l)] = objective(c, l)
            surface_rows.append([arm, "coarse", c, l, grid[(c, l)][0], grid[(c, l)][1], (c, l) == (C_EV, LAMBDA)])
    starts = [("printed", (C_EV, LAMBDA))]
    dc, dl = GRID_C[1] - GRID_C[0], GRID_LAMBDA[1] - GRID_LAMBDA[0]
    for c0, l0 in grid_minima(grid):
        sub = {}
        for c in np.linspace(c0 - dc, c0 + dc, 11):
            for l in np.linspace(l0 - dl, l0 + dl, 11):
                if BOX[0][0] <= c <= BOX[0][1] and BOX[1][0] <= l <= BOX[1][1]:
                    sub[(float(c), float(l))] = objective(float(c), float(l))
                    surface_rows.append([arm, f"refine({c0:g},{l0:g})", float(c), float(l), sub[(float(c), float(l))][0],
                                         sub[(float(c), float(l))][1], False])
        clean = {k: v for k, v in sub.items() if not v[1]}
        if clean:
            starts.append(("grid minimum", min(clean, key=lambda k: clean[k][0])))
    starts += [("distant", p) for p in DISTANT]
    runs = []
    for kind, start in starts:
        f = Tracked(objective)
        run = powell(f, start)
        end_report = _stationarity_at(objective, run["end"], delta)
        run.update(kind=kind, flagged=f.flagged or end_report["population_violation"], end_report=end_report,
                   verified=_verified(end_report) and not f.flagged, nearby=within_neighbourhood(run["end"]))
        runs.append(run)
        stationarity_rows.append((arm, f"powell end from {kind} {start}", end_report))
    for run, basin in zip(runs, label_basins([r["end"] for r in runs])):
        run["basin"] = basin
        powell_rows.append([arm, run["kind"], *run["start"], *run["end"], run["value"], run["nit"], run["nfev"], run["success"],
                            run["message"], basin, run["nearby"], run["verified"], run["flagged"]])
    verified_basins = {}
    for run in runs:
        if run["verified"]:
            verified_basins.setdefault(run["basin"], run["value"])
    verified_nearby = any(r["verified"] and r["nearby"] for r in runs)
    at_printed = printed["class"]
    return {"printed": printed, "runs": runs, "verified_nearby": verified_nearby, "verified_basins": verified_basins,
            "verdict": s_verdict(at_printed, verified_nearby, list(verified_basins.values()), delta)}


def g_study(rows: list[dict], sets=("EQ", "TS")) -> dict:
    out = {}
    for set_name in sets:
        subset = [r for r in rows if r["set"] == set_name]
        values = metric_values(subset, "sqe")
        out[set_name] = {"values": values, "gates": gates(values, PRINTED[("SQE", set_name)])}
    return out


def arm_study(label: str, params: Parameters, scaled: bool, delta: float, outputs: dict) -> dict:
    prepared = prepare_population(params, scaled=scaled)
    members = valid_members(prepared, params.c_ev, params.lam)
    objective = Objective(prepared, members)
    charges, _ = objective.charges(params.c_ev, params.lam)
    rows = _rows_for(prepared, members, charges)
    by_atom = {(r["set"], r["file"], r["atom"]): r["sqe"] for r in rows}
    pooled = metric_values(rows, "sqe")
    p_value = pooled["dq"]["sqrt"]
    result = {"label": label, "prepared": prepared, "members": members, "rows": rows, "by_atom": by_atom,
              "g": g_study(rows), "t": t_oracle(by_atom), "p": {"sqrt_dq": p_value, "class": prose_class(p_value, PROSE_MODEL_B_DQ)},
              "pooled": pooled}
    result["s"] = s_study(objective, label, delta, outputs["surface"], outputs["powell"], outputs["stationarity"])
    gate_values = [v for s in result["g"].values() for v in s["gates"].values()]
    result["verdict"] = verdict_26(result["s"]["verdict"], all(gate_values), any(gate_values), result["t"]["passed"], result["p"]["class"])
    return result


def v1_study(factor: float) -> dict:
    """2.6e V1 on EQ: applicability, then V1 and V0-scaled on the V1-applicable population."""
    v1_params = Parameters(pair_rule="bond_graph", bond_factor=factor)
    v1 = prepare_population(v1_params, scaled=True, sets=("EQ",))
    v0 = prepare_population(Parameters(), scaled=True, sets=("EQ",))
    applicable, reasons = [], {}
    for i, p in enumerate(v1):
        problems = valence_problems(p.elements, p.pair_list)
        valid = p.solve(C_EV, LAMBDA)[1] and v0[i].solve(C_EV, LAMBDA)[1]
        if problems or not valid:
            reasons[p.key[1]] = "; ".join(problems) or "solver predicate failed"
        else:
            applicable.append(i)
    out = {"factor": factor, "applicable": applicable, "reasons": reasons, "source": len(v1)}
    for name, prepared in (("V1", v1), ("V0-scaled", v0)):
        charges, _ = Objective(prepared, applicable).charges(C_EV, LAMBDA)
        rows = _rows_for(prepared, applicable, charges)
        out[name] = {"g": g_study(rows, sets=("EQ",)), "t": t_oracle({(r["set"], r["file"], r["atom"]): r["sqe"] for r in rows},
                                                                        [r for r in table3_rows() if r["set"] == "EQ"])}
    gate_values = list(out["V1"]["g"]["EQ"]["gates"].values())
    out["verdict"] = verdict_26("NOT APPLICABLE", all(gate_values), any(gate_values), out["V1"]["t"]["passed"], "NOT APPLICABLE")
    return out


def _population_rows(pop_id: str, prepared: list[Prepared], members, reasons=None) -> list[list]:
    members = set(members)
    return [[pop_id, p.key[0], p.key[1], len(p.elements), i in members, (reasons or {}).get(p.key[1], "")] for i, p in enumerate(prepared)]


def main_causes() -> None:
    import scipy

    eem = prose_eq_ts()
    print(f"EEM pooled sqrt(dq) {eem['sqrt']:.6f} (section 3.5: {EEM_POOLED_SQRT_DQ})")
    if abs(eem["sqrt"] - EEM_POOLED_SQRT_DQ) > 1e-6:
        raise SystemExit("2.6 stops: the EEM analogue of P does not recur")
    delta = rounding_delta(PROSE_MODEL_B_DQ)
    outputs = {"surface": [], "powell": [], "stationarity": []}
    arms = {
        "V0-unscaled": arm_study("V0-unscaled", Parameters(), False, delta, outputs),
        "V0-scaled": arm_study("V0-scaled", Parameters(), True, delta, outputs),
        "V2-scaled": arm_study("V2-scaled", Parameters(kernel="ohno_klopman"), True, delta, outputs),
    }
    common = sorted(set(arms["V0-unscaled"]["members"]) & set(arms["V0-scaled"]["members"]))
    cross = {}
    for label in ("V0-unscaled", "V0-scaled"):
        arm = arms[label]
        charges, _ = Objective(arm["prepared"], common).charges(C_EV, LAMBDA)
        rows = _rows_for(arm["prepared"], common, charges)
        cross[label] = {"g": g_study(rows), "pooled": metric_values(rows, "sqe"), "by_atom": {(r["set"], r["file"], r["atom"]): r["sqe"] for r in rows}}
    differing = []
    for i in sorted(set(arms["V0-unscaled"]["members"]) ^ set(arms["V0-scaled"]["members"])):
        pu, ps = arms["V0-unscaled"]["prepared"][i], arms["V0-scaled"]["prepared"][i]
        qu, vu, ru = pu.solve(C_EV, LAMBDA)
        qs, vs, rs = ps.solve(C_EV, LAMBDA)
        with_s = sorted(set(common) | {i})
        charges, _ = Objective(ps if vs else pu, with_s).charges(C_EV, LAMBDA)
        rows = _rows_for(ps if vs else pu, with_s, charges)
        values = metric_values(rows, "sqe")
        base = cross["V0-scaled" if vs else "V0-unscaled"]["pooled"]
        differing.append({"file": pu.key[1], "set": pu.key[0], "unscaled_valid": vu, "scaled_valid": vs, "residual_unscaled": ru,
                          "residual_scaled": rs, "max_charge_difference": float(np.abs(qu - qs).max()),
                          "dq_difference": values["dq"]["eq15_as_printed"] - base["dq"]["eq15_as_printed"],
                          "r2_all_difference": values["All"]["r2"] - base["All"]["r2"]})
    model_c_rows = {}
    for label, scaled in (("V0-unscaled", False), ("V0-scaled", True)):
        prepared = prepare_population(model_c(), scaled=scaled)
        members = valid_members(prepared, MODEL_C["c_ev"], MODEL_C["lam"])
        charges, _ = Objective(prepared, members).charges(MODEL_C["c_ev"], MODEL_C["lam"])
        values = metric_values(_rows_for(prepared, members, charges), "sqe")
        model_c_rows[label] = {"n_structures": len(members), "sqrt_dq": values["dq"]["sqrt"], "r2_all": values["All"]["r2"],
                               "dq_class": prose_class(values["dq"]["sqrt"], PROSE_MODEL_C_DQ),
                               "r2_in_interval": in_interval(values["All"]["r2"], PROSE_MODEL_C_R2)}
    v1 = {factor: v1_study(factor) for factor in (1.2, BOND_FACTOR, 1.4)}

    source = arms["V0-scaled"]["prepared"]
    population_rows = (_population_rows("SOURCE_POPULATION", source, range(len(source)))
                       + _population_rows("VALID_V0-unscaled@printed", source, arms["V0-unscaled"]["members"])
                       + _population_rows("VALID_V0-scaled@printed", source, arms["V0-scaled"]["members"])
                       + _population_rows("COMMON_VALID", source, common)
                       + _population_rows("VALID_V2-scaled@printed", source, arms["V2-scaled"]["members"])
                       + _population_rows("V1-applicable@1.3 (EQ)", prepare_population(Parameters(), scaled=True, sets=("EQ",)),
                                          v1[BOND_FACTOR]["applicable"], v1[BOND_FACTOR]["reasons"]))
    _write(HERE / "mathieu_sqe_population.csv", "TRIAGE 2.6b: membership of every structure in every population, canonical order.",
           ["population_id", "set", "file", "atoms", "member", "reason"], population_rows)
    _write(HERE / "mathieu_sqe_surface.csv", "TRIAGE 2.6d: pooled eq 15 (no root) on each arm's population fixed at the printed point.",
           ["arm", "stage", "c_ev", "lambda", "dq", "population_violation", "printed_point"],
           [[a, s, f"{c:.6f}", f"{l:.6f}", f"{v:.12e}", fl, pp] for a, s, c, l, v, fl, pp in outputs["surface"]])
    _write(HERE / "mathieu_sqe_powell.csv", f"TRIAGE 2.6d: scipy {scipy.__version__} Powell in scaled coordinates, bounded; physical units here.",
           ["arm", "start_kind", "start_c_ev", "start_lambda", "end_c_ev", "end_lambda", "end_dq", "nit", "nfev", "success", "message",
            "basin", "within_preregistered_neighbourhood", "verified_minimum", "population_violation"],
           [[a, k, f"{sc:.6f}", f"{sl:.6f}", f"{ec:.6f}", f"{el:.6f}", f"{v:.12e}", nit, nfev, ok, msg, b, nb, ver, fl]
            for a, k, sc, sl, ec, el, v, nit, nfev, ok, msg, b, nb, ver, fl in outputs["powell"]])
    stat_rows = []
    for arm, kind, r in outputs["stationarity"]:
        g, h, gs, hs, est = r["gradient"], r["hessian"], r["gradient_scaled"], r["hessian_scaled"], r["gradient_estimates"]
        stat_rows.append([arm, kind, f"{r['point'][0]:.6f}", f"{r['point'][1]:.6f}", f"{r['value']:.12e}",
                          *[f"{x:.6e}" for x in est.ravel()], f"{g[0]:.6e}", f"{g[1]:.6e}", f"{h[0, 0]:.6e}", f"{h[0, 1]:.6e}",
                          f"{h[1, 1]:.6e}", f"{gs[0]:.6e}", f"{gs[1]:.6e}", f"{hs[0, 0]:.6e}", f"{hs[0, 1]:.6e}", f"{hs[1, 1]:.6e}",
                          f"{r['eigenvalues_scaled'][0]:.6e}", f"{r['eigenvalues_scaled'][1]:.6e}", f"{r['condition_scaled']:.6e}",
                          r["gradient_ok"], r["trusted"], f"{r['gradient_norm_scaled']:.6e}", f"{r['g_tol']:.6e}",
                          f"{r['predicted_improvement']:.6e}", f"{r['delta']:.6e}", r["population_violation"], r["class"]])
    _write(HERE / "mathieu_sqe_stationarity.csv",
           "TRIAGE 2.6d: step study (dC 1, 0.5, 0.25 eV; dlambda 2e-3, 1e-3, 5e-4), physical and scaled (c = C/115, l = lambda/0.816) derivatives.",
           ["arm", "point", "c_ev", "lambda", "dq", "g_c_h1", "g_l_h1", "g_c_h2", "g_l_h2", "g_c_h3", "g_l_h3", "grad_c_per_ev", "grad_lambda",
            "hess_cc", "hess_cl", "hess_ll", "grad_c_scaled", "grad_l_scaled", "hess_cc_scaled", "hess_cl_scaled", "hess_ll_scaled",
            "eig_min_scaled", "eig_max_scaled", "condition_scaled", "gradient_ok", "trusted", "gradient_norm_scaled", "g_tol",
            "predicted_improvement", "delta", "population_violation", "class"], stat_rows)
    cause_rows = []
    for label, arm in arms.items():
        population_id = f"VALID_{label}@printed"
        for set_name, g in arm["g"].items():
            for m in METRICS:
                cause_rows.append([label, population_id, "G", f"{set_name} {m}", _f(g["values"][m]["r2"]), PRINTED[("SQE", set_name)][m],
                                   "pass" if g["gates"][m] else "miss"])
        for t in arm["t"]["rows"]:
            cause_rows.append([label, population_id, "T", f"{t['file']} {t['element']}{t['atom']}", "" if t["model"] is None else f"{t['model']:.6f}",
                               t["q_printed"], t["status"]])
        cause_rows.append([label, population_id, "P", "pooled sqrt(dq)", f"{arm['p']['sqrt_dq']:.6f}", PROSE_MODEL_B_DQ, arm["p"]["class"]])
        cause_rows.append([label, population_id, "S", "printed point", f"{arm['s']['printed']['value']:.12e}", "", arm["s"]["printed"]["class"]])
        cause_rows.append([label, population_id, "S", "verdict", "", "", arm["s"]["verdict"]])
        cause_rows.append([label, population_id, "verdict", "local / universal", "", "", " / ".join(arm["verdict"])])
    for label, c in cross.items():
        for set_name, g in c["g"].items():
            for m in METRICS:
                cause_rows.append([label, "COMMON_VALID", "G", f"{set_name} {m}", _f(g["values"][m]["r2"]), PRINTED[("SQE", set_name)][m],
                                   "pass" if g["gates"][m] else "miss"])
        cause_rows.append([label, "COMMON_VALID", "P", "pooled sqrt(dq)", f"{c['pooled']['dq']['sqrt']:.6f}", PROSE_MODEL_B_DQ,
                           prose_class(c["pooled"]["dq"]["sqrt"], PROSE_MODEL_B_DQ)])
    for d in differing:
        cause_rows.append(["V0 arms", "differing validity", "numerical", f"{d['set']} {d['file']}", "", "",
                           f"unscaled valid {d['unscaled_valid']} ({d['residual_unscaled']:.2e}); scaled valid {d['scaled_valid']} "
                           f"({d['residual_scaled']:.2e}); max |dq_atom| {d['max_charge_difference']:.2e}; "
                           f"pooled dq diff {d['dq_difference']:+.2e}; R2 All diff {d['r2_all_difference']:+.2e}"])
    for label, c in model_c_rows.items():
        cause_rows.append([f"model C {label}", f"VALID_{label}@model C", "P_C diagnostic", "pooled sqrt(dq)", f"{c['sqrt_dq']:.6f}", PROSE_MODEL_C_DQ, c["dq_class"]])
        cause_rows.append([f"model C {label}", f"VALID_{label}@model C", "P_C diagnostic", "pooled R2 All", f"{c['r2_all']:.6f}", PROSE_MODEL_C_R2,
                           "in interval" if c["r2_in_interval"] else "outside"])
    for factor, v in v1.items():
        pid = f"V1-applicable@{factor} (EQ)"
        cause_rows.append([f"V1 x{factor}", pid, "population", "applicable / source", len(v["applicable"]), v["source"], ""])
        for name in ("V1", "V0-scaled"):
            g = v[name]["g"]["EQ"]
            for m in METRICS:
                cause_rows.append([f"{name} on {pid}", pid, "G (subpopulation)", f"EQ {m}", _f(g["values"][m]["r2"]), PRINTED[("SQE", "EQ")][m],
                                   "pass" if g["gates"][m] else "miss"])
            cause_rows.append([f"{name} on {pid}", pid, "T (EQ rows)", "all identified", "", "",
                               f"passed {v[name]['t']['passed']}; failures {len(v[name]['t']['failures'])}; not evaluable {len(v[name]['t']['not_evaluable'])}"])
        cause_rows.append([f"V1 x{factor}", pid, "S, P, TS", "", "", "", "NOT APPLICABLE"])
        cause_rows.append([f"V1 x{factor}", pid, "verdict", "local / universal", "", "", " / ".join(v["verdict"])])
    _write(HERE / "mathieu_sqe_causes.csv", "TRIAGE 2.6: every oracle, per variant, arm and population. Long format.",
           ["variant_arm", "population_id", "oracle", "item", "value", "printed", "result"], cause_rows)

    for label, arm in arms.items():
        s = arm["s"]
        print(f"\n{label}: population {len(arm['members'])}/249; verdict {arm['verdict']}")
        print(f"  P pooled sqrt(dq) {arm['p']['sqrt_dq']:.6f} vs {PROSE_MODEL_B_DQ}: {arm['p']['class']}")
        pr = s["printed"]
        print(f"  S printed: dq {pr['value']:.8e} grad_scaled {pr['gradient_scaled']} |g| {pr['gradient_norm_scaled']:.3e} g_tol {pr['g_tol']:.3e} "
              f"pred {pr['predicted_improvement']:.3e} delta {delta:.3e} eig {pr['eigenvalues_scaled']} -> {pr['class']}")
        for run in s["runs"]:
            print(f"  powell {run['kind']:13} {run['start']} -> ({run['end'][0]:.3f}, {run['end'][1]:.5f}) dq {run['value']:.8e} "
                  f"basin {run['basin']} nearby {run['nearby']} verified {run['verified']} flagged {run['flagged']}")
        print(f"  S verdict {s['verdict']}; verified basins {s['verified_basins']}")
        print("  G", {k: {m: round(v['values'][m]['r2'], 4) for m in METRICS} for k, v in arm["g"].items()})
        print("  G gates", {k: sum(v["gates"].values()) for k, v in arm["g"].items()}, "T", arm["t"]["passed"], "failures", arm["t"]["failures"])
    print("\ncommon valid:", len(common), "differing:", differing)
    print("model C:", model_c_rows)
    for factor, v in v1.items():
        print(f"V1 x{factor}: applicable {len(v['applicable'])}/{v['source']}; V1 gates {sum(v['V1']['g']['EQ']['gates'].values())}/6 "
              f"V0 gates {sum(v['V0-scaled']['g']['EQ']['gates'].values())}/6; verdict {v['verdict']}")


if __name__ == "__main__":
    if "--causes" in sys.argv:
        main_causes()
    else:
        main()
