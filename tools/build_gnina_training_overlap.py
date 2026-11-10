"""Intersect CrossDocked2020 set-ids with the docking catalog.

The index file stays off-repo (default `D:/_scratch/gnina/crossdocked_set_ids.txt`).
Prints catalog hits for comparison with `gnina_core.TRAINING_OVERLAP`.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "benchmarks" / "docking"))

import gnina_core as core  # noqa: E402

DEFAULT_IDS = pathlib.Path("D:/_scratch/gnina/crossdocked_set_ids.txt")
SURVEY = pathlib.Path(__file__).resolve().parents[1] / "benchmarks" / "docking" / "artifacts_prep_box" / "results.jsonl"


def main() -> None:
    path = pathlib.Path(os.environ.get("OPENCHEM_CROSSDOCKED_IDS", DEFAULT_IDS))
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    ids = core.parse_crossdocked_pdb_ids(data.decode("utf-8", "replace"))
    rows = [json.loads(line) for line in SURVEY.read_text(encoding="utf-8").splitlines() if line.strip()]
    meas = {r["pdb"] for r in rows if r.get("arm") == "app" and not str(r.get("outcome", "")).startswith("setup")}
    hit = frozenset(meas & ids)
    print(
        json.dumps(
            {
                "path": str(path),
                "sha256": digest,
                "n_index": len(ids),
                "n_catalog": len(meas),
                "overlap": sorted(hit),
                "n_overlap": len(hit),
                "matches_core": hit == core.TRAINING_OVERLAP,
                "sha_matches_core": digest == core.CROSSDOCKED_SET_IDS_SHA256,
                "count_matches_core": len(ids) == core.CROSSDOCKED_UNIQUE_PDB_COUNT,
            },
            indent=2,
        )
    )
    if hit != core.TRAINING_OVERLAP or digest != core.CROSSDOCKED_SET_IDS_SHA256:
        raise SystemExit("overlap or hash does not match gnina_core.py")


if __name__ == "__main__":
    main()
