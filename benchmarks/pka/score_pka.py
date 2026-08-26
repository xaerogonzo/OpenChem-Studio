"""Is pkasolver actually inaccurate, or is acetic acid a bad advert for it?

The External Tools Test button reports acetic acid: predicted 4.19 against
a literature 4.76, which reads badly. Measure it against a spread of
well-established values instead of judging from one.

Literature pKa values are standard textbook figures in water at 25 C.
Compounds are chosen to be unambiguous: one dominant ionizable centre,
well separated from any other.
"""

from __future__ import annotations

import sys
from pathlib import Path

from openchem.chem.pka_providers import compute_pka
from rdkit import Chem

# The sibling `_config` reads the SAME Settings the application uses, so
# this benchmark measures the pkasolver install the app actually runs.
# It carried that path as a literal until 2026-08-26, which is the exact
# drift `_config`'s own docstring exists to prevent.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "docking"))

from _config import pka_interpreter  # noqa: E402

INTERPRETER = pka_interpreter()

# (name, SMILES, literature pKa, kind)
CASES = [
    ("formic acid", "OC=O", 3.75, "acid"),
    ("acetic acid", "CC(=O)O", 4.76, "acid"),
    ("propionic acid", "CCC(=O)O", 4.87, "acid"),
    ("chloroacetic acid", "OC(=O)CCl", 2.86, "acid"),
    ("phenylacetic acid", "OC(=O)Cc1ccccc1", 4.31, "acid"),
    ("benzoic acid", "OC(=O)c1ccccc1", 4.20, "acid"),
    ("4-nitrobenzoic acid", "OC(=O)c1ccc(cc1)[N+](=O)[O-]", 3.44, "acid"),
    ("ibuprofen", "CC(C)Cc1ccc(cc1)C(C)C(=O)O", 4.91, "acid"),
    ("aspirin", "CC(=O)Oc1ccccc1C(=O)O", 3.49, "acid"),
    ("phenol", "Oc1ccccc1", 9.99, "acid"),
    ("4-methylphenol", "Cc1ccc(O)cc1", 10.26, "acid"),
    ("4-nitrophenol", "Oc1ccc(cc1)[N+](=O)[O-]", 7.15, "acid"),
    ("2,4-dinitrophenol", "Oc1ccc(cc1[N+](=O)[O-])[N+](=O)[O-]", 4.09, "acid"),
    ("paracetamol", "CC(=O)Nc1ccc(O)cc1", 9.38, "acid"),
    ("pyridine", "c1ccncc1", 5.23, "base"),
    ("aniline", "Nc1ccccc1", 4.60, "base"),
    ("imidazole", "c1c[nH]cn1", 6.95, "base"),
    ("methylamine", "CN", 10.66, "base"),
    ("ethylamine", "CCN", 10.65, "base"),
    ("triethylamine", "CCN(CC)CC", 10.75, "base"),
    ("benzylamine", "NCc1ccccc1", 9.34, "base"),
    ("morpholine", "C1COCCN1", 8.36, "base"),
    ("piperidine", "C1CCNCC1", 11.12, "base"),
    ("pyrrolidine", "C1CCNC1", 11.27, "base"),
]

print(f"{'compound':<22} {'lit':>6} {'predicted':<24} {'nearest':>8} {'err':>7} {'n':>2}")
rows = []
for name, smiles, lit, kind in CASES:
    mol = Chem.MolFromSmiles(smiles)
    try:
        got = compute_pka(mol, INTERPRETER)
    except Exception as exc:  # noqa: BLE001
        print(f"{name:<22} {lit:6.2f}  FAILED: {type(exc).__name__} {exc}"[:110])
        continue
    predictions = sorted(got or [], key=lambda prediction: prediction.value)
    values = [prediction.value for prediction in predictions]
    if not values:
        print(f"{name:<22} {lit:6.2f}  (no ionizable centre found)")
        rows.append((name, lit, None, None, kind, 0.0))
        continue
    nearest_prediction = min(predictions, key=lambda p: abs(p.value - lit))
    nearest = nearest_prediction.value
    shown = ", ".join(f"{v:.2f}" for v in values)[:23]
    print(f"{name:<22} {lit:6.2f} {shown:<24} {nearest:>8.2f} {nearest-lit:>+7.2f} {len(values):>2}")
    rows.append((name, lit, nearest, len(values), kind, nearest_prediction.stddev))

scored = [r for r in rows if r[2] is not None]
errs = [abs(r[2] - r[1]) for r in scored]
single = [r for r in scored if r[3] == 1]
single_errs = [abs(r[2] - r[1]) for r in single]
print(f"\nn = {len(scored)} of {len(CASES)}")
print(f"MAE  {sum(errs)/len(errs):.2f}   median {sorted(errs)[len(errs)//2]:.2f}   "
      f"max {max(errs):.2f}   within 1.0 unit: {sum(e <= 1 for e in errs)}/{len(errs)}")
if single_errs:
    print(f"unambiguous (one predicted centre only), n={len(single_errs)}: "
          f"MAE {sum(single_errs)/len(single_errs):.2f}")
for kind in ("acid", "base"):
    k = [abs(r[2] - r[1]) for r in scored if r[4] == kind]
    if k:
        print(f"  {kind:<5} n={len(k):>2}  MAE {sum(k)/len(k):.2f}  max {max(k):.2f}")
worst = sorted(scored, key=lambda r: -abs(r[2] - r[1]))[:5]
print("\nworst five:")
for name, lit, nearest, n, _k, _sd in worst:
    print(f"  {name:<22} lit {lit:5.2f}  predicted {nearest:5.2f}  err {nearest-lit:+.2f}")


# --- Is the ensemble spread worth anything as a warning signal? ---------
#
# The spread is REAL model-reported uncertainty, which is why it is now
# carried through `PkaPrediction` and printed. But "the fifty models
# agreed" is not "the answer is right" -- they share training data and can
# agree while wrong together. Whether it behaves as a usable warning here
# is measurable, so measure it.
import statistics as _st

with_spread = [(r[5], abs(r[2] - r[1])) for r in scored if r[5]]
if with_spread:
    spreads = [s for s, _e in with_spread]
    errs = [e for _s, e in with_spread]
    mean_s, mean_e = _st.fmean(spreads), _st.fmean(errs)
    denom = _st.pstdev(spreads) * _st.pstdev(errs)
    r_value = (
        sum((s - mean_s) * (e - mean_e) for s, e in with_spread) / len(with_spread) / denom
        if denom
        else float("nan")
    )
    print(f"\nensemble spread, n={len(with_spread)}")
    print(f"  mean spread {mean_s:.2f}   mean |error| {mean_e:.2f}")
    print(f"  Pearson r(spread, |error|) = {r_value:+.2f}")
    tight = [e for s, e in with_spread if s <= 0.3]
    wide = [e for s, e in with_spread if s > 0.3]
    if tight and wide:
        print(f"  spread <= 0.30 (n={len(tight)}): mean |error| {_st.fmean(tight):.2f}")
        print(f"  spread >  0.30 (n={len(wide)}): mean |error| {_st.fmean(wide):.2f}")
    tightest_bad = max(with_spread, key=lambda pair: pair[1])
    print(f"  worst error {tightest_bad[1]:.2f} came at a spread of only {tightest_bad[0]:.2f}")
