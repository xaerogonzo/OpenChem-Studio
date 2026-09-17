"""Ionescu 2013 E models: are the solutions minima, and can a blow-up be predicted?

The committed instrument behind `ionescu_src_preregistration.md` sections 4, 6-R and 7-R.
It was first run from a scratch directory; it is assembled here from exactly that source, with
only the imports and paths changed, so the recorded numbers are reproducible:

    uv run --no-sync python benchmarks/charges/models/ionescu_stability.py convexity
    uv run --no-sync python benchmarks/charges/models/ionescu_stability.py guard
    uv run --no-sync python benchmarks/charges/models/ionescu_stability.py alignment

Reads the Ionescu SI from Sci Downloads (not in the repository), so it runs where that folder
exists. Every quantity it reports is unit-independent: the parameters are in "the paper's units",
which nobody here has established.
"""
import importlib.util
import json
import pathlib
import sys

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem

ROOT = pathlib.Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("ionescu_eem_check", pathlib.Path(__file__).resolve().parent / "ionescu_eem_check.py")
ion = importlib.util.module_from_spec(_spec)
sys.modules["ionescu_eem_check"] = ion
_spec.loader.exec_module(ion)

#: Molecules outside these elements have no E-model parameters.
ALLOWED = {"H", "C", "N", "O", "S", "Ca"}
#: The conformer seed every registered run used.
SEED = 20260916
#: Excluded from the shipped set on section 4's Finding 3; kept here as the only source of positives.
EXCLUDED = "E-HiI/6-31G*/PCM"
#: The in-domain maximum |q| over all 12 E models; a solve above it is a registered positive.
POSITIVE_Q = 2.051


def reduced_min_eigenvalue(hessian: np.ndarray) -> float:
    """Smallest eigenvalue of H on {q : sum(q) = 0}, via an orthonormal basis of that subspace."""
    n = hessian.shape[0]
    ones = np.ones((n, 1)) / np.sqrt(n)
    # Complete `ones` to an orthonormal basis; the last n-1 columns span the constraint's null space.
    q, _ = np.linalg.qr(np.hstack([ones, np.eye(n)[:, : n - 1]]))
    basis = q[:, 1:]
    return float(np.linalg.eigvalsh(basis.T @ hessian @ basis).min())


def analyse(elements, coords, parameters) -> dict:
    coords = np.asarray(coords, dtype=float)
    distance = np.linalg.norm(coords[:, None, :] - coords[None, :, :], axis=-1)
    np.fill_diagonal(distance, np.inf)
    b = np.array([parameters["types"][e][1] for e in elements])
    hessian = parameters["kappa"] / distance
    np.fill_diagonal(hessian, b)
    matrix, rhs = ion.eem_system(elements, coords, parameters, "R_angstrom")
    rhs[len(elements)] = 0.0
    charges = np.linalg.solve(matrix, rhs)[: len(elements)]
    return {
        "min_eig": reduced_min_eigenvalue(hessian),
        "cond": float(np.linalg.cond(matrix)),
        "max_abs_q": float(np.max(np.abs(charges))),
        "n": len(elements),
    }


def in_domain():
    for name in ("training_set", "insulin", "ubiquitin"):
        for molecule in ion.dataset(name):
            if molecule["coords"] is None:
                continue
            yield name, molecule["geometry_elements"], molecule["coords"]


def extrapolation():
    corpus = json.loads((ROOT / "benchmarks" / "naming" / "corpus.json").read_text(encoding="utf-8"))
    for item in corpus:
        mol = Chem.MolFromSmiles(item["smiles"])
        if mol is None or Chem.GetFormalCharge(mol) != 0 or mol.GetNumHeavyAtoms() < 3:
            continue
        mol = Chem.AddHs(mol)
        if not {a.GetSymbol() for a in mol.GetAtoms()} <= ALLOWED:
            continue
        params = AllChem.ETKDGv3()
        params.randomSeed = SEED
        if AllChem.EmbedMolecule(mol, params) != 0:
            continue
        AllChem.MMFFOptimizeMolecule(mol)
        pos = mol.GetConformer().GetPositions()
        yield item["label"], [a.GetSymbol() for a in mol.GetAtoms()], pos


