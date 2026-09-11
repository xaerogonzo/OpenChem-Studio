"""Generate `docs/CALCULATOR_REFERENCE.md` from the live registry.

Same split as `build_sources_doc.py` and `build_regulatory_rulesets.py`: the
SOURCE is hand-edited and reviewed, the Markdown is machine-owned and must
not be edited. Here the source is the registry itself -- every calculator
already declares what it is, what it runs on, what it produces and what it
can be asked -- plus `ui/fact_help.py` for the always-on descriptors and
`domain/calculator_taxonomy.RETIREMENTS` for the names that are gone.

**WHY GENERATE RATHER THAN WRITE.** A hand-written reference over 68
calculators is 68 places to forget when one is added, renamed, re-categorised
or retired, and this repository has already paid for that shape four times
(`inapplicable_calculators`, the `_PAYLOAD_FIELDS` probe, the panel's private
taxonomy copy, and a guide that said 51 while the registry held 53). The
declarations are what the APPLICATION reads; a reference derived from them
cannot describe a tree that does not exist.

**WHAT IT DOES NOT DO.** It does not validate anything -- that is
`tests/test_calculator_reference.py`, which owns completeness and the
relationships. A generator that also validated would report a problem in the
one place nobody runs.

`--check` regenerates in memory and compares byte for byte, which catches
BOTH failure modes in one pass: a hand-edited file differs from what the
registry produces, and so does a stale one. `build_sources_doc.py` needs a
hash as well because its source is a separate file that can move underneath
it; here the source IS the code being imported, so there is nothing to get
out of step with.

**OUTPUT MUST BE DETERMINISTIC**, or `--check` becomes decorative. No
timestamps, no absolute paths, no dict iteration that depends on insertion
luck: categories come out in the taxonomy's declared display order and
calculators are sorted within one.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

GENERATED = ROOT / "docs" / "CALCULATOR_REFERENCE.md"

#: A help anchor is `[a-z0-9-]+` -- no underscores -- while a calculator id
#: uses them. The two therefore differ by separator, and every reference to
#: one from the other goes through here rather than through a second
#: `.replace()` somewhere else.
def anchor_for(calculator_id: str) -> str:
    return "calc-" + calculator_id.replace("_", "-").replace(".", "-")


#: What each result kind means to somebody reading it, in the second person.
#: A closed table rather than a guess from the class name: the vocabulary is
#: `domain/result_kinds.py`'s and this is a rendering of it.
_PRODUCES = {
    "ReportResult": "a list of facts, each with its own units, basis and evidence",
    "AlertResult": "a list of matched lines",
    "PerAtomDataset": "one value per atom, with a depiction coloured by them",
    "PhCurveResult": "a curve against pH",
    "StructureSetResult": "a set of structures",
    "SpectrumResult": "a spectrum",
    "NMRSpectrumResult": "an NMR spectrum",
    "VibrationalSpectrumResult": "a vibrational spectrum",
    "TrajectoryResult": "a trajectory you can play",
}

_INPUT = {
    "drawing": "the 2D drawing, so no conformer is needed",
    "geometry": "a real 3D conformer -- generate one first",
}

_BASIS = {
    "empirical": "empirical (fitted to measured data, with real scatter)",
    "ab_initio": "ab initio (computed from theory rather than fitted)",
}


def _result_kind(definition) -> str:
    """What the compute function says it returns, or "" if it does not say.

    **THE RAW ANNOTATION IS THE FALLBACK, AND IT IS NOT A NICETY.**
    `get_type_hints` resolves a string annotation against the module's
    namespace, so a forward reference to a name imported only under
    `TYPE_CHECKING` -- which is how `compute_oxidation_states` declares
    `-> "PerAtomDataset"` -- raises `NameError` and looks identical to a
    function that declared nothing. Reading the signature's own annotation
    recovers it, at the cost of getting a string rather than a class, which
    is all this needs.
    """
    import inspect
    import typing

    compute = getattr(definition.execution, "compute", None)
    if compute is None:
        return ""
    try:
        annotation = typing.get_type_hints(compute).get("return")
        if annotation is not None:
            return getattr(annotation, "__name__", "")
    except Exception:  # noqa: BLE001 - a plugin's annotation must not break the doc
        pass
    try:
        raw = inspect.signature(compute).return_annotation
    except (TypeError, ValueError):
        return ""
    if raw is inspect.Signature.empty:
        return ""
    return str(raw).strip("\"'").rsplit(".", 1)[-1]


def _parameter_line(parameter) -> str:
    bits = [f"`{parameter.name}`", f"-- {parameter.label}"]
    if parameter.choices:
        bits.append("(" + ", ".join(str(c) for c in parameter.choices) + ")")
    if parameter.default not in (None, ""):
        bits.append(f"default `{parameter.default}`")
    if parameter.minimum is not None and parameter.maximum is not None:
        bits.append(f"range {parameter.minimum} to {parameter.maximum}")
    return "- " + " ".join(bits)


def _calculator_section(definition, retired_by_target) -> list[str]:
    from openchem.domain.calculator import ServiceExecution

    lines = [
        f"<!-- help:{anchor_for(definition.calculator_id)} -->",
        f"### {definition.display_name}",
        "",
        definition.description,
        "",
    ]

    aliases = retired_by_target.get(definition.calculator_id, [])
    if aliases:
        names = ", ".join(f"**{a.display_name}**" for a in aliases)
        lines += [
            f"Also known as {names} -- retired and folded in here. "
            f"{aliases[0].reason}",
            "",
        ]

    kind = _result_kind(definition)
    produces = _PRODUCES.get(kind)
    if isinstance(definition.execution, ServiceExecution):
        lines.append(
            f"- Runs from the **{definition.execution.panel_name}** panel rather "
            "than from a Properties button."
        )
    elif produces:
        lines.append(f"- Produces {produces}.")
    if definition.calculation_input in _INPUT:
        lines.append(f"- Runs on {_INPUT[definition.calculation_input]}.")
    if definition.prediction_basis in _BASIS:
        lines.append(f"- Basis: {_BASIS[definition.prediction_basis]}.")
    if definition.parameters:
        lines.append("- Options:")
        lines += ["  " + _parameter_line(p) for p in definition.parameters]
    lines.append("")
    return lines


def _descriptor_sections() -> list[str]:
    """The always-on values, grouped by the category their producer declares.

    Their prose is `ui/fact_help.py`'s -- the same text the reader shows when
    you hover the name -- because a second copy written for the reference
    would be a second thing to keep true. What the reference adds is what a
    tooltip has no room for: the units, the group, and the citation.
    """
    from openchem.chem.descriptor_providers import (
        _DESCRIPTOR_SPECS,
        _SHAPE_DESCRIPTOR_SPECS,
    )
    from openchem.domain.calculator_taxonomy import category_label
    from openchem.domain.descriptor_aggregate import descriptor_help_id
    from openchem.ui.fact_help import CONTRACTS

    rows = [(d, n, u, c) for d, n, u, c in _DESCRIPTOR_SPECS]
    rows += [(d, n, u, "shape") for d, n, u in _SHAPE_DESCRIPTOR_SPECS]

    by_category: dict[str, list] = {}
    for descriptor_id, name, units, category in rows:
        by_category.setdefault(category or "other", []).append(
            (descriptor_id, name, units)
        )

    lines = [
        "<!-- help:always-on-properties -->",
        "## Always-on properties",
        "",
        "These are computed for every molecule the moment you select it -- there "
        "is no button, because there is nothing to start. They are read in the "
        "Results panel as one entry, **Molecular Properties**, where each keeps "
        "its own units, provenance and state.",
        "",
        "Hovering a name in that panel shows the same definition given here.",
        "",
    ]
    for category in sorted(by_category):
        lines += [f"### {category_label(category)}", ""]
        for descriptor_id, name, units in sorted(by_category[category], key=lambda r: r[1]):
            contract = CONTRACTS.get(descriptor_help_id(descriptor_id))
            text = contract.text if contract else ""
            suffix = f" _Units: {units}._" if units else ""
            cite = ""
            if contract is not None and contract.source_key:
                cite = f" _Source: `{contract.source_key}`._"
            lines.append(f"- **{name}** -- {text}{suffix}{cite}")
        lines.append("")
    return lines


def render() -> str:
    from openchem.bootstrap import build_service_container
    from openchem.domain.calculator_taxonomy import (
        RETIREMENTS,
        category_label,
        category_sort_key,
    )

    registry = build_service_container().calculator_registry

    retired_by_target: dict[str, list] = {}
    for retirement in RETIREMENTS.values():
        retired_by_target.setdefault(retirement.replaced_by, []).append(retirement)

    lines = [
        "<!-- GENERATED by tools/build_calculator_reference.py -- do not edit. -->",
        "<!-- The source is the calculator registry itself; edit a declaration "
        "and regenerate. -->",
        "",
        "<!-- help:calculator-reference -->",
        "# Calculator reference",
        "",
        "One section per calculator, and one for the always-on properties. This "
        "is the deep answer; the tooltip on a button or a value is the short "
        "one, and both point here.",
        "",
        "Every section says what the calculator produces, what it needs to run, "
        "whether its numbers are fitted or computed, and what you can ask it. "
        "A calculator that has been retired is listed under whatever does its "
        "job now, by its old name, so searching for one still finds it.",
        "",
    ]

    categories = sorted(registry.categories(), key=category_sort_key)
    for category in categories:
        definitions = sorted(
            registry.by_category(category), key=lambda d: d.display_name
        )
        if not definitions:
            continue
        lines += [f"## {category_label(category)}", ""]
        for definition in definitions:
            lines += _calculator_section(definition, retired_by_target)

    lines += _descriptor_sections()

    lines += [
        "<!-- help:locant-coverage -->",
        "## What the locants cover",
        "",
        "Measured over the 181-molecule naming corpus in `benchmarks/naming`, "
        "and the reason IUPAC Locants reports **None found** for most drug-like "
        "structures rather than failing:",
        "",
        "| | coverage | |",
        "|---|---|---|",
        "| ring systems | 45.3% of heavy atoms | every molecule |",
        "| functional groups | 19.7% | every molecule |",
        "| IUPAC locants | 34.8% | 105 of 181 molecules |",
        "",
        "The asymmetry is the point. Naming dispatches to several tree shapes "
        "and only one carries a numbering: 95 of the 181 name to a retained "
        "string with no atom indices at all -- caffeine and camphor among "
        "them -- so there is nothing to map. Even a substitutive name numbers "
        "only its parent, which is why naproxen's covers 3 of its 17 atoms.",
        "",
        "A retained-ring lookup is the mitigation, and lifts coverage from "
        "22.4% to 34.8%. \"None found\" is therefore an ordinary answer here, "
        "not a failure.",
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the generated file is missing, stale or hand-edited",
    )
    args = parser.parse_args(argv)

    rendered = render()
    if not args.check:
        GENERATED.write_text(rendered, encoding="utf-8")
        print(f"wrote {GENERATED.relative_to(ROOT)} ({len(rendered)} chars)")
        return 0

    if not GENERATED.exists():
        print(f"{GENERATED.relative_to(ROOT)} does not exist; run this tool")
        return 1
    current = GENERATED.read_text(encoding="utf-8")
    if current == rendered:
        return 0
    print(
        f"{GENERATED.relative_to(ROOT)} is stale or hand-edited. It is generated "
        "from the calculator registry: change the declaration, then re-run "
        "tools/build_calculator_reference.py."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
