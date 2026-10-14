"""The arithmetic of the Lewis pairing gate, and nothing else (`benchmarks/lewis_gate/PREREGISTRATION.md`).

The gate asks one question (`docs/RECIPES_DESIGN.md` section 10): does the recipe, fed only by stored runs at one method on
real ORCA, reproduce the documented numbers for BH3 and BF3 with carbon monoxide, with the two orbital lines left
disagreeing as they are? Everything that decides the answer is here and is pure, so that it can be tested with invented
numbers and so that nobody, including its author, can choose a tolerance or a pass condition after seeing a measurement:

* what the documented numbers are (`DOCUMENTED`), copied from the tests that carry them and not recomputed;
* how the noise floor is made of two repeats of carbon monoxide, and how a tolerance follows from it by a rule
  (`tolerance_from_floor`) that was written before any floor existed;
* what PASS, FAIL and NOT EVALUABLE each mean (`judge`), every reason collected and none short-circuited, so a run that
  fails two ways says both.

The drive steps in `app/debug_drive.py` read the stored runs and call these. Nothing here starts a job.
"""

from __future__ import annotations

import enum
import math
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any

from openchem.domain.recipe_run import BindingState

#: The ORCA the documented numbers were produced with (comments in `tests/test_lewis_adduct.py`). A run on another version
#: is a recorded difference and never a pass: orbital tables and SCF defaults move between versions.
ORCA_VERSION = "6.1.1"

#: The one method and basis of the gate, from the preset list the Quantum Chemistry panel offers.
METHOD_BASIS = "B3LYP def2-SVP"

#: The smallest tolerance. The documented values carry two decimals, so a difference derived from two of them is good to
#: about 0.01 eV whatever the recipe does.
TOLERANCE_FLOOR_EV = 0.01

#: The largest tolerance, from the smallest margin the claims rest on: the hardness differences order the two pairs by
#: 1.63 against 0.89, which is 0.74 eV apart, and a tolerance of half that or more could let the two orderings swap.
#: A floor that would need more than this makes the gate not evaluable; it never widens the tolerance.
TOLERANCE_CEILING_EV = 0.37

#: A float's own rounding is not a miss. `abs(difference) <= tolerance + _SLACK` is "within the tolerance".
_SLACK = 1e-9

#: The three lines of evidence the report must carry, by the labels it prints them under.
LINE_LABELS = ("Drago-Wayland enthalpy", "Frontier orbital gap", "HSAB hardness match")

#: A fact label containing any of these would be a field that combines the lines. The report has none and must not gain one.
COMBINED_WORDS = ("score", "combined", "overall", "composite", "total", "rank", "rating")

#: The report's own sentence for a role the person set, which is what the gate asks for (`role = acid`).
ROLE_SET_BY_USER = "Role: as you set it."


@dataclass(frozen=True)
class DocumentedPair:
    """What `tests/test_lewis_adduct.py` documents for one borane with carbon monoxide. The four numbers are the
    DOCUMENTED ones, typed in, and never recomputed here: `test_the_documented_numbers_agree_with_their_inputs` checks
    that they follow from the inputs, which is the only circularity allowed."""

    name: str
    acid_lumo_ev: float
    acid_hardness_ev: float
    #: E_LUMO(acid) - E_HOMO(base).
    gap_ev: float
    #: |eta(acid) - eta(base)|.
    hardness_difference_ev: float


#: Carbon monoxide's documented HOMO energy, eV. It is the base in both pairs, so it sets both frontier gaps.
DOCUMENTED_CO_HOMO_EV = -10.17

#: Carbon monoxide's documented delta-SCF hardness, eV: the base's half of both hardness differences.
DOCUMENTED_CO_HARDNESS_EV = 8.40

#: The two pairs. BH3 binds CO and BF3 barely does; the frontier gap says so (8.13 below 10.90) and the hardness
#: difference says the opposite (1.63 above 0.89). That disagreement is the finding the recipe must not remove.
DOCUMENTED = {
    "BH3": DocumentedPair("BH3", acid_lumo_ev=-2.04, acid_hardness_ev=6.77, gap_ev=8.13, hardness_difference_ev=1.63),
    "BF3": DocumentedPair("BF3", acid_lumo_ev=0.73, acid_hardness_ev=9.29, gap_ev=10.90, hardness_difference_ev=0.89),
}