def convexity_main() -> None:
    table = ion.table_s1()
    models = sorted(m for m in table if m.startswith("E-"))
    populations = {"IN-DOMAIN": list(in_domain()), "EXTRAPOLATION": list(extrapolation())}
    for label, members in populations.items():
        print(f"{label}: {len(members)} structures")
    print()
    header = f"{'model':22s} {'population':14s} {'n':>4s} {'saddle':>7s} {'%':>6s} {'worst min_eig':>14s} {'median cond':>12s} {'max|q|':>8s}"
    print(header)
    print("-" * len(header))
    summary = {}
    for model in models:
        parameters = table[model]
        for label, members in populations.items():
            rows = [analyse(el, xyz, parameters) for _, el, xyz in members]
            saddle = sum(r["min_eig"] < 0 for r in rows)
            summary[(model, label)] = rows
            print(f"{model:22s} {label:14s} {len(rows):4d} {saddle:7d} {100 * saddle / len(rows):5.1f}% "
                  f"{min(r['min_eig'] for r in rows):14.3e} {np.median([r['cond'] for r in rows]):12.2e} "
                  f"{max(r['max_abs_q'] for r in rows):8.3f}")
    print()
    total_in = sum(sum(r["min_eig"] < 0 for r in summary[(m, "IN-DOMAIN")]) for m in models)
    total_ex = sum(sum(r["min_eig"] < 0 for r in summary[(m, "EXTRAPOLATION")]) for m in models)
    n_in = sum(len(summary[(m, "IN-DOMAIN")]) for m in models)
    n_ex = sum(len(summary[(m, "EXTRAPOLATION")]) for m in models)
    print(f"ALL MODELS  in-domain saddles {total_in}/{n_in}   extrapolation saddles {total_ex}/{n_ex}")


def reduced_spectrum(elements, coords, parameters):
    coords = np.asarray(coords, dtype=float)
    distance = np.linalg.norm(coords[:, None, :] - coords[None, :, :], axis=-1)
    np.fill_diagonal(distance, np.inf)
    hessian = parameters["kappa"] / distance
    np.fill_diagonal(hessian, [parameters["types"][e][1] for e in elements])
    n = len(elements)
    ones = np.ones((n, 1)) / np.sqrt(n)
    basis = np.linalg.qr(np.hstack([ones, np.eye(n)[:, : n - 1]]))[0][:, 1:]
    lam = np.abs(np.linalg.eigvalsh(basis.T @ hessian @ basis))
    return float(lam.max() / lam.min()), float(lam.min())


def guard_main():
    table = ion.table_s1()
    all_models = sorted(m for m in table if m.startswith("E-"))
    shipped = [m for m in all_models if m != EXCLUDED]
    assert len(shipped) == 11, shipped
    domain = list(in_domain())
    extra = list(extrapolation())

    negatives = []
    for m in shipped:
        for name, el, xyz in domain:
            k, lmin = reduced_spectrum(el, xyz, table[m])
            negatives.append((k, lmin, m, name))

    positives, unlabelled = [], []
    for m in all_models:
        for name, el, xyz in extra:
            q = analyse(el, xyz, table[m])["max_abs_q"]
            k, lmin = reduced_spectrum(el, xyz, table[m])
            (positives if q > POSITIVE_Q else unlabelled).append((k, lmin, m, name, q))

    neg_max = max(negatives)
    pos_min = min(positives)
    print(f"negatives (in-domain x 11 shipped): {len(negatives)}")
    print(f"positives (|q| > {POSITIVE_Q}, all 12):   {len(positives)}")
    print(f"unlabelled extrapolation:           {len(unlabelled)}\n")
    print(f"max kappa_R over negatives: {neg_max[0]:.4e}   ({neg_max[2]}, {neg_max[3]})")
    print(f"min kappa_R over positives: {pos_min[0]:.4e}   ({pos_min[2]}, {pos_min[3]}, |q|={pos_min[4]:.2f})")
    verdict = "SEPARABLE" if pos_min[0] > neg_max[0] else "NOT-SEPARABLE"
    print(f"\nVERDICT: {verdict}   margin (min positive / max negative) = {pos_min[0] / neg_max[0]:.3f}\n")

    print("every positive, by kappa_R:")
    for k, lmin, m, name, q in sorted(positives):
        print(f"   kappa_R={k:.3e}  min|lam|={lmin:.2e}  |q|={q:7.2f}  {m:20s} {name}")
    above = [u for u in unlabelled if u[0] >= pos_min[0]]
    print(f"\nunlabelled solves with kappa_R >= the smallest positive's: {len(above)} of {len(unlabelled)}")
    for k, lmin, m, name, q in sorted(above, reverse=True)[:8]:
        print(f"   kappa_R={k:.3e}  |q|={q:6.3f}  {m:20s} {name}")
    worst_neg = sorted(negatives, reverse=True)[:5]
    print("\nthe five highest-kappa_R NEGATIVES (must not be refused):")
    for k, lmin, m, name in worst_neg:
        print(f"   kappa_R={k:.3e}  min|lam|={lmin:.2e}  {m:20s} {name}")


