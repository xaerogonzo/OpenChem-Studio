"""NL-106 (WS3): adjudication rows that stay ``UNDECIDED`` (legal WS3 outcome).

Pins the five open ``UNDECIDED`` rows in ``benchmarks/naming/adjudication.toml`` and
records that sources do not force a unique PIN (trans-decalin, diazepam P-58.2, fusion /
von Baeyer splits). Re-measured on the current engine name where applicable.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from openchem.vendor.iupac_namer import name_smiles

ADJ = Path(__file__).resolve().parents[1] / "benchmarks" / "naming" / "adjudication.toml"

UNDECIDED_IDS = (
    "trans-decalin",
    "diazepam",
    "h2cid3500",
    "h2cid10500",
    "h2cid16500",
)


def _undecided_by_corpus_id() -> dict[str, dict]:
    table = tomllib.loads(ADJ.read_text(encoding="utf-8"))
    return {
        r["corpus_row_id"]: r
        for r in table["row"]
        if r.get("verdict") == "UNDECIDED" and r.get("corpus_row_id")
    }


def test_nl106_five_undecided_rows_are_still_open():
    by_id = _undecided_by_corpus_id()
    for cid in UNDECIDED_IDS:
        assert cid in by_id, cid
        assert by_id[cid]["fix_status"] == "OPEN"


def test_nl106_trans_decalin_engine_name_unchanged():
    row = next(r for r in tomllib.loads(ADJ.read_text(encoding="utf-8"))["row"] if r.get("corpus_row_id") == "trans-decalin")
    assert name_smiles(row["smiles"]) == row["engine_name"] == "trans-decalin"


def test_nl106_diazepam_engine_name_unchanged():
    row = next(r for r in tomllib.loads(ADJ.read_text(encoding="utf-8"))["row"] if r.get("corpus_row_id") == "diazepam")
    assert name_smiles(row["smiles"]) == row["engine_name"]