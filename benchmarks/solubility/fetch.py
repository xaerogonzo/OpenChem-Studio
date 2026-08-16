"""Step 1 of 2: download an evaluation set and the set ESOL was fitted on.

    uv run --no-sync python benchmarks/solubility/fetch.py

Needs nothing but the project's own environment -- no PyTDC, no throwaway
virtualenv, no Harvard Dataverse. Both files come from the AqSolDB
repository, which publishes its nine constituent datasets separately as
well as the merged result, and that separation is what makes an honest
evaluation possible here.

**WHY NOT THE MERGED AqSolDB, WHICH WAS THE FIRST PLAN.** Two reasons,
both found by looking rather than assuming:

1. It is the ADMET sidecar's own training set, so scoring that model on
   it measures memorisation -- the circularity already recorded for
   nmrshiftdb2.
2. It CONTAINS Delaney's ESOL set as one of its nine sources (dataset-G,
   reference [7] in the AqSolDB README). So it is partly training data for
   ESOL too, and the first version of this benchmark would have scored
   ESOL against its own fit without noticing.

**WHAT IS DOWNLOADED, AND WHY EACH.**

`dataset-I` is the Solubility Challenge (Llinas, Glen & Goodman 2008),
AqSolDB reference [8]: 94 rows of INTRINSIC solubility measured by one
consistent method on druglike compounds. It is the recognised
high-quality reference set for this endpoint, and it post-dates ESOL's
2004 fit.

`dataset-G` is Delaney's own ESOL set, AqSolDB reference [7]. It is
downloaded ONLY so its compounds can be EXCLUDED: 13 of the Challenge's
90 unique InChIKeys appear in it, and scoring those would be scoring
ESOL on its own training data. 80 compounds survive the exclusion.

Writes `data/`, which is NOT committed.
"""

from __future__ import annotations

import csv
import io
import json
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent / "data"

_BASE = "https://raw.githubusercontent.com/mcsorkun/AqSolDB/master/data"

#: The evaluation set, and the set to subtract from it.
EVALUATION = "dataset-I"
ESOL_TRAINING = "dataset-G"


def _read(name: str) -> list[dict]:
    request = urllib.request.Request(
        f"{_BASE}/{name}.csv", headers={"User-Agent": "openchem-solubility-benchmark"}
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        text = response.read().decode("utf-8", "replace")
    return list(csv.DictReader(io.StringIO(text)))


def main() -> int:
    OUT.mkdir(exist_ok=True)

    challenge = _read(EVALUATION)
    delaney = _read(ESOL_TRAINING)
    trained_keys = {row["InChIKey"] for row in delaney if row.get("InChIKey")}

    rows = []
    excluded = 0
    for row in challenge:
        value = (row.get("Solubility") or "").strip()
        if not value:
            continue
        if row.get("InChIKey") in trained_keys:
            excluded += 1
            continue
        rows.append(
            {
                "id": row.get("ID", ""),
                "name": row.get("Name", ""),
                "smiles": row.get("SMILES", ""),
                "inchikey": row.get("InChIKey", ""),
                "measured_logs": value,
            }
        )

    # Kept so the SC-2 set can be de-leaked with the same list rather
    # than a second, possibly different, download.
    (OUT / "esol_training_inchikeys.json").write_text(
        json.dumps(sorted(trained_keys)), encoding="utf-8"
    )

    with (OUT / "evaluation.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    (OUT / "manifest.json").write_text(
        json.dumps(
            {
                "evaluation_source": "Solubility Challenge (Llinas, Glen & Goodman 2008)",
                "source_version": f"AqSolDB {EVALUATION}, retrieved from mcsorkun/AqSolDB@master",
                "measured_unit": "logS (log mol/L)",
                # The Challenge measures the INTRINSIC solubility of the
                # neutral form, which is what the baseline model predicts
                # -- so this validates the baseline layer, not the pH one.
                "target_type": "intrinsic",
                "temperature_c": 25,
                "ph": None,
                # Not recorded per compound by the source. Stated rather
                # than guessed; see score.py, which refuses to derive a
                # free-form-only headline without it.
                "solid_form": "unknown",
                "rows": len(rows),
                "excluded_as_esol_training": excluded,
                # Model -> the sources it was fitted on, so score.py can
                # enforce the anti-leak rule without anybody remembering.
                "models_trained_on_this": ["aqsoldb"],
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"evaluation set     {len(rows)} compounds")
    print(f"excluded (in ESOL's own fit) {excluded}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
