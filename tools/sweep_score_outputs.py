"""The derived-score sweep: every typed number the registry produces on the census panel, with its unit.

**WHY IT EXISTS.** A derived score may name only an entry of the approved output table
(`docs/DERIVED_SCORES_DESIGN.md` section 3), and that table is built by SWEEPING and then
approving by hand: this lists what is there to approve, and `tests/test_score_outputs.py` uses
the same sweep to hold the approved entries to what the registry actually produces. A guard that
reads a different sweep from the one a person approved from would be a second opinion.

**WHAT COUNTS AS A CANDIDATE.** A number the producer typed as one: a `DescriptorValue` or a report
`Fact` whose value is an `int` or `float`, not a `bool` (a pass/fail flag is a verdict and not a
quantity), and finite. A text fact that happens to read as a number is NOT one -- the batch table's
`_as_float` would parse it, and a score must not rest on a string somebody formatted. A per-atom
dataset is not a candidate in this phase: reducing it by an aggregate would make the aggregate a
hidden parameter of the score.

**WHERE THE ID COMES FROM.** The batch column id, reused and not invented (`descriptor:<id>` or
`calculator:<calculator id>:<fact label>`), because saved tables and exports already depend on it.
A candidate whose id two facts of one report share is marked `ambiguous` and can never be approved.

Run it:

    python tools/sweep_score_outputs.py --report            # every candidate, grouped by calculator; approved ones marked
    python tools/sweep_score_outputs.py --report --json out.json
    python tools/sweep_score_outputs.py --check             # hold the approved table to what the registry produces; exit 1 on a problem

The sidecars (ADMET, pKa) are unconfigured and the NMR database absent, exactly as in the census,
so nothing that needs them can be approved: the panel could not show it resolving.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

#: The `source` of a candidate that came from the always-on descriptor set.
FROM_DESCRIPTOR = "descriptor"

#: The `source` of a candidate that came from a registered calculator's report.
FROM_CALCULATOR = "calculator"

#: The fewest census rows an approved output must be a finite number on. One row is an accident of the panel, not a property of the output.
MIN_ROWS = 5

#: The support stages (`CalculatorSupport.stage` values) whose outputs may be approved. An experimental calculator is not one.
APPROVABLE_STAGES = frozenset({"stable", "limited"})


@dataclass
class Candidate:
    """One output id, and everything the panel showed of it."""

    output_id: str
    label: str
    source: str
    #: The descriptor id, or the registered calculator's id.
    source_id: str
    #: `(row id, calculation input, value, units string as carried)` for every run where it came back as a finite
    #: number. The input is part of it because the always-on descriptors used to run on the drawing AND on a geometry,
    #: as two stored results with one id (the design's second finding). Since 2026-10-14 only the ten shape descriptors
    #: are stored under a geometry; an approved output is still read from the drawing (`READ_FROM`).
    observations: list[tuple[str, str, float, str]] = field(default_factory=list)
    #: True when two facts of one report carry this id, so it names no single number.
    ambiguous: bool = False

    @property
    def carried(self) -> list[str]:
        """The distinct units strings it was carried with, in order of first appearance."""
        seen: list[str] = []
        for _row, _input, _value, units in self.observations:
            if units not in seen:
                seen.append(units)
        return seen


def _typed_number(value: Any) -> float | None:
    """`value` when the producer typed it as a finite number; never a bool, never a string."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def scalars_of(column: str, stored: list) -> list[tuple[str, str, str, str, float | None, str, str]]:
    """`(output id, label, source, source id, value, units, calculation input)` for every number-shaped output of one run.

    `value` is None for a fact that is not a finite typed number, so the caller can still see that the
    id exists and was not numeric on this row.
    """
    from openchem.domain.common import CacheState
    from openchem.domain.descriptor import DescriptorValue
    from openchem.domain.report import ReportResult

    out: list[tuple[str, str, str, str, float | None, str, str]] = []
    for item in stored:
        result = item.result
        calculation_input = item.identity.calculation_input
        if getattr(result, "cache_state", None) is CacheState.FAILED:
            continue
        if isinstance(result, DescriptorValue):
            out.append((
                f"descriptor:{result.descriptor_id}", result.name, FROM_DESCRIPTOR, result.descriptor_id,
                _typed_number(result.value), result.units, calculation_input,
            ))
        elif isinstance(result, ReportResult):
            for fact in result.facts:
                out.append((
                    f"calculator:{column}:{fact.label}", fact.label, FROM_CALCULATOR, column,
                    _typed_number(fact.value), fact.units, calculation_input,
                ))
    return out


