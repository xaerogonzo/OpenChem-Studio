"""Turning one molecule's result into the cells of a table row.

THE PROBLEM THIS SOLVES. Of the 50 registered calculators, exactly zero
return a scalar. They return per-atom datasets, alert lists, spectra,
structure sets, pH curves and trajectories -- shapes built for a panel that
shows one molecule. A table needs one value per molecule per column, so
something has to say what "one value" means for each of those shapes, and
every one of those answers can be wrong in a way that looks right.

THE RULES, and why each is what it is:

`AlertResult` is the interesting case, because 17 calculators return one
and most of them are really REPORTS: `matched` holds lines like
``"Randic index: 9.52"``. Counting the lines would throw the numbers away,
so those lines are PARSED, and one report calculator becomes many numeric
columns -- 27 of them for `topology_analysis` alone. That expansion is
most of what makes 46 calculators tabulate into something worth analysing.
The parser is deliberately strict; see `parse_reported_numbers`.

MEASURED, 2026-08-05, over the 16 report calculators run on aspirin with a
conformer and both sidecars configured: **73 numeric columns extracted, 25
lines refused.** Every refusal was checked by hand and all but one are
correct -- formulas, prose caveats, value lists, and desirability mappings
("MW: 180.16 -> 1.00", where the line carries two numbers and neither is
obviously the value). The exception is `logd`'s headline
``"logD = -2.44 at pH 7.4 (Henderson-Hasselbalch)"``, which is refused for
the same two-numbers-on-one-line reason and is a real gap: logD is
reachable only through `logd_curve` in a table. Loosening the rule to
catch it also catches the five cns_mpo mappings, which is the worse
trade -- a wrong column survives being looked at, a missing one does not.

`PerAtomDataset` collapses by an aggregate the caller chooses, EXCEPT when
the producer marked its values categorical, where any aggregate is
meaningless -- summing ring-system ids gives "15" for a molecule with two
rings. Those columns report the number of distinct categories instead, and
say so in the label. This is the same trap the Calculator Inspector's
"Overall: N" already had to close.

`SpectrumResult`, `StructureSetResult`, `PhCurveResult` and
`TrajectoryResult` produce a text cell and NO number. A count of NMR peaks
or of generated tautomers is a fact about the calculation, not a property
of the molecule, and putting it in a numeric column invites someone to
correlate it against LogP. They are still tabulated, because "this
molecule has 4 tautomers" is worth seeing in a row.

Kept in `chem/` and free of Qt so the reductions can be tested against
real result objects without constructing a service or a widget -- the
parsing is the part that can be wrong.
"""

from __future__ import annotations

import math
import re
from typing import Any

from openchem.domain.batch import (
    SOURCE_CALCULATOR,
    SOURCE_DESCRIPTOR,
    BatchCell,
    BatchColumn,
)
from openchem.domain.common import CATEGORICAL_SCALE, CacheState, ScientificResult
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.scientific_result import (
    AlertResult,
    PerAtomDataset,
    PhCurveResult,
    SpectrumResult,
    StructureSetResult,
    TrajectoryResult,
)

#: How a per-atom dataset collapses to one number. `sum` is offered
#: because for several of these it is the physically meaningful total (the
#: summed Crippen contribution IS the molecule's LogP; summed per-atom SASA
#: is its total accessible surface), and `max_abs` because for charges the
#: extreme matters more than the average.
PER_ATOM_AGGREGATES: tuple[str, ...] = ("mean", "sum", "min", "max", "max_abs")

_AGGREGATE_FUNCTIONS = {
    "mean": lambda values: sum(values) / len(values),
    "sum": sum,
    "min": min,
    "max": max,
    "max_abs": lambda values: max(values, key=abs),
}

