"""Query the application's help contracts.

GENERATED FROM THE WIDGETS, never from a parallel registry -- the same
one-authoritative-representation pattern as `build_sources_doc.py` ->
`docs/SOURCES.md`. It calls `iter_documentable_controls`, which is also
what `tests/test_tooltip_coverage.py` calls, so the guard and this tool
cannot grow two different ideas of "all interactive controls".

    uv run --no-sync python tools/list_tooltips.py --missing [--json]
    uv run --no-sync python tools/list_tooltips.py --tier 3 --undocumented
    uv run --no-sync python tools/list_tooltips.py --search docking
    uv run --no-sync python tools/list_tooltips.py --help-id docking.rmsd_lower_bound --context
    uv run --no-sync python tools/list_tooltips.py --source trott_olson2010
    uv run --no-sync python tools/list_tooltips.py --excluded
    uv run --no-sync python tools/list_tooltips.py --stale
    uv run --no-sync python tools/list_tooltips.py --json

`--context` prints an AUTHORING BRIEF and never grades anything. The whole
division of labour here is that the software guarantees the metadata
relationships while a human or an agent writes the wording; making a model
part of the oracle would give the suite a test that can disagree with
itself between runs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

#: The controls only exist once a window is built, and building one needs a
#: platform. `offscreen` is enough -- this reads widget metadata and never
#: renders.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

#: Constant prohibitions, printed with every brief.
#:
#: THE `DO NOT` BLOCK IS THE PART THAT EARNS ITS KEEP. This is exactly
#: where an agent produces valid code and scientifically misleading prose:
#: a Vina scoring error was once written into a tooltip from memory, and it
#: happened to be right, which is luck rather than method.
_PROHIBITIONS = (
    "rename or reuse the help_id -- it is a stable semantic identifier",
    "state a number that no source_key supports",
    "restate the control's own label and call it an explanation",
)

_TIER_CONTRACT = {
    1: "action + result",
    2: "what it controls + at least one applicable qualifier "
       "(unit, range, default, or behavioural consequence)",
    3: "definition + units/reference frame where applicable + the interpretation limit",
}


def _build_window():
    from PySide6.QtWidgets import QApplication

    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container

    QApplication.instance() or QApplication([])
    services = build_service_container()
    return MainWindow(services, Settings(services.event_bus), SessionManager())


def _record(control) -> dict:
    tooltip = control.help_tooltip
    return {
        "help_id": tooltip.help_id if tooltip else None,
        "tier": tooltip.tier if tooltip else None,
        "topic": tooltip.topic if tooltip else None,
        "help_anchor": tooltip.help_anchor if tooltip else None,
        "source_key": tooltip.source_key if tooltip else None,
        # DERIVED at emit time, never stored on HelpTooltip: two booleans
        # rather than a category, because a tooltip can legitimately carry
        # BOTH an external fact and an OpenChem explanation, and a
        # categorical would need a fourth term for that. A stored copy of a
        # derivable fact is a second version that can contradict the first.
        "has_external_source": bool(tooltip and tooltip.source_key),
        "has_help_anchor": bool(tooltip and tooltip.help_anchor),
        "text": tooltip.text if tooltip else None,
        "kind": control.kind,
        "status": control.status,
        "widget_class": control.widget_class,
        "object_name": control.object_name,
        "instance_path": control.instance_path,
    }


def _brief(record: dict) -> str:
    lines = [
        f"help_id: {record['help_id']}",
        f"target:  {record['widget_class']} ({record['kind']})",
        f"tier:    {record['tier']}",
        f"status:  {record['status']}",
        "",
        f"UI LABEL:        {record['object_name'] or '(none)'}",
        f"IMPLEMENTATION:  {record['instance_path']}",
        "",
        "CURRENT TEXT:",
        f"  {record['text'] or '(none)'}",
        "",
        f"SEMANTIC CONTRACT (tier {record['tier']}):",
        f"  {_TIER_CONTRACT.get(record['tier'], 'unknown tier')}",
    ]
    if record["help_anchor"]:
        lines += ["", f"DOCUMENTATION:   {record['help_anchor']}"]
    if record["source_key"]:
        lines += [f"EXTERNAL SOURCE: {record['source_key']}"]
    lines += ["", "DO NOT:"]
    lines += [f"  - {rule}" for rule in _PROHIBITIONS]
    return "\n".join(lines)


def _stale(records, window) -> list[str]:
    """Metadata INCONSISTENCY, not scientific staleness."""
    from openchem import help as help_docs

    problems: list[str] = []
    anchors = {topic.key for topic in help_docs.topics()}
    registry = ROOT / "docs" / "sources.toml"
    keys = {e["key"] for e in tomllib.loads(registry.read_text(encoding="utf-8"))["source"]}

    contracts: dict[str, dict] = {}
    for record in records:
        help_id = record["help_id"]
        if help_id is None:
            continue
        previous = contracts.setdefault(help_id, record)
        if previous["text"] != record["text"] or previous["tier"] != record["tier"]:
            problems.append(f"{help_id}: two different contracts share this id")
        if record["help_anchor"] and record["help_anchor"] not in anchors:
            problems.append(f"{help_id}: help_anchor {record['help_anchor']!r} resolves to nothing")
        if record["source_key"] and record["source_key"] not in keys:
            problems.append(f"{help_id}: source_key {record['source_key']!r} is not in the registry")
        if record["tier"] == 3 and not record["help_id"]:
            problems.append(f"{record['instance_path']}: tier 3 with no help_id")
    debt = [r for r in records if r["status"] == "legacy_tooltip"]
    if debt:
        problems.append(f"migration debt: {len(debt)} controls carry a raw tooltip with no contract")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--missing", action="store_true",
                        help="controls with NO semantic help at all (not merely no tooltip)")
    parser.add_argument("--undocumented", action="store_true",
                        help="contracts with no help_anchor")
    parser.add_argument("--tier", type=int, choices=(1, 2, 3))
    parser.add_argument("--search", metavar="TEXT")
    parser.add_argument("--help-id", dest="help_id", metavar="ID")
    parser.add_argument("--source", metavar="KEY", help="every UI claim tied to a source")
    parser.add_argument("--context", action="store_true", help="print an authoring brief")
    parser.add_argument("--excluded", action="store_true", help="what was skipped, and why")
    parser.add_argument("--stale", action="store_true", help="metadata inconsistencies")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    from openchem.ui.widgets.tooltip_inventory import (
        iter_documentable_controls,
        iter_exclusions,
    )

    window = _build_window()
    controls = list(iter_documentable_controls(window))
    records = [_record(c) for c in controls]

    if args.excluded:
        rows = [
            {"reason": e.reason, "instance_path": e.instance_path, "widget_class": e.widget_class}
            for e in iter_exclusions(window)
        ]
        print(json.dumps(rows, indent=1) if args.json else
              "\n".join(f"{r['reason']:14} {r['instance_path']}" for r in rows))
        return 0

    if args.stale:
        problems = _stale(records, window)
        print(json.dumps(problems, indent=1) if args.json else
              ("\n".join(problems) if problems else "No metadata inconsistencies."))
        return 1 if problems and not args.json else 0

    selected = records
    if args.missing:
        selected = [r for r in selected if r["status"] == "missing"]
    if args.tier is not None:
        selected = [r for r in selected if r["tier"] == args.tier]
    if args.undocumented:
        selected = [r for r in selected if r["help_id"] and not r["help_anchor"]]
    if args.source:
        selected = [r for r in selected if r["source_key"] == args.source]
    if args.help_id:
        selected = [r for r in selected if r["help_id"] == args.help_id]
    if args.search:
        needle = args.search.casefold()
        selected = [
            r for r in selected
            if needle in json.dumps(r, default=str).casefold()
        ]

    if args.context:
        if not selected:
            print("No control matched.")
            return 1
        print("\n\n".join(_brief(r) for r in selected))
        return 0

    if args.json:
        print(json.dumps(selected, indent=1))
        return 0

    if not selected:
        print("Nothing matched.")
        return 0
    for record in selected:
        print(f"{record['status']:15} {str(record['help_id'] or '-'):34} {record['instance_path']}")
    print(f"\n{len(selected)} of {len(records)} controls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
