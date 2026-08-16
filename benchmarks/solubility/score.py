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

4. **THE ANTI-LEAK RULE, WHICH CAUGHT BOTH MODELS.** A model may not
   headline against data it was fitted on. That was obvious for the
   AqSolDB sidecar and NOT obvious for ESOL: the merged AqSolDB contains
   Delaney's own ESOL set as one of its nine sources, so the first
   version of this benchmark would have scored ESOL against its own fit.
   `fetch.py` subtracts those compounds by InChIKey -- 14 of 94 -- and the
   remaining 80 are a genuine held-out set.

`solid_form` is an ACCEPTANCE rule rather than a note: intrinsic
solubility depends on the solid phase, so salts, hydrates and polymorphs
would be reported separately and `unknown` never contributes to a
free-form headline. The source records none, which is itself a finding
and is printed as one.

MEASURED, 2026-08-16, ESOL against the de-leaked Solubility Challenge:

    all      n=67  MAE 0.74  RMSE 0.98  median 0.52  max 2.65  bias -0.20
    neutral  n=16  MAE 0.80                                    bias +0.02
    acid     n=22  MAE 0.61                                    bias +0.06
    base     n=29  MAE 0.81                                    bias -0.52

**THE STRATIFICATION EARNED ITS KEEP ON THE FIRST RUN.** The aggregate
bias is -0.20 and looks like noise; split by class, ESOL under-predicts
BASES by half a log unit while acids sit at +0.06. An aggregate MAE would
have hidden a systematic error in one third of a druglike set.

13 of 80 compounds -- 16% -- are ampholytes and are refused. That is a
large fraction of druglike chemistry to decline, and it is printed beside
the accuracy so the two are never read apart.
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
#: Which models were fitted on which evaluation sources. The rule is
#: enforced from the MANIFEST at run time rather than from this table, so
#: a new source cannot bypass it by not being listed here.
TRAINED_ON = {AQSOLDB: {"aqsoldb"}}


@dataclass
class Row:
    smiles: str
    measured: float
    ionization: IonizationClass


def load(manifest: dict) -> tuple[list[Row], Counter]:
    """Every test row, classified. Rows the predictor refuses are counted
    rather than dropped."""
    path = DATA / "evaluation.csv"
    if not path.is_file():
        raise SystemExit(f"No evaluation set at {path}. Run fetch.py first (see its docstring).")

    rows: list[Row] = []
    refusals: Counter = Counter()
    with path.open(newline="", encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            smiles = record.get("smiles") or ""
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                refusals["unparseable"] += 1
                continue
            try:
                measured = float(record.get("measured_logs"))
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


def score_sc2() -> None:
    """The Solubility Challenge 2 tight set, when it has been extracted.

    Two things this set has that the other does not, and both change how
    a number should be read:

      * a NOISE FLOOR. Interlab SD averages 0.17 log unit, and CheqSol
        against high-quality shake-flask is RMSE 0.34. Nothing can score
        below that, so a model at 0.9 is not "0.9 away from perfect".
      * a PUBLISHED BASELINE. The paper reports the General Solubility
        Equation at RMSE 1.1 on these same compounds. Reproducing that
        from the table's own GSE column is what makes our figure
        comparable rather than merely reported -- and the GSE needs a
        melting point, which we do not have and it does.

    De-leaked exactly like the other set: any compound whose InChIKey
    appears in Delaney's fitting set is dropped, because ESOL cannot be
    scored on its own training data.
    """
    manifest_path = DATA / "sc2_manifest.json"
    corpus = DATA / "sc2_tight.csv"
    if not (manifest_path.is_file() and corpus.is_file()):
        print()
        print("SC-2 TIGHT SET  not extracted (see extract_sc2.py; it needs the paper)")
        return

    from rdkit.Chem import inchi

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    trained_keys = _delaney_inchikeys()

    rows, refused, leaked = [], Counter(), 0
    with corpus.open(newline="", encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            mol = Chem.MolFromSmiles(record["smiles"])
            if mol is None:
                refused["unparseable"] += 1
                continue
            if trained_keys and inchi.MolToInchiKey(mol) in trained_keys:
                leaked += 1
                continue
            verdict = classify_ionization(mol, PKaResolution(status=PKaStatus.FOUND, values=(7.0,)))
            if verdict is IonizationClass.UNSUPPORTED:
                refused["salt or mixture"] += 1
                continue
            if verdict is IonizationClass.AMPHOLYTE:
                refused["ampholyte"] += 1
                continue
            rows.append((Row(smiles=record["smiles"], measured=float(record["measured_logs"]),
                             ionization=verdict), float(record["gse_logs"]), float(record["sd"])))

    print()
    print(f"SC-2 TIGHT SET  {manifest['evaluation_source']}")
    print(f"  {len(rows)} scored, {leaked} dropped as ESOL training data, "
          f"{sum(refused.values())} refused {dict(refused)}")
    print(f"  NOISE FLOOR: interlab SD {manifest['interlab_sd_log']} log; nothing here can")
    print("               score below it, and a gap smaller than it is not a gap.")

    report("ESOL", errors([r for r, _, _ in rows], esol_logs))
    for klass in (IonizationClass.NEUTRAL, IonizationClass.ACID, IonizationClass.BASE):
        subset = [r for r, _, _ in rows if r.ionization is klass]
        report(f"  ESOL, {klass.name.lower()}", errors(subset, esol_logs))
    report("GSE (published baseline)", [g - r.measured for r, g, _ in rows])
    print(f"  the paper reports GSE at RMSE {manifest['published_baseline']['rmse']} on all 100;")
    print("  ours is over the de-leaked subset, so the two are not the same number.")
    print("  The GSE needs a measured melting point. This app does not have one, and")
    print("  ESOL lands within a tenth of a log unit of it anyway -- which is the")
    print("  comparison that says whether our figure is poor or the endpoint is hard.")


def _delaney_inchikeys() -> set[str]:
    """ESOL's own fitting set, for de-leaking. Empty if it was not fetched."""
    path = DATA / "esol_training_inchikeys.json"
    if path.is_file():
        return set(json.loads(path.read_text(encoding="utf-8")))
    return set()


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

    leaky = "aqsoldb" in set(manifest.get("models_trained_on_this", []))
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
    score_sc2()

    print("\nThis is evidence disclosure. No model is selected as correct, and")
    print("nothing here licenses the word 'validated'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
