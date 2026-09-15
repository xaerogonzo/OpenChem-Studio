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


if __name__ == "__main__":
    main()