def _printed(lines: list[str], label: str) -> float | None:
    """The number on the report's own `label: x.xx eV` line, or None when there is no such line. The summary sentence that
    names both lines side by side has no colon after the label, and is not mistaken for one."""
    for line in lines:
        match = re.match(rf"\s*{re.escape(label)}: (-?\d+\.\d+) eV", line)
        if match:
            return float(match.group(1))
    return None


def measure_pair(acid: str, run: Any) -> MeasuredPair:
    """Read one evaluated pairing, the acid FIRST and its role set to acid, into what the gate judges.

    `run` is the `RecipeRun` the pairing window showed. The six numbers are the bound evidence values at the precision the
    stored runs recorded; the four a verdict compares are derived from them by `MeasuredPair`, and the report's own printed
    lines ride along so the gate can check the report against its own evidence. Raises `ValueError` naming a number that
    has no bound evidence, which is a defect to fix and not a measurement.
    """
    if run.result is None:
        raise ValueError(f"{acid} with CO has no answer to read: {run.status.value}")
    by_target = {binding.target: binding for binding in run.bindings}
    values: dict[str, float] = {}
    for target in ("first_lumo", "first_hardness", "second_homo", "second_hardness"):
        binding = by_target.get(target)
        if binding is None or binding.evidence is None:
            raise ValueError(f"{acid} with CO has no bound value for {target}")
        values[target] = binding.evidence.value
    lines = [str(line) for line in run.result.matched]
    return MeasuredPair(
        acid=acid,
        acid_lumo_ev=values["first_lumo"],
        acid_hardness_ev=values["first_hardness"],
        base_homo_ev=values["second_homo"],
        base_hardness_ev=values["second_hardness"],
        printed_gap_ev=_printed(lines, "Frontier orbital gap"),
        printed_hardness_difference_ev=_printed(lines, "HSAB hardness match"),
        all_bound=len(run.bindings) == 6 and all(binding.state is BindingState.BOUND for binding in run.bindings),
        role_set_by_user=any(line.strip() == ROLE_SET_BY_USER for line in lines),
        fact_labels=tuple(fact.label for fact in run.result.facts),
        line_names=tuple(line.split(":", 1)[0].strip() for line in lines if ":" in line),
    )


class Outcome(str, enum.Enum):
    PASS = "pass"
    FAIL = "fail"
    #: The gate could not decide: the tolerance is outside its window or unset, an ORCA other than the documented one,
    #: a run that did not complete, a number that was not bound, or a report that disagrees with its own evidence.
    #: Nothing is claimed either way.
    NOT_EVALUABLE = "not_evaluable"


@dataclass(frozen=True)
class Tolerance:
    #: The tolerance in eV, or None when the floor leaves no tolerance inside the window.
    value_ev: float | None
    floor_ev: float
    reason: str


def repeat_differences(first: Mapping[str, float], second: Mapping[str, float]) -> dict[str, float]:
    """|first - second| for each quantity. The two must name the same quantities: a repeat that measured something
    the other did not has no difference to report, and a floor must not be made of fewer quantities than were run."""
    if set(first) != set(second):
        raise ValueError(f"a repeat measures the same quantities: {sorted(first)} against {sorted(second)}")
    return {name: abs(first[name] - second[name]) for name in first}


def noise_floor_ev(*repeats: Mapping[str, float]) -> float:
    """The floor: the largest difference between any two runs that should have given the same number.

    `repeats` are the dictionaries `repeat_differences` returns (the same input run twice, the whole chain run twice).
    The largest of all of them is the floor, because the pair run is one more draw from the same chain and can differ
    from a documented value by as much as two draws differ from each other.
    """
    values = [difference for repeat in repeats for difference in repeat.values()]
    if not values:
        raise ValueError("a noise floor needs at least one repeat")
    return max(values)


