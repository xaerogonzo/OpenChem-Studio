"""Hold the CNNaffinity ranking RESULT to the committed jsonl and summary."""

from __future__ import annotations

import json
import pathlib
import sys

_DIR = pathlib.Path(__file__).parents[1] / "benchmarks" / "docking"
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from cnn_affinity_core import (  # noqa: E402
    TRAINING_OVERLAP,
    RANKING_PDBS,
    bootstrap_interval,
    clustered_interval,
    deciding_pdbs,
    integration_eligible,
    median_of,
    n_series,
    paired_delta_rho,
    verdict,
)

ROOT = pathlib.Path(__file__).parents[1]
ART = ROOT / "benchmarks" / "docking" / "artifacts_cnn_affinity"
RESULT = ROOT / "benchmarks" / "docking" / "RESULT_CNN_AFFINITY.md"


def _rows() -> list[dict]:
    return [
        json.loads(line)
        for line in (ART / "results.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _tally(rows: list[dict]) -> dict:
    by_series: dict[str, list[dict]] = {}
    for row in rows:
        by_series.setdefault(row["series_id"], []).append(row)
    deciding_deltas: list[float] = []
    overlap_deltas: list[float] = []
    by_pdb: dict[str, list[float]] = {pdb: [] for pdb in deciding_pdbs()}
    dropped = 0
    for _series_id, ligands in sorted(by_series.items()):
        pdb = ligands[0]["pdb"]
        vina = [float(r["vina"]) for r in ligands if r.get("vina") is not None]
        cnn = [
            float(r["cnn_affinity"]) if r.get("cnn_affinity") is not None else None
            for r in ligands
            if r.get("vina") is not None
        ]
        pchembl = [float(r["pchembl"]) for r in ligands if r.get("vina") is not None]
        delta = paired_delta_rho(vina, cnn, pchembl)
        if delta is None:
            if pdb in RANKING_PDBS and pdb not in TRAINING_OVERLAP:
                dropped += 1
            continue
        if pdb in TRAINING_OVERLAP:
            overlap_deltas.append(delta)
        else:
            deciding_deltas.append(delta)
            by_pdb.setdefault(pdb, []).append(delta)
    n_deciding = n_series(deciding_pdbs())
    series_iv = bootstrap_interval(deciding_deltas)
    clustered = clustered_interval({k: v for k, v in by_pdb.items() if v})
    v = verdict(series_iv, dropped=dropped, n_deciding=n_deciding)
    return {
        "deciding_n": len(deciding_deltas),
        "overlap_n": len(overlap_deltas),
        "dropped": dropped,
        "median_delta": median_of(deciding_deltas) if deciding_deltas else None,
        "overlap_median": median_of(overlap_deltas) if overlap_deltas else None,
        "series_interval": list(series_iv) if series_iv else None,
        "clustered_interval": list(clustered) if clustered else None,
        "verdict": v,
        "integration_eligible": integration_eligible(v, clustered),
    }


def test_committed_summary_is_the_jsonl_tally_not_a_hand_count():
    rows = _rows()
    assert len(rows) == 833
    assert len({(r["series_id"], r["molecule_id"]) for r in rows}) == 833
    assert all(r.get("match") is True for r in rows)
    assert all(r.get("cnn_affinity") is not None for r in rows)
    got = _tally(rows)
    summary = json.loads((ART / "summary.json").read_text(encoding="utf-8"))
    for key in (
        "deciding_n",
        "overlap_n",
        "dropped",
        "median_delta",
        "series_interval",
        "clustered_interval",
        "verdict",
        "integration_eligible",
    ):
        assert summary[key] == got[key]
    assert summary["verdict"] == "HARMFUL"
    assert summary["deciding_n"] == 35
    assert summary["overlap_n"] == 42
    assert summary["dropped"] == 0
    assert summary["integration_eligible"] is False
    assert got["overlap_median"] == -0.09090909090909091
    text = RESULT.read_text(encoding="utf-8")
    assert "**Verdict by the preregistered rule: HARMFUL.**" in text
    assert "| 35 of 35 | −0.130 | series [−0.330, −0.014] |" in text
    assert "| 42 of 42 | −0.091 |" in text