class Sweep:
    """The census observer: collects every output id the panel produced, across all rows."""

    def __init__(self) -> None:
        self.candidates: dict[str, Candidate] = {}

    def __call__(self, column: str, row, stored: list) -> None:
        seen_this_run: dict[str, int] = {}
        for output_id, label, source, source_id, value, units, calculation_input in scalars_of(column, stored):
            seen_this_run[output_id] = seen_this_run.get(output_id, 0) + 1
            candidate = self.candidates.setdefault(output_id, Candidate(output_id, label, source, source_id))
            if seen_this_run[output_id] > 1:
                candidate.ambiguous = True
            if value is not None:
                candidate.observations.append((row.id, calculation_input, value, units))

    def numeric(self) -> list[Candidate]:
        """The candidates that were a finite number on at least one row, in id order."""
        return sorted((c for c in self.candidates.values() if c.observations), key=lambda c: c.output_id)


def run_sweep(qapp, rows=None, *, calculator_ids: list[str] | None = None) -> tuple[Sweep, dict[str, Any]]:
    """The census over `rows` (the whole panel by default), observed.

    Returns the sweep and the census itself, whose `support` map says each calculator's stage and visibility.
    """
    import calculator_census as census_tool

    sweep = Sweep()
    census = census_tool.run_census(
        qapp, rows if rows is not None else census_tool.load_corpus(), calculator_ids=calculator_ids, observer=sweep
    )
    return sweep, census


def entry_problems(entry, sweep: Sweep, census: dict[str, Any]) -> list[str]:
    """Everything wrong with one approved entry, measured against what the registry produced on the panel. Empty when it holds.

    Every message ends by saying what a failure here costs, because the person who sees it renamed a fact label and did not know a score
    read it.
    """
    from openchem.domain.score_outputs import READ_FROM

    cost = f" -- this breaks every score that uses {entry.output_id}"
    candidate = sweep.candidates.get(entry.output_id)
    if candidate is None:
        return [f"{entry.output_id} was produced by no run on the census panel (renamed, removed, or its calculator no longer runs there){cost}"]
    problems: list[str] = []
    if candidate.ambiguous:
        problems.append("two facts of one report carry this id, so it names no single number" + cost)
    if candidate.source == FROM_CALCULATOR:
        support = census["support"].get(candidate.source_id)
        if support is None:
            problems.append(f"{candidate.source_id} is not a registry calculator" + cost)
        else:
            if support["stage"] not in APPROVABLE_STAGES:
                problems.append(f"{candidate.source_id} is {support['stage']}; only {sorted(APPROVABLE_STAGES)} outputs may be approved" + cost)
            if support["visibility"] != "shown":
                problems.append(f"{candidate.source_id} is {support['visibility']} by default; only an output offered by default may be approved" + cost)
    seen = [(row, units) for row, calc_input, _value, units in candidate.observations if calc_input == READ_FROM]
    rows = {row for row, _units in seen}
    if not seen:
        problems.append(f"it was never a finite typed number on the {READ_FROM} input" + cost)
    elif len(rows) < MIN_ROWS:
        problems.append(f"it was a finite number on {len(rows)} census rows; at least {MIN_ROWS} are needed" + cost)
    wrong = sorted({units for _row, units in seen if units != entry.carried_as})
    if wrong:
        problems.append(f"it carries the units {wrong!r}, not the declared {entry.carried_as!r}" + cost)
    return problems