# A reported line: "<label>: <number><rest>". The label is bounded at 60
# characters so a prose paragraph containing a colon ("Note: simple Huckel
# treats every pi centre...") cannot masquerade as one.
_REPORTED_LINE = re.compile(r"^(?P<label>[^:]{1,60}):\s*(?P<number>[+-]?\d+(?:\.\d+)?)(?P<rest>.*)$")

# "LogP = 1.31" -- the same measurement written with an equals sign.
_EQUALS_LINE = re.compile(r"^(?P<label>[^=]{1,60}?)\s*=\s*(?P<number>[+-]?\d+(?:\.\d+)?)(?P<rest>.*)$")

# "pKa 3.65 +/- 0.11 (ensemble spread)" -- the pKa calculator's entire
# result, and the one headline number in this file written with no
# separator at all. Matched separately rather than by loosening the rules
# above, because loosening them also admits every sentence that happens to
# contain a number.
_LABELLED_VALUE_LINE = re.compile(
    r"^(?P<label>[A-Za-z][A-Za-z0-9 _/()-]{0,40}?)\s+(?P<number>[+-]?\d+(?:\.\d+)?)"
    r"(?:\s*\+/-.*)?$"
)

# One unit token. MUST START WITH A LETTER, and that is the load-bearing
# part: it is what separates a real unit from the rest of an expression.
# Digits inside are fine and necessary ("A^3", "A^2", "Ų"), but a token
# BEGINNING with a digit or a sign is a second number, not a unit -- which
# is what keeps "MW: 180.16 -> 1.00" and "LogD: -2.44 -> 1.00" out. An
# earlier version banned digits outright and lost the polarizability and
# BBB surface-area units to it.
_UNIT_TOKEN = r"[^\W\d_][^\s,;()]{0,11}"

# What may follow the number and still leave the line a plain measurement.
# Each alternative was chosen against real output (see the module tests):
#   ""                 "Randic index: 9.52"
#   "%"                "C: 60.00%"
#   "Debye" / "A^3"    a unit token, or two
#   "(as drawn)"       "Polar surface area: 63.60 Ų (as drawn)"
#   "/ 5.00"           "CNS MPO score: 4.75 / 5.00" -- an out-of-N score,
#                      whose numerator is the value someone wants
_UNIT_TAIL = re.compile(
    r"^(?:"
    r"|%"
    rf"|{_UNIT_TOKEN}(?:\s{_UNIT_TOKEN})?"
    r"|/\s*[\d.]+"
    r")\s*(?:\([^)]{0,40}\))?$"
)


def parse_reported_numbers(lines: list[str]) -> list[tuple[str, float, str]]:
    """(label, value, units) for every line that is unambiguously one number.

    STRICT ON PURPOSE. A table column whose header says "Pi system" and
    whose values are the atom counts scraped out of "Pi system: 10 atoms,
    10 pi electrons" is worse than no column at all -- it is wrong in a way
    that survives being looked at. So a line is only accepted when what
    follows the number is empty, a percent sign, one or two unit-like
    tokens, an out-of-N denominator, or a parenthetical qualifier.

    Measured against every `AlertResult` the registry produces (see
    `tests/test_result_reduction.py`), this accepts the 60-odd real
    measurements and rejects: molecular formulas ("Formula: C9H8O4"),
    lists ("Orbital energies (beta): +2.14, +1.41, ..."), desirability
    mappings ("MW: 180.16 -> 1.00"), unavailability notes ("pKa (most
    basic): unavailable (needs a configured pkasolver environment)") and
    every prose caveat.

    A label is emitted at most once per result: `logd` reports both
    "logD = ..." and "pKa: 3.65", and a calculator that repeated a label
    would otherwise have its later value silently overwrite the earlier.
    """
    found: list[tuple[str, float, str]] = []
    seen: set[str] = set()
    for line in lines:
        parsed = _parse_line(line.strip())
        if parsed is None:
            continue
        label, value, units = parsed
        if label in seen:
            continue
        seen.add(label)
        found.append((label, value, units))
    return found


