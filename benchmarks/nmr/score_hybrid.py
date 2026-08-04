"""Compare selection strategies against assigned experimental shifts.

WHAT THIS MEASURES THAT MAE DOES NOT. For every benchmark atom we know the
lookup value, the ORCA value AND the truth -- so after the fact we know
whether the rule chose the source that was actually closer. That gives two
metrics about the DECISION, independent of how good either predictor is:

    selection accuracy   how often the chosen source was the better one
    regret               how much worse the choice was, in ppm

A rule can lower MAE purely because the calculation is good while still
choosing badly; regret catches that and MAE cannot. Worst regret is also
the direct measure of "how bad is the worst atom this makes wrong", which
is the thing to minimise.

Error is reported as MAE, median, RMSE, p95 and worst, because an average
hides the failures that matter most to someone reading a single peak.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "src"))

import bootstrap as bs  # noqa: E402
from hybrid_strategies import BASELINES, STRATEGIES, AtomChoice, MoleculeInput  # noqa: E402
from rdkit import Chem  # noqa: E402

from openchem.chem import nmr_database  # noqa: E402
from openchem.chem.nmr_scaling import (  # noqa: E402
    REFERENCE_COMPOUNDS,
    fit_scaling,
    reference_points,
)

BANDS = ("good", "medium", "rough")


@dataclass
class AtomRecord:
    """One row of the decision matrix -- what every metric is derived from."""

    molecule: str
    atom: int
    label: str
    quality: str
    truth: float
    lookup: float | None
    orca: float | None
    chosen_source: str
    chosen_value: float
    expected_error: float | None
    flagged: bool

    @property
    def error(self) -> float:
        return abs(self.chosen_value - self.truth)

    @property
    def best_possible(self) -> float:
        """The error of whichever source was actually closer."""
        options = [abs(v - self.truth) for v in (self.lookup, self.orca) if v is not None]
        return min(options)

    @property
    def regret(self) -> float:
        """How much the choice cost against the better available source."""
        return self.error - self.best_possible

    @property
    def decidable(self) -> bool:
        """Only atoms where BOTH sources offered a value test the decision;
        where only one existed there was nothing to get wrong."""
        return self.lookup is not None and self.orca is not None

    @property
    def chose_better(self) -> bool:
        return self.regret <= 1e-9


@dataclass
class StrategyEvaluation:
    name: str
    records: list[AtomRecord] = field(default_factory=list)
    #: Molecules the strategy declined entirely.
    refused: list[str] = field(default_factory=list)

    def metrics(self, band: str | None = None) -> dict:
        rows = [r for r in self.records if band is None or r.quality == band]
        if not rows:
            return {"n": 0}
        errors = np.array([r.error for r in rows])
        decidable = [r for r in rows if r.decidable]
        regrets = np.array([r.regret for r in decidable]) if decidable else np.array([0.0])
        low, high = bs.resample(self._grouped(rows, lambda r: r.error), bs.mean, seed=7)
        return {
            "n": len(rows),
            "molecules": len({r.molecule for r in rows}),
            "mae": float(errors.mean()),
            "mae_ci": (low, high),
            "median": float(np.median(errors)),
            "rmse": float(np.sqrt((errors**2).mean())),
            "p95": float(np.percentile(errors, 95)),
            "worst": float(errors.max()),
            "selection_accuracy": (
                sum(r.chose_better for r in decidable) / len(decidable) if decidable else float("nan")
            ),
            "decidable": len(decidable),
            "mean_regret": float(regrets.mean()),
            "p95_regret": float(np.percentile(regrets, 95)),
            "worst_regret": float(regrets.max()),
            "flagged": sum(r.flagged for r in rows),
            "refused_molecules": len(self.refused),
        }

    @staticmethod
    def _grouped(rows, value) -> list[list[float]]:
        groups: dict[str, list[float]] = {}
        for record in rows:
            groups.setdefault(record.molecule, []).append(value(record))
        return list(groups.values())


def calibrate(store: dict, element: str = "C"):
    """Fit the scaling line from the reference compounds in `store`."""
    per_compound: dict[str, list[float]] = {}
    for compound in REFERENCE_COMPOUNDS:
        entry = store.get(compound.name.replace(" ", "_"))
        if not entry or entry.get("failed"):
            continue
        per_compound[compound.name] = [
            value
            for index, value in entry["shieldings"].items()
            if entry["elements"][index] == element
        ]
    return fit_scaling(reference_points(per_compound, element))


def build_input(name: str, spectrum, store: dict, factors, global_error: float):
    """Assemble one molecule's two candidate spectra plus its truth."""
    entry = store.get(name)
    if not entry or entry.get("failed"):
        return None, None
    mol = Chem.MolFromMolBlock(
        (HERE / "geometries" / f"{name}.mol").read_text(encoding="utf-8"), removeHs=False
    )
    if mol is None:
        return None, None

    orca = {
        int(i): factors.apply(v)
        for i, v in entry["shieldings"].items()
        if entry["elements"][i] == "C"
    }
    result = nmr_database.predict_spectrum(mol, name, element="C")
    per_atom = (result.provenance.parameters or {}).get("per_atom", {})
    quality = {int(i): d["quality"] for i, d in per_atom.items()}
    data = MoleculeInput(
        name=name,
        lookup=dict(result.values),
        orca=orca,
        quality=quality,
        global_error=global_error,
    )
    truth = {i: (label, ppm) for i, (label, ppm) in spectrum.shifts.items()}
    return data, truth


