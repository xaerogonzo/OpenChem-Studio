"""Reads the larger-basis probe's records and prints the comparison `PLAN.md` fixed: each molecule's state ladder at each basis, the sigma-pi gap G, the sigma shift S, the distance from gate 4's printed range, and the reading rule's outcome.

    python report_probe.py            writes report.txt and summary.json beside this file

The 6-31G* column is gate 4's own records (`../artifacts/runs.jsonl`, and `../artifacts/calibration/runs.jsonl` for pyridine); the others are `artifacts/<tag>/runs.jsonl`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from openchem.app import fukui_gate_4 as gate  # noqa: E402

BASES = (("6-31G*", None), ("6-31+G*", "631pG"), ("def2-TZVP", "def2tzvp"))
SIX = ("pyrimidine", "pyrazine", "pyridazine", "imidazole", "pyrazole", "oxazole")
OUTSIDE = ("pyrimidine", "pyridazine", "imidazole", "oxazole")  # outside their printed range at 6-31G*, in the gate's record (11.4)
PYRIDINE_EOM = (0.0, 0.15, 0.85, 3.17)  # trofimov2017 Table V, EOM-IP-CCSDT: 7a1 sigma, 1a2 pi, 2b1 pi, 5b2 sigma, in eV above the lowest


def records(tag: str | None, name: str) -> dict | None:
    path = (HERE.parent / "artifacts" / ("calibration" if name == "pyridine" else "") / "runs.jsonl") if tag is None else HERE / "artifacts" / tag / "runs.jsonl"
    if not path.exists():
        return None
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    done = [r for r in rows if r["species"] == name and r["kind"] == "E" and r["completed"]]
    return done[-1] if done else None


def ladder(record: dict | None) -> list[gate.State]:
    return gate.states_of(record["jobs"]) if record else []


def sigma_pi_gap(states: list[gate.State]) -> float | None:
    """G = E(lowest pi state) - E(lowest sigma state) in eV: positive when the sigma state is lower; None if one of the two kinds was not found."""
    pi = next((s for s in states if s.kind == "pi" and s.consistent), None)
    sigma = next((s for s in states if s.kind == "sigma" and s.consistent), None)
    return None if pi is None or sigma is None else pi.above_ev - sigma.above_ev


def distance_from(value: float, interval: tuple[float, float]) -> float:
    return max(interval[0] - value, value - interval[1], 0.0)


def main() -> None:
    by_name = {s.name: s for s in (*gate.GATE_SPECIES, *gate.CALIBRATION)}
    lines: list[str] = []
    summary: dict = {"molecules": {}}
    for name in (*SIX, "pyridine"):
        reference = by_name[name].reference
        entry: dict = {}
        lines.append(f"\n{name}" + (f"  (printed range of the gap {reference.gap_ev[0]:.2f} to {reference.gap_ev[1]:.2f} eV)" if reference else "  (calibration)"))
        for label, tag in BASES:
            record = records(tag, name)
            states = ladder(record)
            if not states:
                lines.append(f"  {label:10s} no completed record")
                continue
            gap = sigma_pi_gap(states)
            shown = ", ".join(f"{s.above_ev:.3f} ({s.kind or '?'})" for s in states)
            seconds = record["seconds"]
            lines.append(f"  {label:10s} {shown}   | sigma-pi gap G = {gap:+.3f}" if gap is not None else f"  {label:10s} {shown}   | G not defined" + f"   [{seconds:.0f} s]")
            entry[label] = {"states": [(round(s.above_ev, 4), s.kind) for s in states], "G": gap, "lowest_kind": states[0].kind}
        base_g = entry.get("6-31G*", {}).get("G")
        for label, _tag in BASES[1:]:
            g = entry.get(label, {}).get("G")
            if base_g is not None and g is not None:
                shift = base_g - g
                entry[label]["S"] = shift
                text = f"  S({label}) = {shift:+.3f} eV"
                if reference:
                    d0, d1 = distance_from(abs(base_g), reference.gap_ev), distance_from(abs(g), reference.gap_ev)
                    entry[label]["distance"] = (d0, d1)
                    text += f"; distance of |G| from the printed range {d0:.3f} -> {d1:.3f}"
                lines.append(text)
        summary["molecules"][name] = entry
    lines.append("\npyridine against EOM-IP-CCSDT (+0.15, +0.85, +3.17 for the 1a2, 2b1 and 5b2 states above the 7a1):")
    for label, tag in BASES:
        states = ladder(records(tag, "pyridine"))
        if states:
            lines.append(f"  {label:10s} " + ", ".join(f"{s.above_ev:.3f}" for s in states[:4]) + "   (EOM-IP-CCSDT " + ", ".join(f"{v:.2f}" for v in PYRIDINE_EOM) + ")")

    # the reading rule of PLAN.md
    verdict = "NOT YET: a basis is missing"
    s_big = {n: summary["molecules"][n].get("def2-TZVP", {}).get("S") for n in SIX}
    if all(v is not None for v in s_big.values()):
        at_least = sum(1 for v in s_big.values() if v >= 0.10)
        below = sum(1 for v in s_big.values() if v < 0.05)
        nearer = {n: summary["molecules"][n]["def2-TZVP"].get("distance") for n in OUTSIDE}
        all_nearer = all(d is not None and d[1] < d[0] for d in nearer.values())
        none_farther = all(d is not None and d[1] <= d[0] for d in nearer.values())
        flipped = [n for n in SIX if summary["molecules"][n].get("def2-TZVP", {}).get("lowest_kind") != summary["molecules"][n].get("6-31G*", {}).get("lowest_kind")]
        if at_least >= 5 and all_nearer:
            verdict = "SUPPORTED"
        elif below >= 3 or not none_farther:
            verdict = "NOT SUPPORTED"
        else:
            verdict = "MIXED"
        lines.append(f"\nS(def2-TZVP) >= +0.10 in {at_least} of 6; below +0.05 in {below} of 6; the four outside their range each nearer: {all_nearer}, none farther: {none_farther}; a change of the lowest state's kind: {flipped or 'none'}")
    lines.append(f"\nREADING RULE OF PLAN.md: {verdict}")
    summary["verdict"] = verdict
    text = "\n".join(lines)
    print(text)
    (HERE / "report.txt").write_text(text, encoding="utf-8")
    (HERE / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