def _parse_line(line: str) -> tuple[str, float, str] | None:
    for pattern in (_REPORTED_LINE, _EQUALS_LINE):
        match = pattern.match(line)
        if match is None:
            continue
        rest = match.group("rest").strip()
        if _UNIT_TAIL.match(rest) is None:
            return None
        return match.group("label").strip(), float(match.group("number")), _units_from(rest)
    match = _LABELLED_VALUE_LINE.match(line)
    if match is not None:
        return match.group("label").strip(), float(match.group("number")), ""
    return None


def _units_from(rest: str) -> str:
    """The unit part of a tail, without any trailing qualifier.

    "Ų (as drawn)" is a surface area in Ų that was computed on the drawn
    structure -- the qualifier belongs in the label's story, not in the
    units, where it would end up in a column header reading
    "Polar surface area (Ų (as drawn))".
    """
    units = re.sub(r"\([^)]*\)", "", rest).strip()
    return "" if units.startswith("/") else units


def descriptor_column(descriptor: DescriptorValue) -> BatchColumn:
    """The column one descriptor contributes.

    `numeric` is decided from the VALUE, not from the descriptor id,
    because the provider is the only thing that knows: `formula` is a
    string and `mol_wt` is a float, and both arrive through the same field.
    """
    return BatchColumn(
        column_id=f"{SOURCE_DESCRIPTOR}:{descriptor.descriptor_id}",
        label=descriptor.name,
        units=descriptor.units,
        source=SOURCE_DESCRIPTOR,
        source_id=descriptor.descriptor_id,
        numeric=_numeric_value(descriptor.value) is not None,
    )


def descriptor_cell(descriptor: DescriptorValue) -> BatchCell:
    """One descriptor value as a cell.

    Booleans become 1.0/0.0 rather than staying text. Lipinski, Veber,
    Ghose, Egan and the rest are pass/fail flags, and as numbers they are
    directly useful: the mean of a filter column across a project is the
    fraction of it that passes, and a filter can be correlated against the
    property that drives it. The text keeps saying "Yes"/"No", so nothing
    reads as 1.0 on screen.
    """
    if descriptor.cache_state is CacheState.FAILED:
        return BatchCell(
            text="",
            cache_state=CacheState.FAILED,
            error=descriptor.error,
            provenance=descriptor.provenance,
        )
    value = descriptor.value
    return BatchCell(
        value=_numeric_value(value),
        text=_descriptor_text(value),
        provenance=descriptor.provenance,
        cache_state=descriptor.cache_state,
        error=descriptor.error,
    )


def _numeric_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        number = float(value)
        # NaN/inf reach here from 3D descriptors on degenerate geometries.
        # Passing them on would poison a mean, a correlation and a PCA
        # alike, each failing somewhere far from the cell that caused it.
        return number if math.isfinite(number) else None
    return None


def _descriptor_text(value: Any) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def reduce_result(
    result: ScientificResult,
    calculator_id: str,
    display_name: str,
    prediction_basis: str | None = None,
    per_atom_aggregate: str = "mean",
) -> list[tuple[BatchColumn, BatchCell]]:
    """Every (column, cell) pair one calculator contributes for one molecule.

    A list, not a single pair, because a report calculator legitimately
    contributes many columns -- and because returning zero pairs is a real
    answer for a result that carries nothing tabulable.
    """
    if result.cache_state is CacheState.FAILED:
        # One column carrying the failure, so the row shows WHY the value is
        # missing. A failed report calculator cannot say which columns it
        # would have produced, so it gets its own name as the column -- and
        # if another molecule succeeds, that molecule's real columns appear
        # beside this one rather than replacing it.
        return [
            (
                BatchColumn(
                    column_id=f"{SOURCE_CALCULATOR}:{calculator_id}",
                    label=display_name,
                    source=SOURCE_CALCULATOR,
                    source_id=calculator_id,
                    prediction_basis=prediction_basis,
                    numeric=False,
                ),
                BatchCell(
                    text="",
                    cache_state=CacheState.FAILED,
                    error=result.error,
                    provenance=result.provenance,
                ),
            )
        ]
    if isinstance(result, AlertResult):
        return _reduce_alert(result, calculator_id, display_name, prediction_basis)
    if isinstance(result, PerAtomDataset):
        return _reduce_per_atom(result, calculator_id, display_name, prediction_basis, per_atom_aggregate)
    return _reduce_descriptive(result, calculator_id, display_name, prediction_basis)