def evaluate(name: str, strategy, inputs: list[tuple[MoleculeInput, dict]]) -> StrategyEvaluation:
    evaluation = StrategyEvaluation(name=name)
    for data, truth in inputs:
        choices = strategy(data)
        if choices is None:  # refused the whole spectrum
            evaluation.refused.append(data.name)
            choices = {i: AtomChoice("lookup", v, None) for i, v in data.lookup.items()}
        for index, (label, experimental) in truth.items():
            choice = choices.get(index)
            if choice is None:
                continue
            evaluation.records.append(
                AtomRecord(
                    molecule=data.name,
                    atom=index,
                    label=label,
                    quality=data.quality.get(index, "uncovered"),
                    truth=experimental,
                    lookup=data.lookup.get(index),
                    orca=data.orca.get(index),
                    chosen_source=choice.source,
                    chosen_value=choice.value,
                    expected_error=choice.expected_error,
                    flagged=choice.flagged,
                )
            )
    return evaluation


def report(evaluations: list[StrategyEvaluation], title: str) -> str:
    lines = [f"## {title}", ""]
    header = (
        f"{'strategy':<20} {'n':>4} {'MAE':>6} {'95% CI':>16} {'med':>6} {'RMSE':>6} "
        f"{'p95':>6} {'worst':>7} {'sel.acc':>8} {'regret':>7} {'worst reg':>10} {'ref':>4}"
    )
    lines += ["```", header, "-" * len(header)]
    for ev in evaluations:
        m = ev.metrics()
        if not m["n"]:
            continue
        low, high = m["mae_ci"]
        lines.append(
            f"{ev.name:<20} {m['n']:>4} {m['mae']:>6.2f} "
            f"[{low:>5.2f}, {high:>5.2f}]  {m['median']:>6.2f} {m['rmse']:>6.2f} "
            f"{m['p95']:>6.2f} {m['worst']:>7.2f} {m['selection_accuracy']:>7.1%} "
            f"{m['mean_regret']:>7.2f} {m['worst_regret']:>10.2f} {m['refused_molecules']:>4}"
        )
    lines.append("```")
    lines.append("")
    for band in BANDS:
        lines += [f"### {band} atoms", "```",
                  f"{'strategy':<20} {'n':>4} {'MAE':>6} {'worst':>7} {'sel.acc':>8} {'worst reg':>10}"]
        for ev in evaluations:
            m = ev.metrics(band)
            if not m["n"]:
                continue
            lines.append(
                f"{ev.name:<20} {m['n']:>4} {m['mae']:>6.2f} {m['worst']:>7.2f} "
                f"{m['selection_accuracy']:>7.1%} {m['worst_regret']:>10.2f}"
            )
        lines += ["```", ""]
    return "\n".join(lines)


def paired(challenger: StrategyEvaluation, baseline: StrategyEvaluation) -> str:
    """Compare two strategies atom by atom, which is far more sensitive
    than comparing their separate intervals.

    Both rules answered the SAME atoms, so most of the spread in either
    one's MAE is the molecules, not the rule. Differencing per atom
    removes that shared variation -- two strategies whose own intervals
    overlap almost entirely can still differ with certainty.
    """
    theirs = {(r.molecule, r.atom): r.error for r in baseline.records}
    groups: dict[str, list[float]] = {}
    for record in challenger.records:
        key = (record.molecule, record.atom)
        if key in theirs:
            groups.setdefault(record.molecule, []).append(record.error - theirs[key])
    if not groups:
        return f"{challenger.name} vs {baseline.name}: nothing comparable"
    deltas = [d for row in groups.values() for d in row]
    low, high = bs.resample(list(groups.values()), bs.mean, seed=13)
    mean = sum(deltas) / len(deltas)
    return (
        f"{challenger.name:<20} vs {baseline.name:<20} "
        f"delta {mean:+6.3f} ppm  95% CI [{low:+.3f}, {high:+.3f}]  "
        f"{bs.paired_verdict(low, high)}"
    )


def decision_matrix(evaluation: StrategyEvaluation) -> str:
    rows = ["molecule,atom,label,quality,truth,lookup,orca,chosen,value,error,better,regret,flagged"]
    fmt = lambda v: "" if v is None else f"{v:.3f}"  # noqa: E731
    for r in sorted(evaluation.records, key=lambda r: (r.molecule, r.atom)):
        rows.append(
            f"{r.molecule},{r.atom},{r.label},{r.quality},{r.truth:.2f},{fmt(r.lookup)},"
            f"{fmt(r.orca)},{r.chosen_source},{r.chosen_value:.3f},{r.error:.3f},"
            f"{'yes' if r.chose_better else 'NO'},{r.regret:.3f},{'yes' if r.flagged else ''}"
        )
    return "\n".join(rows)