def identical_pairs(entries, sweep: Sweep) -> list[tuple[Any, Any]]:
    """Pairs of approved outputs with DIFFERENT endpoints that gave the same value on every census row they share.

    An endpoint tag is a person's judgement that two outputs estimate one quantity, and a judgement is forgotten. Two outputs that agree to
    the last digit on at least `MIN_ROWS` rows are one number under two names (the ESOL descriptor and the solubility calculator's log
    mol/L did, on 16 of 16 rows), so they must share a tag or the consensus rule would let a formula combine a number with itself. This
    catches a copy, not two methods that merely estimate the same thing: those differ in value, and only a person can tag them.
    """
    from openchem.domain.score_outputs import READ_FROM

    values: dict[str, dict[str, float]] = {}
    for entry in entries:
        candidate = sweep.candidates.get(entry.output_id)
        if candidate is not None:
            values[entry.output_id] = {row: value for row, calc_input, value, _units in candidate.observations if calc_input == READ_FROM}
    found = []
    for i, first in enumerate(entries):
        for second in entries[i + 1:]:
            if first.endpoint == second.endpoint:
                continue
            a, b = values.get(first.output_id, {}), values.get(second.output_id, {})
            shared = sorted(set(a) & set(b))
            if len(shared) >= MIN_ROWS and all(math.isclose(a[row], b[row], rel_tol=1e-9, abs_tol=1e-12) for row in shared):
                found.append((first, second))
    return found


def _report(sweep: Sweep, census: dict[str, Any], json_path: str | None) -> None:
    rows = len(census["rows"])
    by_source: dict[str, list[Candidate]] = {}
    for candidate in sweep.numeric():
        by_source.setdefault(candidate.source_id, []).append(candidate)
    for source_id, candidates in sorted(by_source.items()):
        support = census["support"].get(source_id)
        tag = f" [{support['stage']}, {support['visibility']}]" if support else " [always on]"
        print(f"\n{source_id}{tag}")
        for candidate in candidates:
            flags = " AMBIGUOUS" if candidate.ambiguous else ""
            values = [v for _r, _i, v, _u in candidate.observations]
            inputs = sorted({i for _r, i, _v, _u in candidate.observations})
            print(
                f"  {candidate.output_id}  units={candidate.carried!r}  input={'+'.join(inputs)}  "
                f"rows={len({r for r, _i, _v, _u in candidate.observations})}/{rows}  "
                f"range=[{min(values):.4g}, {max(values):.4g}]{flags}"
            )
    if json_path:
        payload = [
            {
                "output_id": c.output_id, "label": c.label, "source": c.source, "source_id": c.source_id,
                "carried": c.carried, "inputs": sorted({i for _r, i, _v, _u in c.observations}),
                "rows": len({r for r, _i, _v, _u in c.observations}), "ambiguous": c.ambiguous,
                "support": census["support"].get(c.source_id),
                "min": min(v for _r, _i, v, _u in c.observations), "max": max(v for _r, _i, v, _u in c.observations),
            }
            for c in sweep.numeric()
        ]
        Path(json_path).write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        print(f"\nwrote {json_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--report", action="store_true", help="print every candidate")
    mode.add_argument("--check", action="store_true", help="hold the approved table to the registry; exit 1 on a problem")
    parser.add_argument("--json", help="with --report, also write the candidates to this file")
    args = parser.parse_args(argv)

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    # A unit like "A^2" is ASCII, but "Ų" and a subscript two are not, and a Windows console is not UTF-8.
    sys.stdout.reconfigure(encoding="utf-8")
    import calculator_census as census_tool

    census_tool._isolated_environment()
    from PySide6.QtWidgets import QApplication

    qapp = QApplication.instance() or QApplication([])
    sweep, census = run_sweep(qapp)
    if args.report:
        _report(sweep, census, args.json)
        return 0
    from openchem.domain.score_outputs import APPROVED

    found = {entry.output_id: entry_problems(entry, sweep, census) for entry in APPROVED}
    for output_id, problems in found.items():
        for problem in problems:
            print(f"{output_id}: {problem}")
    bad = sum(1 for problems in found.values() if problems)
    copies = identical_pairs(APPROVED, sweep)
    for first, second in copies:
        print(f"{first.output_id} and {second.output_id} agree on every shared row but carry different endpoints ({first.endpoint}, {second.endpoint})")
    print(f"{len(found) - bad} of {len(found)} approved outputs hold; {len(copies)} untagged copies")
    return 1 if bad or copies else 0


if __name__ == "__main__":
    raise SystemExit(main())