def _reduce_alert(
    result: AlertResult, calculator_id: str, display_name: str, prediction_basis: str | None
) -> list[tuple[BatchColumn, BatchCell]]:
    numbers = parse_reported_numbers(result.matched)
    if numbers:
        return [
            (
                BatchColumn(
                    column_id=f"{SOURCE_CALCULATOR}:{calculator_id}:{label}",
                    label=label,
                    units=units,
                    source=SOURCE_CALCULATOR,
                    source_id=calculator_id,
                    prediction_basis=prediction_basis,
                    numeric=True,
                ),
                BatchCell(
                    value=value,
                    text=f"{value:g}",
                    provenance=result.provenance,
                    cache_state=result.cache_state,
                ),
            )
            for label, value, units in numbers
        ]
    # A report whose lines carry no parseable number: an IUPAC name, a
    # stereo summary, a list of intramolecular contacts. TEXT, with no
    # value -- counting the lines would put "1" in a numeric column for
    # "No stereo elements in this structure.", which is the same
    # meaningless-total trap categorical per-atom data already closes.
    # Alert CATALOGS, where the count genuinely is the property, come
    # through `alert_catalog_columns` below instead.
    return [
        (
            BatchColumn(
                column_id=f"{SOURCE_CALCULATOR}:{calculator_id}",
                label=display_name,
                source=SOURCE_CALCULATOR,
                source_id=calculator_id,
                prediction_basis=prediction_basis,
                numeric=False,
            ),
            BatchCell(
                text="; ".join(result.matched),
                provenance=result.provenance,
                cache_state=result.cache_state,
            ),
        )
    ]


def alert_catalog_columns(alert: AlertResult) -> list[tuple[BatchColumn, BatchCell]]:
    """A structural-alert catalog (PAINS, BRENK, mutagenicity) as two cells.

    Separate from `reduce_result` because the two AlertResult populations
    mean different things. These come from `DescriptorProvider.
    compute_alerts`, where `matched` is a list of things that FIRED, so the
    length is a real per-molecule property and an empty list is a 0 rather
    than a gap -- "checked, nothing flagged" is the shape PAINS established.
    The registered calculators that also return `AlertResult` are reports,
    where the same length would be a count of prose lines.

    Two columns rather than one: the count is what sorts and correlates,
    the names are what a chemist actually needs to see.
    """
    return [
        (
            BatchColumn(
                column_id=f"alert:{alert.alert_id}:count",
                label=f"{alert.name} (matches)",
                source=SOURCE_CALCULATOR,
                source_id=alert.alert_id,
                numeric=True,
            ),
            BatchCell(
                value=float(len(alert.matched)),
                text=str(len(alert.matched)),
                provenance=alert.provenance,
                cache_state=alert.cache_state,
            ),
        ),
        (
            BatchColumn(
                column_id=f"alert:{alert.alert_id}:matched",
                label=alert.name,
                source=SOURCE_CALCULATOR,
                source_id=alert.alert_id,
                numeric=False,
            ),
            BatchCell(
                text="; ".join(alert.matched) or "none",
                provenance=alert.provenance,
                cache_state=alert.cache_state,
            ),
        ),
    ]


