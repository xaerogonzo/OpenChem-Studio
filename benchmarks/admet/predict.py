"""Step 2 of 3: run the real ADMET sidecar over every TDC molecule.

Executed BY THE SIDECAR'S OWN INTERPRETER, not this project's -- it is the
one that has admet_ai. `_config.admet_interpreter()` reports the path the
app is configured with, so:

    ADMET=$(uv run --no-sync python -c "import sys;sys.path.insert(0,'../docking');from _config import admet_interpreter as a;print(a())")
    "$ADMET" predict.py test
    "$ADMET" predict.py train

WHY IT PREDICTS EVERYTHING AT ONCE. Loading the ensemble costs a couple of
minutes; predicting is sub-second per molecule after that. The app pays
that load per calculation because a user runs one molecule occasionally
(see `chem/admet_runner.py`), but 22 datasets would be 22 loads for no
reason. One pass over ~14k molecules takes about two minutes total.

Writes predictions_<split>.csv, indexed by SMILES, carrying the 52
non-percentile columns. Scoring is a separate step so that a scoring bug
costs seconds instead of a re-run.
"""

from __future__ import annotations

import contextlib
import csv
import random
import sys
from pathlib import Path

DATA = Path("tdc_data")

#: The leakage check needs enough train molecules to estimate performance,
#: not all 65,000 of them.
TRAIN_SAMPLE = 600


def _collect(split: str) -> list[str]:
    suffix = "__test.csv" if split == "test" else "__trainval.csv"
    smiles: set[str] = set()
    for path in sorted(DATA.glob(f"*{suffix}")):
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        if split != "test" and len(rows) > TRAIN_SAMPLE:
            # Seeded so a re-run scores the same molecules; score.py reads
            # this same file back rather than re-sampling.
            rows = random.Random(0).sample(rows, TRAIN_SAMPLE)
            sample_path = DATA / path.name.replace("__trainval", "__trainsample")
            with sample_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        smiles.update(str(row["Drug"]) for row in rows)
    return sorted(smiles)


def main(argv: list[str]) -> int:
    split = argv[1] if len(argv) > 1 else "test"
    smiles = _collect(split)
    print(f"{len(smiles)} unique SMILES across the {split} splits", flush=True)

    # The model's progress bars go to stdout and would land mid-CSV; the
    # same reason `chem/admet_runner.py` redirects them.
    with contextlib.redirect_stdout(sys.stderr):
        from admet_ai import ADMETModel

        frame = ADMETModel().predict(smiles=smiles)

    keep = [c for c in frame.columns if not c.endswith("_drugbank_approved_percentile")]
    frame[keep].to_csv(f"predictions_{split}.csv", index_label="smiles")
    print(f"wrote predictions_{split}.csv  {frame.shape[0]} rows x {len(keep)} cols")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
