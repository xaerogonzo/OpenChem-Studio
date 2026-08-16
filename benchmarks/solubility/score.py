"""Step 2 of 2: score the solubility predictor, stratified and with its
refusals counted.

    uv run --no-sync python benchmarks/solubility/score.py

**THIS IS EVIDENCE DISCLOSURE, NOT A RELEASE GATE.** It reports what the
models do; it does not pick a winner and it does not license the word
"validated". The feature ships as a comparative predictor, so a mediocre
MAE is a fact to publish rather than a reason to withhold.

FOUR THINGS IT DOES THAT A PLAIN MAE WOULD NOT, each because a plain MAE
can hide the exact failure this feature is about:

1. **REFUSALS ARE COUNTED BESIDE ACCURACY.** The predictor deliberately
   declines ampholytes, salts and mixtures. Dropping those rows silently
   would make the model look better the more it refuses -- accuracy over a
   denominator you chose is not accuracy.

2. **STRATIFIED BY IONIZATION CLASS.** An aggregate over mostly-neutral
   molecules hides whatever the acid/base handling does, and the pH
   machinery is the whole point of the feature.

3. **BASELINE AND pH-ADJUSTED ARE SEPARATE.** They validate different
   layers. Merging them means an error cannot be attributed to the
   baseline model, the pKa, or the ionization equation.

4. **THE ANTI-LEAK RULE.** A model may not headline against the data it
   was trained on. AqSolDB is the sidecar's own training set; reporting
   its score there as skill is the nmrshiftdb2 circularity again.

`solid_form` is an ACCEPTANCE rule rather than a note: intrinsic
solubility depends on the solid phase, so salts, hydrates and polymorphs
are reported separately and `unknown` never contributes to the headline.
AqSolDB does not record solid form at all, which is itself a finding and
is printed as one.
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from rdkit import Chem, RDLogger

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from openchem.chem.pka_providers import PKaResolution, PKaStatus  # noqa: E402
from openchem.chem.solubility import (  # noqa: E402
    AQSOLDB,
    IonizationClass,
    ModelStatus,
    classify_ionization,
    esol_logs,
    model_logs0,
)


def _admet_interpreter() -> str:
    """The configured ADMET interpreter, read the way the app reads it.

    A benchmark that probes with `None` reports "not installed" on a
    machine where it plainly is -- that exact mistake was made once while
    planning this feature and inverted the conclusion.
    """
    import os

    return os.environ.get("OPENCHEM_ADMET_PYTHON", "")

RDLogger.DisableLog("rdApp.*")

DATA = Path(__file__).resolve().parent / "data"
#: Which models were trained on which evaluation source. The rule is
#: enforced from the manifest rather than from memory.
TRAINED_ON = {AQSOLDB: {"Solubility_AqSolDB"}}


@dataclass
class Row:
    smiles: str
    measured: float
    ionization: IonizationClass


def load(manifest: dict) -> tuple[list[Row], Counter]:
    """Every test row, classified. Rows the predictor refuses are counted
    rather than dropped."""
    path = DATA / f"{manifest['evaluation_source']}__test.csv"
    if not path.is_file():
        raise SystemExit(f"No test split at {path}. Run fetch.py first (see its docstring).")

    rows: list[Row] = []
    refusals: Counter = Counter()
    with path.open(newline="", encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            smiles = record.get("Drug") or record.get("smiles") or ""
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                refusals["unparseable"] += 1
                continue
            try:
                measured = float(record.get("Y") or record.get("y"))
            except (TypeError, ValueError):
                refusals["no measured value"] += 1
                continue
            # The class is a structural question, so a resolution status of
            # FOUND is enough to let it answer; no sidecar is called here.
            verdict = classify_ionization(mol, PKaResolution(status=PKaStatus.FOUND, values=(7.0,)))
            if verdict is IonizationClass.UNSUPPORTED:
                refusals["salt or mixture"] += 1
                continue
            if verdict is IonizationClass.AMPHOLYTE:
                refusals["ampholyte"] += 1
                continue
            rows.append(Row(smiles=smiles, measured=measured, ionization=verdict))
    return rows, refusals


def errors(rows: list[Row], predict) -> list[float]:
    out = []
    for row in rows:
        mol = Chem.MolFromSmiles(row.smiles)
        value = predict(mol)
        if value is not None:
            out.append(value - row.measured)
    return out


def report(label: str, deltas: list[float]) -> None:
    if not deltas:
        print(f"  {label:26} n=0")
        return
    absolute = [abs(d) for d in deltas]
    rmse = (sum(d * d for d in deltas) / len(deltas)) ** 0.5
    print(
        f"  {label:26} n={len(deltas):<6} "
        f"MAE {statistics.fmean(absolute):5.2f}  RMSE {rmse:5.2f}  "
        f"median {statistics.median(absolute):5.2f}  max {max(absolute):5.2f}  "
        f"bias {statistics.fmean(deltas):+5.2f}"
    )


def shape_checks() -> None:
    """Directional behaviour, phrased as model-shape claims.

    A model can carry a respectable MAE and an absurd curve. These are
    claims about the independent-site HH model this app implements, NOT
    universal statements about chemistry.
    """
    from openchem.chem.solubility import logs_at_ph

    print("\nSHAPE (monotonic-HH model behaviour, not universal chemistry)")
    acid = [logs_at_ph(-4.0, ph, [4.5], [True]) for ph in (1.0, 4.5, 8.0)]
    base = [logs_at_ph(-4.0, ph, [9.0], [False]) for ph in (1.0, 6.0, 12.0)]
    flat = [logs_at_ph(-4.0, ph, [], []) for ph in (1.0, 7.0, 13.0)]
    print(f"  acid rises with pH      {acid[0]:+.2f} -> {acid[-1]:+.2f}   "
          f"{'ok' if acid == sorted(acid) else 'FAIL'}")
    print(f"  base falls with pH      {base[0]:+.2f} -> {base[-1]:+.2f}   "
          f"{'ok' if base == sorted(base, reverse=True) else 'FAIL'}")
    print(f"  neutral is flat         {flat[0]:+.2f} -> {flat[-1]:+.2f}   "
          f"{'ok' if len(set(flat)) == 1 else 'FAIL'}")


def main() -> int:
    manifest_path = DATA / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"No manifest at {manifest_path}. Run fetch.py first.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = manifest["evaluation_source"]

    rows, refusals = load(manifest)
    total = len(rows) + sum(refusals.values())

    print(f"SOURCE  {source}  ({manifest.get('source_version', 'unknown version')})")
    print(f"        target_type={manifest.get('target_type')}  "
          f"solid_form={manifest.get('solid_form')}  "
          f"pH={manifest.get('ph')}  T={manifest.get('temperature_c')}")
    if manifest.get("solid_form") == "unknown":
        print("        NOTE: solid form is not recorded, so no entry can enter a")
        print("              free-form-only headline. Every number below is over")
        print("              mixed and unknown solid forms.")

    print(f"\nCOVERAGE  {len(rows)} scored of {total} rows")
    for reason, count in refusals.most_common():
        print(f"  refused: {reason:24} {count}")
    print("  (ampholytes and salts are refused BY DESIGN; they are not failures,")
    print("   and they are shown here so accuracy is never read over a denominator")
    print("   the predictor chose for itself.)")

    print("\nESOL (Delaney 2004) - baseline logS0, no pKa involved")
    report("all", errors(rows, esol_logs))
    for klass in (IonizationClass.NEUTRAL, IonizationClass.ACID, IonizationClass.BASE):
        subset = [r for r in rows if r.ionization is klass]
        report(klass.name.lower(), errors(subset, esol_logs))

    leaky = source in TRAINED_ON.get(AQSOLDB, set())
    print(f"\nAqSolDB (trained model) - {'LEAKY on this source' if leaky else 'held out'}")
    if leaky:
        print("  NOT SCORED. This model was trained on this dataset, so any figure")
        print("  here measures memorisation rather than skill -- the same circularity")
        print("  recorded for nmrshiftdb2. Score it on an independent source or not")
        print("  at all; a leaked number quoted once outlives every caveat beside it.")
    else:
        interpreter = _admet_interpreter()
        probe = model_logs0(Chem.MolFromSmiles("CCO"), AQSOLDB, interpreter)
        if probe.status is not ModelStatus.AVAILABLE:
            # A silent n=0 reads as "the model scored nothing", which is a
            # statement about the model. This is a statement about the
            # machine, and the two must not look alike.
            print(f"  NOT RUN: {probe.reason}")
        else:
            report("all", errors(rows, lambda m: model_logs0(m, AQSOLDB, interpreter).logs0))

    shape_checks()

    print("\nThis is evidence disclosure. No model is selected as correct, and")
    print("nothing here licenses the word 'validated'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