def decompose(elements, coords, parameters, total=0.0):
    """Section 7.1: q = q0 + Z y, R y = g, R = V Lambda V^T, c_k = (v_k . g) / lambda_k."""
    coords = np.asarray(coords, dtype=float)
    n = len(elements)
    distance = np.linalg.norm(coords[:, None, :] - coords[None, :, :], axis=-1)
    np.fill_diagonal(distance, np.inf)
    H = parameters["kappa"] / distance
    np.fill_diagonal(H, [parameters["types"][e][1] for e in elements])
    A = np.array([parameters["types"][e][0] for e in elements])
    q0 = np.full(n, total / n)
    ones = np.ones((n, 1)) / np.sqrt(n)
    Z = np.linalg.qr(np.hstack([ones, np.eye(n)[:, : n - 1]]))[0][:, 1:]
    R = Z.T @ H @ Z
    g = -Z.T @ (A + H @ q0)
    lam, V = np.linalg.eigh(R)
    c = (V.T @ g) / lam
    q = q0 + Z @ (V @ c)
    c2 = c ** 2
    order = np.argsort(np.abs(lam))              # ascending |lambda|
    dominant = int(np.argmax(c2))
    rank = int(np.where(order == dominant)[0][0]) + 1
    smallest_share = float(c2[order[0]] / c2.sum())
    return {
        "q": q,
        "max_abs_q": float(np.max(np.abs(q))),
        "share": float(c2.max() / c2.sum()),
        "rank": rank,
        "smallest_share": smallest_share,
        "alpha": float(np.sqrt(c2.sum()) * np.median(np.abs(lam)) / np.linalg.norm(g)),
    }


def regulatory_validation():
    naming = {Chem.CanonSmiles(i["smiles"]) for i in json.loads((ROOT / "benchmarks" / "naming" / "corpus.json").read_text(encoding="utf-8"))
              if Chem.MolFromSmiles(i["smiles"])}
    reg = json.loads((ROOT / "benchmarks" / "regulatory" / "corpus.json").read_text(encoding="utf-8"))
    # A dict wrapping the list, as the earlier eligibility count found; iterating it directly yields keys.
    reg = reg if isinstance(reg, list) else next(v for v in reg.values() if isinstance(v, list))
    seen, kept, dropped = set(), [], {"embed": 0, "overlap": 0, "charged": 0}
    for item in reg:
        mol = Chem.MolFromSmiles(item["smiles"]) if item.get("smiles") else None
        if mol is None:
            continue
        can = Chem.CanonSmiles(item["smiles"])
        if can in seen:
            continue
        seen.add(can)
        mh = Chem.AddHs(mol)
        if mol.GetNumHeavyAtoms() < 3 or not {a.GetSymbol() for a in mh.GetAtoms()} <= ALLOWED:
            continue
        if Chem.GetFormalCharge(mol) != 0:
            dropped["charged"] += 1
            continue
        if can in naming:
            dropped["overlap"] += 1
            continue
        params = AllChem.ETKDGv3()
        params.randomSeed = SEED
        if AllChem.EmbedMolecule(mh, params) != 0:
            dropped["embed"] += 1
            continue
        AllChem.MMFFOptimizeMolecule(mh)
        kept.append((item["name"], [a.GetSymbol() for a in mh.GetAtoms()], mh.GetConformer().GetPositions()))
    return kept, dropped


