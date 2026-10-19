"""Reads the second-functional probe's records and prints the comparison `PLAN.md` fixed: each molecule's state ladder at B3LYP and at the other functional, the sigma-pi gap G, the shift S, the distance from gate 4's printed range, and the reading rule's outcome.

    python report_functional.py                                  writes report.txt and summary.json beside this file
    python report_functional.py --root ../basis_probe/artifacts --tag def2tzvp --label "B3LYP def2-TZVP" --no-write
                                                                 a dry run of the rule on records that already exist (the larger-basis probe's), to see it run

The B3LYP column is gate 4's own records (`../artifacts/runs.jsonl`, and `../artifacts/calibration/runs.jsonl` for pyridine), read through `basis_probe/report_probe.py`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "basis_probe"))

import report_probe as base  # noqa: E402

from openchem.app import fukui_gate_4 as gate  # noqa: E402

SIX = base.SIX
OUTSIDE = base.OUTSIDE  # outside their printed range at B3LYP/6-31G* in the gate's record (11.4)
SMALL_SHIFT_EV = 0.05  # PLAN.md: |S| below this is "where B3LYP had it"
MOVED_SHIFT_EV = 0.05  # PLAN.md: |S| at or above this is "moved"
INSIDE_NEEDED = 3  # of the four OUTSIDE gaps, for SUPPORTED
SMALL_NEEDED = 4  # of the six, for NOT SUPPORTED
PYRIDINE_EOM = base.PYRIDINE_EOM


def load(root: Path, tag: str, name: str) -> dict | None:
    """The last completed exhaustive-search record of a species under `root/tag/runs.jsonl`."""
    path = root / tag / "runs.jsonl"
    if not path.exists():
        return None
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    done = [r for r in rows if r["species"] == name and r["kind"] == "E" and r["completed"]]
    return done[-1] if done else None


def decide(summary: dict) -> tuple[str, list[str]]:
    """The reading rule of PLAN.md. The first line that holds decides; returns the outcome and the lines that say why."""
    why: list[str] = []
    missing = [n for n in SIX if summary["molecules"][n].get("S") is None]
    if missing:
        return "NOT YET", [f"no completed record, or no sigma-pi gap, for: {', '.join(missing)}"]
    flipped = [n for n in SIX if summary["molecules"][n]["lowest_kind"] != summary["molecules"][n]["lowest_kind_b3lyp"]]
    inside = [n for n in OUTSIDE if summary["molecules"][n]["distance"][1] == 0.0]
    pyrazine_inside = summary["molecules"]["pyrazine"]["distance"][1] == 0.0
    small = [n for n in SIX if abs(summary["molecules"][n]["S"]) < SMALL_SHIFT_EV]
    toward = [n for n in SIX if summary["molecules"][n]["S"] >= MOVED_SHIFT_EV]
    away = [n for n in SIX if summary["molecules"][n]["S"] <= -MOVED_SHIFT_EV]
    why.append(f"a change of the lowest state's kind: {flipped or 'none'}")
    why.append(f"of the four outside their range at B3LYP, inside it now: {len(inside)} ({', '.join(inside) or 'none'}); pyrazine inside: {pyrazine_inside}")
    why.append(f"|S| below {SMALL_SHIFT_EV} eV in {len(small)} of 6 ({', '.join(small) or 'none'}); S at least +{MOVED_SHIFT_EV}: {len(toward)} ({', '.join(toward) or 'none'}); at most -{MOVED_SHIFT_EV}: {len(away)} ({', '.join(away) or 'none'})")
    if len(inside) >= INSIDE_NEEDED and pyrazine_inside and not flipped:
        return "SUPPORTED", why
    if len(small) >= SMALL_NEEDED:
        return "NOT SUPPORTED", why
    return "MOVED", why


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", default=str(HERE / "artifacts"), help="the folder the tag folder is in")
    parser.add_argument("--tag", default="wb97xd3")
    parser.add_argument("--label", default="wB97X-D3 6-31G*", help="how the column is named in the report")
    parser.add_argument("--no-write", action="store_true", help="print only (a dry run of the rule on other records)")
    args = parser.parse_args()
    root = Path(args.root).resolve()

    by_name = {s.name: s for s in (*gate.GATE_SPECIES, *gate.CALIBRATION)}
    lines: list[str] = []
    summary: dict = {"label": args.label, "molecules": {}}
    for name in (*SIX, "pyridine"):
        reference = by_name[name].reference
        lines.append(f"\n{name}" + (f"  (printed range of the gap {reference.gap_ev[0]:.2f} to {reference.gap_ev[1]:.2f} eV)" if reference else "  (calibration)"))
        entry: dict = {}
        ladders = {}
        for label, record in (("B3LYP 6-31G*", base.records(None, name)), (args.label, load(root, args.tag, name))):
            states = base.ladder(record)
            ladders[label] = states
            if not states:
                lines.append(f"  {label:18s} no completed record")
                continue
            gap = base.sigma_pi_gap(states)
            shown = ", ".join(f"{s.above_ev:.3f} ({s.kind or '?'})" for s in states)
            lines.append(f"  {label:18s} {shown}   | sigma-pi gap G = " + (f"{gap:+.3f}" if gap is not None else "not defined") + f"   [{record['seconds']:.0f} s]")
            entry[label] = {"states": [(round(s.above_ev, 4), s.kind) for s in states], "G": gap}
        g0, g1 = entry.get("B3LYP 6-31G*", {}).get("G"), entry.get(args.label, {}).get("G")
        if ladders["B3LYP 6-31G*"]:
            entry["lowest_kind_b3lyp"] = ladders["B3LYP 6-31G*"][0].kind
        if ladders[args.label]:
            entry["lowest_kind"] = ladders[args.label][0].kind
        if g0 is not None and g1 is not None:
            entry["S"] = g0 - g1
            text = f"  S = {entry['S']:+.3f} eV"
            if reference:
                entry["distance"] = (base.distance_from(abs(g0), reference.gap_ev), base.distance_from(abs(g1), reference.gap_ev))
                text += f"; distance of |G| from the printed range {entry['distance'][0]:.3f} -> {entry['distance'][1]:.3f}"
            lines.append(text)
        summary["molecules"][name] = entry
    lines.append("\npyridine against EOM-IP-CCSDT (+0.15, +0.85, +3.17 for the 1a2, 2b1 and 5b2 states above the 7a1):")
    for label, record in (("B3LYP 6-31G*", base.records(None, "pyridine")), (args.label, load(root, args.tag, "pyridine"))):
        states = base.ladder(record)
        if states:
            lines.append(f"  {label:18s} " + ", ".join(f"{s.above_ev:.3f}" for s in states[:4]) + "   (EOM-IP-CCSDT " + ", ".join(f"{v:.2f}" for v in PYRIDINE_EOM) + ")")

    verdict, why = decide(summary)
    lines.append("\n" + "\n".join(why))
    lines.append(f"\nREADING RULE OF PLAN.md: {verdict}")
    summary["verdict"] = verdict
    text = "\n".join(lines)
    print(text)
    if not args.no_write:
        (HERE / "report.txt").write_text(text, encoding="utf-8")
        (HERE / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