def _reduce_per_atom(
    result: PerAtomDataset,
    calculator_id: str,
    display_name: str,
    prediction_basis: str | None,
    aggregate: str,
) -> list[tuple[BatchColumn, BatchCell]]:
    categorical = _is_categorical(result)
    if categorical:
        # Distinct categories present, not an aggregate of the ids. "3 ring
        # systems" is a real property of the molecule; the mean of the ids
        # 1, 2, 3 is 2.0 and means nothing.
        distinct = len({round(value) for value in result.values.values()})
        label = f"{result.name or display_name} (distinct)"
        value: float | None = float(distinct)
        # Zero is a real, correlatable answer here, so the VALUE stays 0
        # rather than becoming a gap -- but a bare "0" in a cell reads as a
        # calculator that did not run. Caffeine genuinely detects no
        # functional groups (its lactam carbonyls are ring-embedded and
        # unclaimed), and the producer's own sentence saying so is what
        # makes that legible.
        text = str(distinct) if result.values else (_summary_note(result) or "0")
        units = ""
    elif result.values:
        label = f"{result.name or display_name} ({aggregate})"
        value = _AGGREGATE_FUNCTIONS.get(aggregate, _AGGREGATE_FUNCTIONS["mean"])(
            list(result.values.values())
        )
        value = _numeric_value(value)
        text = "" if value is None else f"{value:.4g}"
        units = result.units
    else:
        # Empty is not failure and must explain itself rather than render as
        # a blank cell -- caffeine detects zero functional groups because its
        # lactam carbonyls are ring-embedded, which is a finding, not a bug.
        label = f"{result.name or display_name} ({aggregate})"
        value = None
        text = _summary_note(result) or "no values"
        units = result.units
    return [
        (
            BatchColumn(
                column_id=f"{SOURCE_CALCULATOR}:{calculator_id}",
                label=label,
                units=units,
                source=SOURCE_CALCULATOR,
                source_id=calculator_id,
                prediction_basis=prediction_basis,
                numeric=True,
            ),
            BatchCell(
                value=value,
                text=text,
                provenance=result.provenance,
                cache_state=result.cache_state,
            ),
        )
    ]


def _reduce_descriptive(
    result: ScientificResult, calculator_id: str, display_name: str, prediction_basis: str | None
) -> list[tuple[BatchColumn, BatchCell]]:
    """A spectrum, structure set, pH curve or trajectory: text, no number.

    See the module docstring -- the count of peaks or tautomers describes
    the calculation, not the molecule, and a numeric column invites it to
    be correlated against something.
    """
    text = _descriptive_text(result)
    if not text:
        return []
    return [
        (
            BatchColumn(
                column_id=f"{SOURCE_CALCULATOR}:{calculator_id}",
                label=display_name,
                source=SOURCE_CALCULATOR,
                source_id=calculator_id,
                prediction_basis=prediction_basis,
                numeric=False,
            ),
            BatchCell(
                text=text,
                provenance=result.provenance,
                cache_state=result.cache_state,
            ),
        )
    ]


def _descriptive_text(result: ScientificResult) -> str:
    if isinstance(result, StructureSetResult):
        total = result.total_available if result.total_available is not None else len(result.entries)
        suffix = " (truncated)" if result.truncated else ""
        return f"{total} structures{suffix}"
    if isinstance(result, SpectrumResult):
        return f"{len(result.values)} shifts"
    if isinstance(result, PhCurveResult):
        return f"{len(result.series)} series over {len(result.ph_values)} pH points"
    if isinstance(result, TrajectoryResult):
        return f"{len(result.frames)} frames"
    return ""


def _is_categorical(result: ScientificResult) -> bool:
    return _provenance_parameter(result, "scale") == CATEGORICAL_SCALE


def _summary_note(result: ScientificResult) -> str:
    return str(_provenance_parameter(result, "summary", "") or "")


def _provenance_parameter(result: ScientificResult, key: str, default: Any = None) -> Any:
    provenance = getattr(result, "provenance", None)
    if provenance is None:
        return default
    try:
        return provenance.parameters.get(key, default)
    except AttributeError:
        return default