def tolerance_from_floor(floor_ev: float) -> Tolerance:
    """THE RULE, written before any floor was measured: `T = max(0.01, floor rounded UP to the next 0.01 eV)`.

    Inside [0.01, 0.37] eV the rule gives a tolerance; above 0.37 it gives none, because a tolerance that wide could let
    the two hardness orderings swap, and the gate then says it cannot decide. It is never widened to make a pass.
    """
    if floor_ev < 0 or math.isnan(floor_ev):
        raise ValueError(f"a noise floor is a non-negative number, not {floor_ev!r}")
    rounded_up = math.ceil(round(floor_ev, 9) * 100) / 100
    tolerance = round(max(TOLERANCE_FLOOR_EV, rounded_up), 2)
    if tolerance > TOLERANCE_CEILING_EV + _SLACK:
        return Tolerance(
            None, floor_ev,
            f"the noise floor {floor_ev:.4f} eV needs a tolerance of {tolerance:.2f} eV, above the {TOLERANCE_CEILING_EV} eV "
            "a tolerance may not exceed, so the gate cannot tell the two hardness orderings apart",
        )
    return Tolerance(tolerance, floor_ev, f"max({TOLERANCE_FLOOR_EV}, {floor_ev:.4f} rounded up to 0.01) = {tolerance:.2f} eV")


@dataclass(frozen=True)
class MeasuredPair:
    """One pairing as the recipe evaluated it. The four numbers are DERIVED here from the six bound values (full precision,
    as the run recorded them), and the report's own printed lines are carried so the two can be checked against each other."""

    acid: str
    acid_lumo_ev: float
    acid_hardness_ev: float
    base_homo_ev: float
    base_hardness_ev: float
    #: What the report printed on its two lines (two decimals), or None when it printed none.
    printed_gap_ev: float | None
    printed_hardness_difference_ev: float | None
    #: Whether every one of the six bindings was BOUND (a current run, at this method, of this geometry).
    all_bound: bool
    #: Whether the report carries `ROLE_SET_BY_USER`.
    role_set_by_user: bool
    #: Every fact label of the report.
    fact_labels: tuple[str, ...]
    #: The name each line of the report is printed under (the text before its first colon). **THE LINES ARE CHECKED BY
    #: THIS AND NOT BY FACT LABEL**: the report files the Drago-Wayland line under the report's own name, because its
    #: text starts with a space and is not parsed into a label of its own, so a check for the label would fail a correct
    #: report. The name before the colon is what a person reads.
    line_names: tuple[str, ...]

    @property
    def gap_ev(self) -> float:
        return self.acid_lumo_ev - self.base_homo_ev

    @property
    def hardness_difference_ev(self) -> float:
        return abs(self.acid_hardness_ev - self.base_hardness_ev)


@dataclass(frozen=True)
class Row:
    """One line of the record: a quantity, the documented value, the measured one and whether it is within tolerance."""

    quantity: str
    documented_ev: float
    measured_ev: float
    difference_ev: float
    within: bool | None


@dataclass(frozen=True)
class Verdict:
    outcome: Outcome
    tolerance_ev: float | None
    #: Every reason, one sentence each: why it could not be decided, or every way it failed. Empty for a pass.
    reasons: tuple[str, ...]
    rows: tuple[Row, ...]


