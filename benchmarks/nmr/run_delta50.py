"""Score every selection strategy on DELTA50, choosing on a split.

    uv run --no-sync python benchmarks/nmr/run_delta50.py "B3LYP def2-SVP"
    uv run --no-sync python benchmarks/nmr/run_delta50.py "B3LYP def2-SVP" bench-out/nmr

WHERE THE REPORTS GO, and why it is an argument rather than a constant.
With no second argument they land in `reports/` beside this file, which is
the deliberate hand-run that refreshes the committed tables. CI must NOT
do that, for two separate reasons:

  - `benchmarks-selfhosted.yml` uploads `bench-out/` and nothing else, so
    reports written here are never published at all; and
  - the `lookup` rows come from `nmr_database.predict_spectrum`, which
    reads a MACHINE-LOCAL index that grows -- nmrshiftdb2 gained roughly
    4% in three days (see README.md). On this machine today the run
    reproduces the committed reports byte for byte and leaves the tree
    clean; on a runner whose index differs it silently rewrites 24
    TRACKED files.

WHY A SPLIT. Forty-seven molecules is few enough to tune to by accident,
and one of the candidate rules was written after looking at an atom it
fixes. Strategies are compared on a development subset and the leader is
then confirmed on molecules it never influenced. A rule that leads on
development and not on held-out has been fitted to noise.

Needs no ORCA -- it reads the committed shieldings.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import delta50  # noqa: E402
import plots  # noqa: E402
import score_hybrid as sh  # noqa: E402
from hybrid_strategies import BASELINES, STRATEGIES, MoleculeInput  # noqa: E402
from rdkit import Chem  # noqa: E402
from run_shieldings import SHIELDINGS, slug  # noqa: E402

from openchem.chem import nmr_database  # noqa: E402

#: A mapping is only used when the two calculations agree this closely on
#: the shieldings being matched, in ppm. Beyond it the correspondence is
#: not established and the compound is dropped rather than guessed at.
MAX_SHIELDING_GAP = 8.0


def build(method: str):
    store = json.loads((SHIELDINGS / f"{slug(method)}.json").read_text(encoding="utf-8"))
    factors = sh.calibrate(store, "C")
    inputs, dropped = [], []
    for compound in delta50.load():
        entry = store.get(f"d50_{compound.name}")
        if not entry or entry.get("failed"):
            dropped.append((compound.name, "no shieldings"))
            continue
        raw = {int(i): v for i, v in entry["shieldings"].items() if entry["elements"][i] == "C"}
        mapping = delta50.map_to_atoms(compound, raw)
        if mapping is None:
            dropped.append((compound.name, "no atom correspondence"))
            continue
        if mapping.worst_shielding_gap > MAX_SHIELDING_GAP:
            dropped.append(
                (compound.name, f"shielding gap {mapping.worst_shielding_gap:.1f} ppm")
            )
            continue

        mol = Chem.AddHs(Chem.MolFromSmiles(compound.smiles))
        result = nmr_database.predict_spectrum(mol, compound.name, element="C")
        per_atom = (result.provenance.parameters or {}).get("per_atom", {})
        data = MoleculeInput(
            name=compound.name,
            lookup=dict(result.values),
            orca={i: factors.apply(v) for i, v in raw.items()},
            quality={int(i): d["quality"] for i, d in per_atom.items()},
            global_error=factors.residual_rms,
        )
        inputs.append((data, mapping.shifts, mapping))
    return factors, inputs, dropped


def split(inputs, fraction: float = 0.3, seed: int = 11):
    names = sorted(d.name for d, _t, _m in inputs)
    rng = random.Random(seed)
    rng.shuffle(names)
    held = set(names[: max(1, round(len(names) * fraction))])
    dev = [(d, t) for d, t, _m in inputs if d.name not in held]
    test = [(d, t) for d, t, _m in inputs if d.name in held]
    return dev, test, sorted(held)


def band_reality_check(inputs) -> str:
    """What the lookup's bands are actually worth ON THIS CORPUS.

    The expected errors every strategy selects on were measured on a
    held-out nmrshiftdb2 split. DELTA50 is a different corpus, and if the
    bands do not transfer then every rule is selecting on the wrong number.
    """
    from openchem.chem.nmr_database import HELD_OUT_BAND_MAE

    buckets: dict[str, list[float]] = {}
    for data, truth in inputs:
        for index, (_label, experimental) in truth.items():
            if index in data.lookup:
                buckets.setdefault(data.quality.get(index, "uncovered"), []).append(
                    abs(data.lookup[index] - experimental)
                )
    lines = ["```", f"{'band':<10} {'n':>4} {'observed MAE':>13} {'expected':>9}"]
    for band in ("good", "medium", "rough"):
        errs = buckets.get(band, [])
        if not errs:
            continue
        lines.append(
            f"{band:<10} {len(errs):>4} {sum(errs)/len(errs):>13.2f} "
            f"{HELD_OUT_BAND_MAE[band]:>9.2f}"
        )
    lines.append("```")
    return "\n".join(lines)


def main() -> None:
    method = sys.argv[1] if len(sys.argv) > 1 else "B3LYP def2-SVP"
    factors, inputs, dropped = build(method)
    print(f"{method}: slope {factors.slope:.4f}  R^2 {factors.r_squared:.5f}  "
          f"residual RMS {factors.residual_rms:.3f} ppm")
    print(f"{len(inputs)} compounds usable, {len(dropped)} dropped")
    for name, why in dropped:
        print(f"   dropped {name}: {why}")

    worst = max((m.worst_shielding_gap for _d, _t, m in inputs), default=0)
    closest = min((m.closest_pair for _d, _t, m in inputs), default=0)
    print(f"mapping: worst shielding gap {worst:.2f} ppm, closest adjacent pair {closest:.2f} ppm\n")

    dev, test, held = split(inputs)
    everything = [(d, t) for d, t, _m in inputs]
    print(f"development {len(dev)} molecules, held-out {len(test)}: {', '.join(held)}\n")
    print("Lookup band errors on THIS corpus vs what the strategies assume:")
    print(band_reality_check(everything), "\n")

    out = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "reports"
    out.mkdir(parents=True, exist_ok=True)
    sections = []
    for label, subset in (("development", dev), ("held-out", test), ("all", everything)):
        evaluations = [
            sh.evaluate(name, fn, subset) for name, fn in {**BASELINES, **STRATEGIES}.items()
        ]
        text = sh.report(evaluations, f"DELTA50 {label} - {method}")
        sections.append(text)
        print(text)
        if label == "all":
            for ev in evaluations:
                (out / f"delta50_{slug(method)}_{ev.name}_decisions.csv").write_text(
                    sh.decision_matrix(ev), encoding="utf-8"
                )
            _write_plots(out, method, evaluations)

    (out / f"delta50_{slug(method)}_report.md").write_text(
        "\n\n".join(
            [f"# DELTA50 — {method}", "", "## Lookup bands on this corpus",
             band_reality_check(everything), f"\nHeld-out molecules: {', '.join(held)}", *sections]
        ),
        encoding="utf-8",
    )
    print(f"reports -> {out}")


def _write_plots(out: Path, method: str, evaluations) -> None:
    by_name = {ev.name: ev for ev in evaluations}
    best = by_name.get("disagreement_defers") or evaluations[-1]
    lookup, orca = by_name["lookup_only"], by_name["orca_only"]
    scatter = plots.scatter(
        [
            plots.Series("lookup", "#c44", [(r.truth, r.chosen_value) for r in lookup.records]),
            plots.Series("ORCA", "#48a", [(r.truth, r.chosen_value) for r in orca.records]),
            plots.Series(best.name, "#2a2", [(r.truth, r.chosen_value) for r in best.records]),
        ],
        f"DELTA50 13C: predicted vs experimental ({method})",
        "experimental (ppm)", "predicted (ppm)",
    )
    (out / f"delta50_{slug(method)}_scatter.svg").write_text(scatter, encoding="utf-8")
    histogram = plots.histogram(
        [
            ("lookup", "#c44", [r.error for r in lookup.records]),
            ("ORCA", "#48a", [r.error for r in orca.records]),
            (best.name, "#2a2", [r.error for r in best.records]),
        ],
        f"DELTA50 13C error distribution ({method})",
    )
    (out / f"delta50_{slug(method)}_errors.svg").write_text(histogram, encoding="utf-8")


if __name__ == "__main__":
    main()
