"""Step 1 of 2: download a public aqueous-solubility set to score against.

Same throwaway-environment recipe as `benchmarks/admet/fetch_tdc.py`, and
for the same reason -- PyTDC pins `rdkit-pypi` and has no business in
either this project or the ADMET sidecar:

    uv venv tdcenv --python 3.11
    uv pip install --python tdcenv/Scripts/python.exe "PyTDC==0.4.1" "setuptools<81"
    tdcenv/Scripts/python.exe fetch.py

**THE DATASET IS AqSolDB, AND THAT IS A PROBLEM FOR EXACTLY ONE MODEL.**
It is the set the ADMET sidecar's `Solubility_AqSolDB` head was TRAINED
on, so scoring that model here measures memorisation, not skill -- the
same circularity already recorded for nmrshiftdb2 in the NMR work.
`score.py` refuses to report it as a headline for that reason and says so
in the output rather than quietly omitting it. ESOL has no such
relationship to this data: it is a four-term regression published in 2004
with fixed coefficients, so the set is a genuine held-out test for it.

Writes `data/`, which is NOT committed.
"""

from __future__ import annotations

import json
from pathlib import Path

from tdc.single_pred import ADME

OUT = Path("data")

#: Written into the manifest so `score.py` can enforce the anti-leak rule
#: without anybody having to remember it.
DATASET = "Solubility_AqSolDB"
TRAINED_ON = {"aqsoldb": ("Solubility_AqSolDB",)}


def main() -> int:
    OUT.mkdir(exist_ok=True)
    data = ADME(name=DATASET, path=str(OUT / "raw"))
    split = data.get_split()

    rows = 0
    for part in ("train", "valid", "test"):
        frame = split[part]
        frame.to_csv(OUT / f"{DATASET}__{part}.csv", index=False)
        rows += len(frame)
        print(f"  {part:6} {len(frame):>6} rows")

    (OUT / "manifest.json").write_text(
        json.dumps(
            {
                "evaluation_source": DATASET,
                "source_version": "TDC ADME, PyTDC 0.4.1",
                "measured_unit": "logS (log mol/L)",
                # AqSolDB reports aqueous solubility of the compound as
                # supplied at unstated pH and temperature. That is NOT the
                # same quantity as a thermodynamic intrinsic solubility,
                # and score.py treats every row accordingly.
                "target_type": "intrinsic",
                "temperature_c": None,
                "ph": None,
                "solid_form": "unknown",
                "rows": rows,
                "models_trained_on_this": list(TRAINED_ON),
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"wrote {OUT}/ ({rows} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
