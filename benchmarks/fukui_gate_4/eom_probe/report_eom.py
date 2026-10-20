"""Reads the EOM-IP-CCSD probe's records and prints the comparison `PLAN.md` fixed: each molecule's EOM ladder at each basis, the sigma-pi gap G of the EOM reference, the gaps of B3LYP and wB97X-D3
at the decision basis (def2-TZVP) and at 6-31G*, which functional is nearer, the pyridine validation, and the reading rule's outcome.

    python report_eom.py            writes report.txt and summary.json beside this file
    python report_eom.py --no-write

EOM records: `artifacts/<tag>/runs.jsonl`. B3LYP: gate 4's records (6-31G*) and `../basis_probe/artifacts/def2tzvp`. wB97X-D3: `../functional_probe/artifacts/wb97xd3` (6-31G*) and `.../wb97xd3_def2tzvp`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "basis_probe"))
sys.path.insert(0, str(HERE.parent / "functional_probe"))

import report_functional as functional  # noqa: E402
import report_probe as base  # noqa: E402

from openchem.app import fukui_gate_4 as gate  # noqa: E402

#: The EOM bases in order of size, with the folder each one's records are in. aug-cc-pVTZ (about 640 functions for pyrimidine) is not attempted: a canonical CCSD of that size does not fit this machine.
LADDER = (("cc-pVDZ", "ccpvdz"), ("aug-cc-pVDZ", "augccpvdz"), ("cc-pVTZ", "ccpvtz"))
RULE_MOLECULES = ("pyrimidine", "pyrazine")
PYRIDINE_EOM_CCSDT = (0.15, 0.85, 3.17)  # trofimov2017 Table V: 1a2 pi, 2b1 pi, 5b2 sigma, in eV above the 7a1
#: The difference between the two functionals' errors below which a molecule is a tie; the largest change of G between the two largest EOM bases above which the reference is called not converged; the pyridine tolerance (gate 4's).
TIE_EV, CONVERGED_EV, VALIDATION_EV = 0.05, 0.10, 0.25


def load(tag: str, name: str) -> dict | None:
    path = HERE / "artifacts" / tag / "runs.jsonl"
    if not path.exists():
        return None
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    done = [r for r in rows if r["species"] == name and r["kind"] == "EOM" and r["completed"]]
    return done[-1] if done else None


def eom_gap(record: dict | None) -> float | None:
    """G = E(lowest pi root) - E(lowest sigma root) in eV, positive when the sigma root is lower."""
    if not record:
        return None
    pi = next((r for r in record["roots"] if r["kind"] == "pi"), None)
    sigma = next((r for r in record["roots"] if r["kind"] == "sigma"), None)
    return None if pi is None or sigma is None else pi["energy_ev"] - sigma["energy_ev"]


def dft_gap(root: Path | None, tag: str | None, name: str) -> float | None:
    """The sigma-pi gap of a DFT ladder: gate 4's records when `tag` is None, else `root/tag/runs.jsonl`."""
    record = base.records(None, name) if tag is None else functional.load(root, tag, name)
    return base.sigma_pi_gap(base.ladder(record)) if record else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    by_name = {s.name: s for s in (*gate.GATE_SPECIES, *gate.CALIBRATION)}
    lines: list[str] = []
    summary: dict = {"molecules": {}}
    present = [(label, tag) for label, tag in LADDER if any(load(tag, n) for n in (*RULE_MOLECULES, "pyridine"))]
    decision = next(((label, tag) for label, tag in reversed(present) if all(load(tag, n) for n in (*RULE_MOLECULES, "pyridine"))), None)
    for name in (*RULE_MOLECULES, "pyridine"):
        reference = by_name[name].reference
        lines.append(f"\n{name}" + (f"  (printed range of the gap {reference.gap_ev[0]:.2f} to {reference.gap_ev[1]:.2f} eV)" if reference else "  (calibration)"))
        entry: dict = {"G_eom": {}}
        for label, tag in LADDER:
            record = load(tag, name)
            if not record:
                lines.append(f"  EOM {label:12s} no completed record")
                continue
            e0 = record["roots"][0]["energy_ev"]
            shown = ", ".join(f"{r['energy_ev'] - e0:.3f} ({r['kind']})" for r in record["roots"][:6])
            gap = eom_gap(record)
            entry["G_eom"][label] = gap
            low_singles = min(r["singles_percent"] or 0 for r in record["roots"][:4])
            lines.append(f"  EOM {label:12s} first IP {e0:.3f} eV; {shown} | G = {gap:+.3f}   (lowest four roots: singles >= {low_singles:.0f}%) [{record['seconds']:.0f} s]")
        gaps = {
            "B3LYP 6-31G*": dft_gap(None, None, name), "wB97X-D3 6-31G*": dft_gap(HERE.parent / "functional_probe" / "artifacts", "wb97xd3", name),
            "B3LYP def2-TZVP": dft_gap(HERE.parent / "basis_probe" / "artifacts", "def2tzvp", name),
            "wB97X-D3 def2-TZVP": dft_gap(HERE.parent / "functional_probe" / "artifacts", "wb97xd3_def2tzvp", name)}
        entry["G_dft"] = gaps
        lines.append("  DFT gaps G: " + ", ".join(f"{k} " + (f"{v:+.3f}" if v is not None else "missing") for k, v in gaps.items()))
        summary["molecules"][name] = entry

    # pyridine validation at the decision basis
    lines.append("\npyridine against EOM-IP-CCSDT (+0.15, +0.85, +3.17 for the 1a2, 2b1 and 5b2 states above the 7a1):")
    valid, validation_text = None, "no decision basis yet (a basis is missing for one of the three molecules)"
    for label, tag in LADDER:
        record = load(tag, "pyridine")
        if record:
            e0 = record["roots"][0]["energy_ev"]
            lines.append(f"  EOM {label:12s} " + ", ".join(f"{r['energy_ev'] - e0:.3f} ({r['kind']})" for r in record["roots"][:4]))
    if decision:
        record = load(decision[1], "pyridine")
        e0 = record["roots"][0]["energy_ev"]
        four = record["roots"][:4]
        got = [r["energy_ev"] - e0 for r in four[1:]]
        kinds_ok = [r["kind"] for r in four] == ["sigma", "pi", "pi", "sigma"]
        errors = [abs(g - ref) for g, ref in zip(got, PYRIDINE_EOM_CCSDT)]
        valid = kinds_ok and all(e <= VALIDATION_EV for e in errors)
        validation_text = f"at {decision[0]}: kinds sigma, pi, pi, sigma: {kinds_ok}; errors {', '.join(f'{e:.3f}' for e in errors)} eV (tolerance {VALIDATION_EV})"
    lines.append("  validation " + validation_text)

    # the reading rule
    verdict, why = "NOT YET", ["the three molecules are not all complete at one basis"]
    if decision:
        label, _tag = decision
        why = [f"decision basis: {label}", "validation of the pipeline on pyridine: " + ("PASSED" if valid else "FAILED")]
        converged = True
        previous = next(((lab, t) for (lab, t) in reversed(present) if (lab, t) != decision and all(load(t, n) for n in RULE_MOLECULES)), None)
        shifts = {}
        if previous:
            for name in RULE_MOLECULES:
                shifts[name] = summary["molecules"][name]["G_eom"][label] - summary["molecules"][name]["G_eom"][previous[0]]
            converged = all(abs(v) <= CONVERGED_EV for v in shifts.values())
            why.append(f"change of G from {previous[0]} to {label}: " + ", ".join(f"{n} {v:+.3f}" for n, v in shifts.items()) + f" -> {'converged' if converged else 'NOT converged'} (limit {CONVERGED_EV})")
        else:
            why.append("no smaller basis to judge convergence against")
        winners = {}
        for name in RULE_MOLECULES:
            g_eom = summary["molecules"][name]["G_eom"][label]
            gaps = summary["molecules"][name]["G_dft"]
            g_b, g_w = gaps["B3LYP def2-TZVP"], gaps["wB97X-D3 def2-TZVP"]
            if g_b is None or g_w is None:
                winners[name] = None
                why.append(f"{name}: a DFT gap at def2-TZVP is missing")
                continue
            e_b, e_w = abs(g_b - g_eom), abs(g_w - g_eom)
            winners[name] = "wB97X-D3" if e_b - e_w >= TIE_EV else "B3LYP" if e_w - e_b >= TIE_EV else "TIE"
            why.append(f"{name}: G(EOM) {g_eom:+.3f}; B3LYP {g_b:+.3f} (error {e_b:.3f}), wB97X-D3 {g_w:+.3f} (error {e_w:.3f}) -> {winners[name]}")
        if valid is not True:
            verdict = "NOT EVALUABLE"
        elif any(w is None for w in winners.values()):
            verdict = "NOT YET"
        else:
            values = set(winners.values())
            verdict = ("NEITHER DISTINGUISHABLE" if values == {"TIE"} else "MIXED" if {"B3LYP", "wB97X-D3"} <= values
                       else "B3LYP NEARER" if "B3LYP" in values else "wB97X-D3 NEARER")
        if verdict not in ("NOT YET", "NOT EVALUABLE") and not converged:
            verdict += " (PROVISIONAL: the basis is not converged)"
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
