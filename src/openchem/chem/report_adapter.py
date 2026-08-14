"""Turning an `AlertResult` into facts.

**Not a migration shim, and not temporary.** `AlertResult` stays in the
plugin API -- `PluginContext` hands it to third-party calculators and
`docs/PLUGIN_SDK.md` documents it -- so a plugin will still be producing
one long after the fifteen built-in calculators have moved to
`ReportResult`. This is how those keep rendering like everything else.

It also let the presentation work land in the right order: the renderer
improved every result BEFORE any calculator changed, rather than each
calculator's migration being a prerequisite for seeing anything.

WHAT IT CANNOT RECOVER, and why the migrations still matter. A `Fact`
carries units, a basis, evidence, limitations, which atoms it is about
and how specialist it is. A `matched` string carries none of that, so
everything here is a guess made from the only structure a string has:

    "Max radius (from centroid): 2.35 A"   ->  label / value / units
    "8 alert(s) matched"                    ->  a single opaque line

The split on `": "` is the whole of the cleverness, and it is deliberately
conservative -- see `_split`.
"""

from __future__ import annotations

import re

from openchem.domain.report import Fact, FactCategory, ReportResult
from openchem.domain.scientific_result import AlertResult
from openchem.domain.structure_issue import Basis, Severity

#: `alert.category` is a free-text string chosen by the producer; a
#: `Fact` needs one of the nine `FactCategory` values. Anything unlisted
#: becomes STRUCTURE rather than being dropped -- a fact filed under the
#: wrong heading is recoverable, a missing one is not.
_CATEGORY_BY_NAME: dict[str, FactCategory] = {
    "identity": FactCategory.IDENTITY,
    "naming": FactCategory.IDENTITY,
    "physicochemical": FactCategory.IDENTITY,
    "charge": FactCategory.ELECTRONIC,
    "electronic": FactCategory.ELECTRONIC,
    "quantum": FactCategory.QUANTUM,
    "lewis": FactCategory.ELECTRONIC,
    "nmr": FactCategory.SPECTROSCOPY,
    "topology": FactCategory.TOPOLOGY,
    "geometry": FactCategory.GEOMETRY,
    "surface": FactCategory.GEOMETRY,
    "shape": FactCategory.GEOMETRY,
    "regulatory": FactCategory.REGULATORY,
    "medicinal_chemistry": FactCategory.STRUCTURE,
    "admet": FactCategory.STRUCTURE,
    "substructure": FactCategory.STRUCTURE,
    "stereochemistry": FactCategory.STRUCTURE,
    "interactions": FactCategory.STRUCTURE,
    "pka": FactCategory.ELECTRONIC,
}

#: `"Label: 2.35 A"` -> label, number, unit. Anchored so a line that is
#: prose rather than a measurement does not match: `"Note: this is
#: indicative only"` has no number after the colon and stays one line.
#:
#: **THE SIGN CLASS IS `[-+]`, NOT `-`, AND THAT COST TWO CALCULATORS.**
#: A producer that formats with `f"{v:+.2f}"` -- which is the right thing
#: to do for a signed component, since it makes the sign column line up --
#: emits `"Dipole Z: +0.16 Debye"`. A leading-minus-only pattern refuses
#: that, so the fact fell back to the generic label and the panel showed
#: three parsed component rows beside one unparsed one, the difference
#: being nothing but the sign of the number. Measured by instrumenting
#: this function and running all 49 registered calculators over ten
#: molecules with real conformers -- 484 distinct lines, of which 18 were
#: refused for their sign alone:
#:
#:      9  Dipole X/Y/Z: +0.00 Debye     chem/dipole.py
#:      4  HOMO: +1.00 beta              chem/huckel.py -- a bonding HOMO
#:                                       is positive in `E = alpha+x*beta`,
#:                                       so this was refused on essentially
#:                                       every pi system, not an edge case
#:      5  Orbital energies (beta): ...  chem/huckel.py, a value LIST
#:
#: The value class keeps `,` in it deliberately, and that is what makes
#: the third row safe. A list comes out as value `"+2.00,"` -- unparseable
#: as a float, so `result_reduction` correctly declines to make it a
#: numeric column, while `display_value` still reconstructs the line byte
#: for byte. Tightening this to a bare number was measured and is WORSE on
#: both counts: it yields `2.0` for a ten-orbital spectrum and inserts a
#: stray space before the comma. See
#: `test_a_value_list_is_labelled_without_becoming_a_number`.
#:
#: **DO NOT ADD A `(?=\s|$)` BOUNDARY** to keep lists out. It is the
#: obvious way to do it and the same sweep says it regresses 31 real
#: lines: `"C: 23.79%"` and `"Percent buried volume: 13.30%"` attach their
#: unit with no space, so requiring whitespace after the number refuses
#: the elemental analysis and the buried-volume result outright.
_MEASUREMENT = re.compile(r"^(?P<label>[^:]{1,60}):\s+(?P<value>[-+]?\d[\d.,eE+-]*)\s*(?P<units>[^\s].*)?$")


