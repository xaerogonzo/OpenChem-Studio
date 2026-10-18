"""The reported arm's SITE statements, written afterwards from the GATE's own records (not a gate step, decides nothing).

`fukui2_report` (the drive step the preregistration froze) was given the reported arm's records only, and `app.fukui_gate_2.reported_site_rows` looks each statement up under the species'
gate level, which that file does not hold: the four statements the rules leave out (N2O's O, NO2-'s O, benzaldehyde's para, nitrobenzene's meta) are about runs of the DECIDED arm
(`artifacts/records.json`). So `artifacts/reported.json` has an empty `site_rows`, and this file is the one call it should have made, with the same function and the gate's records.
Nothing is run: it reads a file and writes one. The frozen drive step and function are not touched.

    uv run --no-sync python benchmarks/fukui_gate_2/reported_sites.py
"""
from __future__ import annotations

import json
from pathlib import Path

from openchem.app import fukui_gate_2 as gate

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"


def main() -> None:
    records = json.loads((ARTIFACTS / "records.json").read_text(encoding="utf-8"))
    chosen, never, unfinished, conflicts = gate.settle_attempts(records)
    runs = {pair: gate.measured_from_record(record) for pair, record in chosen.items()}
    out = {
        "source": "artifacts/records.json (the decided arm's runs)", "site_rows": gate.reported_site_rows(runs),
        "not_computed": sorted(f"{m} at {level}" for m, level in never), "unfinished": unfinished, "conflicts": conflicts,
    }
    path = ARTIFACTS / "reported_sites.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    for row in out["site_rows"]:
        print(row)
    print(f"{len(out['site_rows'])} statements -> {path}")


if __name__ == "__main__":
    main()
