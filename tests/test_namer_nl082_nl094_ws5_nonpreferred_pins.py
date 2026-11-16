"""WS5 P3: NL-082..NL-084, NL-091, NL-094 — non-preferred or deliberate deviations that round-trip.

Programme disposition (2026-11-15): **closed** without pursuing Blue Book PINs. NL-083 adjudication
rows keep ``fix_status`` OPEN. NL-094 documents the P-44.1.2 tier rule with an agreeing example;
no corpus molecule disagrees with P-44.2.1 (``KNOWN_LIMITATIONS.md``, ranking row).
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

PINS = [
    (
        "NL-082 PEG diacid substituent chain",
        "O=C(O)COCCOCCOCCOCC(=O)O",
        "(2-{2-[2-(carboxymethoxy)ethoxy]ethoxy}ethoxy)acetic acid",
    ),
    (
        "NL-084 chalcogen terminal chain",
        "CSOSC",
        "{[(methylsulfanyl)oxy]sulfanyl}methane",
    ),
    (
        "NL-084 cyclic trimethylsiloxane",
        "C1[Si](C)(C)O[Si](C)(C)O[Si](C)(C)O1",
        "2,2,4,4,6,6-hexamethyl-1,3,5,2,4,6-trioxatrisilepane",
    ),
    (
        "NL-091 pyrene retained parent",
        "c1cc2ccc3cccc4ccc(c1)c2c34",
        "pyrene",
    ),
    (
        "NL-091 interior CAS letters 10b/10c",
        "O=C1CC2=NC=CC3=CC=C4CCCC1C4C32",
        "6,8,8a,10,10b,10c-hexahydronaphtho[2,1,8-def]quinolin-9(7H)-one",
    ),
    (
        "NL-094 pyridine parent when N is senior to Si",
        "C[Si](C)(C)c1ccccn1",
        "2-(trimethylsilyl)pyridine",
    ),
]

NL083_LOOKUPS = (
    ("corpus_row_id", "carbon disulfide"),
    ("smiles", "CN=C=NC"),
)


def _adjudication_rows() -> list[dict]:
    return tomllib.loads(ADJ.read_text(encoding="utf-8"))["row"]


def _row(lookup: tuple[str, str]) -> dict:
    kind, key = lookup
    for row in _adjudication_rows():
        if kind == "corpus_row_id" and row.get("corpus_row_id") == key:
            return row
        if kind == "smiles" and row.get("smiles") == key:
            return row
    raise KeyError(key)


@pytest.mark.parametrize("label,smiles,expected", PINS, ids=[p[0] for p in PINS])
def test_engine_keeps_documented_name(label, smiles, expected):
    del label
    assert name_smiles(smiles) == expected


@needs_opsin
@pytest.mark.parametrize("label,smiles,expected", PINS, ids=[p[0] for p in PINS])
def test_documented_name_round_trips(label, smiles, expected):
    del label
    from py2opsin import py2opsin

    back = py2opsin(expected)
    assert back, (smiles, expected)
    assert inchi.MolToInchiKey(Chem.MolFromSmiles(back)) == inchi.MolToInchiKey(
        Chem.MolFromSmiles(smiles)
    )


@pytest.mark.parametrize("lookup", NL083_LOOKUPS, ids=[f[1] for f in NL083_LOOKUPS])
def test_nl083_adjudication_row_open(lookup):
    row = _row(lookup)
    assert row["fix_status"] == "OPEN"
    assert row["verdict"] == "ENGINE_WRONG"


@pytest.mark.parametrize("lookup", NL083_LOOKUPS, ids=[f[1] for f in NL083_LOOKUPS])
def test_nl083_engine_name(lookup):
    row = _row(lookup)
    assert name_smiles(row["smiles"]) == row["engine_name"]