def judge(
    pairs: Mapping[str, MeasuredPair],
    tolerance_ev: float | None,
    *,
    orca_versions: Collection[str],
    unfinished_runs: Collection[str] = (),
) -> Verdict:
    """The verdict, decided by the conditions of the preregistration and no others.

    `pairs` is by the acid's name (`"BH3"`, `"BF3"`). `orca_versions` is every version any of the runs recorded.
    `unfinished_runs` names any run that did not complete.

    NOT EVALUABLE takes precedence over FAIL: a gate that cannot decide does not claim a failure. Within each, every
    reason is collected.
    """
    undecided: list[str] = []
    failures: list[str] = []

    if tolerance_ev is None:
        undecided.append("no tolerance is fixed")
    elif not TOLERANCE_FLOOR_EV - _SLACK <= tolerance_ev <= TOLERANCE_CEILING_EV + _SLACK:
        undecided.append(
            f"the tolerance {tolerance_ev} eV is outside the window [{TOLERANCE_FLOOR_EV}, {TOLERANCE_CEILING_EV}] eV"
        )
    elsewhere = sorted(set(orca_versions) - {ORCA_VERSION})
    if elsewhere or not set(orca_versions):
        undecided.append(
            f"ORCA {', '.join(elsewhere) if elsewhere else 'with no recorded version'} is not the documented "
            f"{ORCA_VERSION}: the numbers are recorded and are not a pass"
        )
    if unfinished_runs:
        undecided.append(f"a run did not complete: {', '.join(sorted(unfinished_runs))}")
    if set(pairs) != set(DOCUMENTED):
        undecided.append(f"the gate needs exactly the pairs {sorted(DOCUMENTED)}, not {sorted(pairs)}")

    for name in sorted(set(pairs) & set(DOCUMENTED)):
        pair = pairs[name]
        if not pair.all_bound:
            undecided.append(f"{name} with CO: not every number was bound to a current run")
        for label, printed, derived in (
            ("Frontier orbital gap", pair.printed_gap_ev, pair.gap_ev),
            ("HSAB hardness match", pair.printed_hardness_difference_ev, pair.hardness_difference_ev),
        ):
            if printed is None:
                undecided.append(f"{name} with CO: the report printed no {label} line")
            elif abs(printed - derived) > 0.005 + _SLACK:
                undecided.append(
                    f"{name} with CO: the report prints {label} {printed:.2f} eV but its own evidence gives {derived:.4f} eV"
                )

    rows: list[Row] = []
    for name in sorted(set(pairs) & set(DOCUMENTED)):
        documented, pair = DOCUMENTED[name], pairs[name]
        for quantity, expected, measured in (
            (f"{name}/CO frontier gap", documented.gap_ev, pair.gap_ev),
            (f"{name}/CO |d eta|", documented.hardness_difference_ev, pair.hardness_difference_ev),
        ):
            difference = measured - expected
            within = None if tolerance_ev is None else abs(difference) <= tolerance_ev + _SLACK
            rows.append(Row(quantity, expected, measured, difference, within))
    if not undecided:
        failures.extend(f"{row.quantity}: {row.measured_ev:.4f} eV is {row.difference_ev:+.4f} eV from the documented "
                        f"{row.documented_ev:.2f} eV, beyond {tolerance_ev} eV" for row in rows if row.within is False)
        if set(pairs) == set(DOCUMENTED):
            bh3, bf3 = pairs["BH3"], pairs["BF3"]
            if not bh3.gap_ev < bf3.gap_ev:
                failures.append(
                    f"the frontier gap does not order the pairs as documented: BH3/CO {bh3.gap_ev:.4f} eV is not below "
                    f"BF3/CO {bf3.gap_ev:.4f} eV"
                )
            if not bf3.hardness_difference_ev < bh3.hardness_difference_ev:
                failures.append(
                    "the disagreement did not reproduce: |d eta| for BF3/CO "
                    f"{bf3.hardness_difference_ev:.4f} eV is not below BH3/CO {bh3.hardness_difference_ev:.4f} eV"
                )
        for name, pair in sorted(pairs.items()):
            for word in COMBINED_WORDS:
                for label in dict.fromkeys(pair.fact_labels + pair.line_names):
                    if word in label.lower():
                        failures.append(f"{name} with CO: the report has a field that combines lines ({label!r})")
            absent = [label for label in LINE_LABELS if label not in pair.line_names]
            if absent:
                failures.append(f"{name} with CO: the report lacks the line(s) {', '.join(absent)}")
            if not pair.role_set_by_user:
                failures.append(f"{name} with CO: the role was not recorded as set by the user")

    if undecided:
        return Verdict(Outcome.NOT_EVALUABLE, tolerance_ev, tuple(undecided), tuple(rows))
    if failures:
        return Verdict(Outcome.FAIL, tolerance_ev, tuple(failures), tuple(rows))
    return Verdict(Outcome.PASS, tolerance_ev, (), tuple(rows))
