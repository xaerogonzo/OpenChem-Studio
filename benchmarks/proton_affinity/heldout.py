"""The held-out size panel of the proton-affinity benchmark (`PREREGISTRATION_HELDOUT.md`).

Six neutral bases of 11 to 20 heavy atoms, chosen by chemistry, with Hunter-Lias values from the NIST WebBook fetched afterwards (`heldout_values.json`). The original 28 stay in `nist_values.json`. Nothing here runs ORCA.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
VALUES = HERE / "heldout_values.json"
FIRST_RUN = HERE / "nist_values.json"

#: More missing deciding bases than this is NOT EVALUABLE on this arm. The original 28-base arm allows 2 of 21; this arm allows 1 of 6.
MISSING_ALLOWED = 1
MIN_HEAVY = 11
MAX_HEAVY = 20
SUPPORTED_ELEMENTS = frozenset({"H", "C", "N", "O", "P", "S"})


def document() -> dict:
    return json.loads(VALUES.read_text(encoding="utf-8"))


def bases() -> list[dict]:
    return document()["bases"]


def smiles() -> dict[str, str]:
    return {row["name"]: row["smiles"] for row in bases()}


def first_run_names() -> set[str]:
    return {row["name"] for row in json.loads(FIRST_RUN.read_text(encoding="utf-8"))["bases"]}
