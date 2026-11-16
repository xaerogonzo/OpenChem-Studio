"""WS5 P3: NL-105 — six ``adjudication.toml`` rows whose engine name is not the PIN.

Programme disposition (2026-11-15): **closed** without moving ``fix_status`` to FIXED: each row's
``engine_name`` is re-measured on the current namer, OPSIN round-trips, and the adjudicated
``preferred_name`` stays documented as the book target.
"""

from __future__ import annotations

import shutil
import tomllib
from pathlib import Path

import pytest
from rdkit import Chem, RDLogger
from rdkit.Chem import inchi

from openchem.vendor.iupac_namer import name_smiles

RDLogger.DisableLog("rdApp.*")

ADJ = Path(__file__).resolve().parents[1] / "benchmarks" / "naming" / "adjudication.toml"

needs_opsin = pytest.mark.skipif(shutil.which("java") is None, reason="needs java on PATH (OPSIN read-back)")

# corpus_row_id or case_origin key used to fetch the row
NL105_LOOKUPS: tuple[tuple[str, str], ...] = (
    ("corpus_row_id", "h2cid2500"),
    ("corpus_row_id", "h2cid30500"),
    ("smiles", "C[N+]([O-])=C(C)C"),
    ("smiles", "C[Se][Se]C"),
    ("smiles", "CC(C)(C)OC(=O)NCC(=O)O"),
    ("corpus_row_id", "h4cid4750"),
)


def _rows() -> list[dict]:
    table = tomllib.loads(ADJ.read_text(encoding="utf-8"))
    return list(table["row"])


def _row_by_corpus(corpus_row_id: str) -> dict:
    for row in _rows():
        if row.get("corpus_row_id") == corpus_row_id:
            return row
    raise KeyError(corpus_row_id)


def _row_by_smiles(smiles: str) -> dict:
    for row in _rows():
        if row.get("smiles") == smiles:
            return row
    raise KeyError(smiles)


def _resolve(lookup: tuple[str, str]) -> dict:
    kind, key = lookup
    if kind == "corpus_row_id":
        return _row_by_corpus(key)
    return _row_by_smiles(key)


@pytest.mark.parametrize("lookup", NL105_LOOKUPS, ids=[f[1] for f in NL105_LOOKUPS])
def test_nl105_row_still_open_in_adjudication(lookup):
    row = _resolve(lookup)
    assert row["fix_status"] in ("OPEN", "PARTLY_FIXED"), row.get("corpus_row_id") or lookup[1]
    assert row["verdict"] in ("ENGINE_WRONG", "BOTH_NOT_PREFERRED")


@pytest.mark.parametrize("lookup", NL105_LOOKUPS, ids=[f[1] for f in NL105_LOOKUPS])
def test_nl105_engine_name_matches_current_namer(lookup):
    row = _resolve(lookup)
    smile = row["smiles"]
    documented = row["engine_name"]
    measured = name_smiles(smile)
    assert measured == documented, (lookup, measured, documented)


@needs_opsin
@pytest.mark.parametrize("lookup", NL105_LOOKUPS, ids=[f[1] for f in NL105_LOOKUPS])
def test_nl105_documented_engine_name_round_trips(lookup):
    from py2opsin import py2opsin

    row = _resolve(lookup)
    smile = row["smiles"]
    documented = row["engine_name"]
    back = py2opsin(documented)
    assert back, (lookup, documented)
    assert inchi.MolToInchiKey(Chem.MolFromSmiles(back)) == inchi.MolToInchiKey(
        Chem.MolFromSmiles(smile)
    )