def category_for(name: str) -> FactCategory:
    return _CATEGORY_BY_NAME.get(name, FactCategory.STRUCTURE)


def _split(line: str, source: str, category: FactCategory) -> Fact:
    """One `matched` line as a fact, recovering a label and units if it can.

    CONSERVATIVE ON PURPOSE. Splitting every `": "` would turn
    `"Note: densities on those atoms are indicative only"` into a fact
    labelled "Note", and a limitation dressed up as a measurement is worse
    than an unsplit line. So the pattern insists on a NUMBER after the
    colon, which is what distinguishes a measurement from a sentence.
    """
    match = _MEASUREMENT.match(line.strip())
    if match is None:
        return Fact(
            category=category,
            label=source,
            value=line,
            display_value=line,
            source=source,
            basis=Basis.HEURISTIC,
        )
    return Fact(
        category=category,
        label=match.group("label").strip(),
        value=match.group("value"),
        display_value=(match.group("value") + " " + (match.group("units") or "")).strip(),
        source=source,
        basis=Basis.HEURISTIC,
        units=(match.group("units") or "").strip(),
    )


def facts_from_alert(alert: AlertResult) -> tuple[Fact, ...]:
    """An `AlertResult`'s lines as facts.

    `Basis.HEURISTIC` throughout, and that is honest rather than
    pessimistic: the producer did not say, and this cannot know. A
    migrated calculator states its own basis per fact, which is one of the
    concrete things the migrations buy.
    """
    category = category_for(alert.category)
    return tuple(_split(line, alert.name, category) for line in alert.matched)


def report_from_alert(alert: AlertResult) -> ReportResult:
    """The whole result as a report, for a renderer that wants facts.

    A FAILED alert becomes a report carrying its error rather than an
    empty one: `cache_state` and `error` travel on `ScientificResult` and
    are what let the panel say "this needs a 3D conformer" instead of a
    green "Clean".
    """
    return ReportResult(
        molecule_uuid=alert.molecule_uuid,
        report_id=alert.alert_id,
        name=alert.name,
        category=alert.category,
        facts=facts_from_alert(alert),
        cache_state=alert.cache_state,
        error=alert.error,
        provenance=alert.provenance,
    )


def report_fields(
    *,
    alert_id: str,
    name: str,
    molecule_uuid: str,
    matched: list[str] | None = None,
    category: str = "other",
    **rest,
) -> dict:
    """`AlertResult(...)` keywords, as `ReportResult(...)` keywords.

    Lets a calculator migrate by changing one call rather than rewriting
    every keyword at every site -- there are 20 of them across 13 modules,
    and a 20-way hand edit is 20 chances to transpose a field.

    `severity` is dropped rather than carried: a `ReportResult` is by
    definition not a catalog, so the field would always be INFO and a
    field that is always the same value is a field nobody reads.
    """
    rest.pop("severity", None)
    lines = list(matched or [])
    template = AlertResult(
        alert_id=alert_id, name=name, molecule_uuid=molecule_uuid,
        matched=lines, category=category,
    )
    return {
        "molecule_uuid": molecule_uuid,
        "report_id": alert_id,
        "name": name,
        "category": category,
        "facts": facts_from_alert(template),
        **rest,
    }


def is_catalog(alert: AlertResult) -> bool:
    """Whether this result is a genuine alert catalog.

    The producer declares it through `severity`; guessing from the id
    would be a heuristic, and the producer knows. Counted when `severity`
    was introduced: 5 of 25 `alert_id`s are catalogs.
    """
    return alert.severity is not Severity.INFO