def alignment_main():
    table = ion.table_s1()
    all_models = sorted(m for m in table if m.startswith("E-"))
    shipped = [m for m in all_models if m != EXCLUDED]
    domain = list(in_domain())
    calib = list(extrapolation())
    valid, dropped = regulatory_validation()

    # Built-in check: the reduced solve must equal the benchmark's full KKT solve.
    worst = 0.0
    for m in (all_models[0], EXCLUDED):
        for _, el, xyz in calib[:15] + domain[:3]:
            full = ion.eem_charges(el, xyz, 0.0, table[m], "R_angstrom")
            worst = max(worst, float(np.max(np.abs(decompose(el, xyz, table[m])["q"] - full))))
    print(f"CHECK reduced solve vs benchmark full solve: worst |dq| = {worst:.2e}")
    assert worst < 1e-8, "the decomposition does not reproduce the solve; stopping"

    print(f"validation (regulatory, registered size 53): kept {len(valid)}; dropped {dropped}\n")

    neg = [(m, n, decompose(el, xyz, table[m])) for m in shipped for n, el, xyz in domain]
    cal = [(m, n, decompose(el, xyz, table[m])) for m in all_models for n, el, xyz in calib]
    val = [(m, n, decompose(el, xyz, table[m])) for m in all_models for n, el, xyz in valid]
    cal_pos = [r for r in cal if r[2]["max_abs_q"] > POSITIVE_Q]
    val_pos = [r for r in val if r[2]["max_abs_q"] > POSITIVE_Q]

    # ---- Question 1: the mechanism
    pos_ok = all(r[2]["rank"] <= 3 and r[2]["share"] >= 0.5 for r in cal_pos)
    neg_minor = sum(r[2]["smallest_share"] < 0.5 for r in neg)
    neg_ok = neg_minor > len(neg) / 2
    h1 = "SUPPORTED" if (pos_ok and neg_ok) else ("REFUTED" if not pos_ok else "PARTIAL")
    print("QUESTION 1 - mechanism")
    for m, n, r in sorted(cal_pos, key=lambda t: -t[2]["max_abs_q"]):
        print(f"   positive  |q|={r['max_abs_q']:7.2f}  dominant rank={r['rank']}  share={r['share']:.3f}  {n}")
    print(f"   positive half (every positive: rank<=3 and share>=0.5): {pos_ok}")
    print(f"   negative half: smallest-|lambda| mode carries <0.5 in {neg_minor}/{len(neg)} in-domain solves -> majority: {neg_ok}")
    shares = np.array([r[2]["smallest_share"] for r in neg])
    print(f"   in-domain smallest-mode share: median {np.median(shares):.3f}, 90th pct {np.percentile(shares, 90):.3f}, max {shares.max():.3f}")
    print(f"   H1: {h1}\n")

    # ---- Question 2: the scale-free guard
    tau = min(r[2]["alpha"] for r in cal_pos)
    neg_max = max(r[2]["alpha"] for r in neg)
    c1 = tau > neg_max
    if val_pos:
        c2 = all(r[2]["alpha"] >= tau for r in val_pos)
        c2_text = str(c2)
    else:
        c2, c2_text = None, "UNTESTED (no validation positives)"
    val_sound_refused = [r for r in val if r[0] in shipped and r[2]["max_abs_q"] <= POSITIVE_Q and r[2]["alpha"] >= tau]
    c3 = not val_sound_refused
    print("QUESTION 2 - scale-free guard alpha")
    print(f"   tau_alpha (min over {len(cal_pos)} calibration positives): {tau:.4e}")
    print(f"   max alpha over in-domain negatives: {neg_max:.4e}")
    print(f"   criterion 1 (tau > max negative):              {c1}")
    print(f"   criterion 2 (every validation positive >= tau): {c2_text}   [{len(val_pos)} validation positives]")
    print(f"   criterion 3 (no sound shipped validation solve refused): {c3}   [{len(val_sound_refused)} refused]")
    for m, n, r in val_sound_refused[:6]:
        print(f"      would refuse: alpha={r['alpha']:.3e} |q|={r['max_abs_q']:.3f}  {m} {n}")
    for m, n, r in val_pos:
        print(f"   validation positive: |q|={r['max_abs_q']:.2f} alpha={r['alpha']:.3e}  {m} {n}")
    if c1 and c2 is True and c3:
        verdict = "GUARD-VIABLE"
    elif c1 and c2 is None and c3:
        verdict = "GUARD-NOT-CONTRADICTED"
    else:
        verdict = "NOT-VIABLE"
    print(f"\n   VERDICT: {verdict}")
    print(f"   alpha distributions: in-domain negatives median {np.median([r[2]['alpha'] for r in neg]):.3e}; "
          f"calibration positives {sorted(round(r[2]['alpha'], 4) for r in cal_pos)}")

COMMANDS = {"convexity": convexity_main, "guard": guard_main, "alignment": alignment_main}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        sys.exit(f"usage: ionescu_stability.py {{{'|'.join(COMMANDS)}}}")
    COMMANDS[sys.argv[1]]()
