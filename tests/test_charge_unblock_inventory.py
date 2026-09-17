"""The charge-model unblock inventory (TRIAGE section 5) keeps its shape.

`benchmarks/charges/models/unblock_inventory.csv` records, per failed or partial charge model, what
would change its status. This checks the STRUCTURE only: the columns, the fixed vocabularies, and the
consistency rules between fields. It reads no prose for meaning and needs no network; the facts in the
rows were verified when they were written, and TRIAGE section 5 says how.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import pytest

INVENTORY = Path(__file__).resolve().parent.parent / "benchmarks" / "charges" / "models" / "unblock_inventory.csv"

COLUMNS = [
    "row_kind", "item", "family", "g1_status", "g2_status", "failure_mode", "evidence_state",
    "primary_blocker", "secondary_prerequisites", "evidence_roles_needed", "concrete_route",
    "would_change_status", "would_not_change_status", "owner", "install_required", "cost",
    "worth_chasing", "g2_oracle_options", "terminal_reason", "reopen_condition", "evidence_pointer",
]
VOCABULARY = {
    "row_kind": {"failure", "extension"},
    "family": {"G1", "G2", "both"},
    "g1_status": {"REPRODUCED", "SHIPPED", "PARTIAL", "INCONCLUSIVE", "HOLD", "BLOCKED", "NO", "UNEXPLAINED",
                  "NOT-ASSESSED", "n/a"},
    "g2_status": {"CANDIDATE", "NOT-ASSESSED", "n/a"},
    "evidence_state": {"AVAILABLE-UNASSESSED", "AVAILABLE-PARTIAL", "MISSING", "TERMINAL", "RESOLVED"},
    "primary_blocker": {"source", "data", "tool", "decision", "none-terminal", "none-resolved"},
    "owner": {"me", "alex", "none"},
    "install_required": {"yes", "no"},
    "cost": {"low", "medium", "high"},
    "worth_chasing": {"yes", "no", "g2-only"},
}
EVIDENCE_ROLES = {"equation", "parameter", "implementation", "structures", "charge-oracle"}
#: A reference to ChargeFW2 is only an identity with a commit beside it: the repository is maintained,
#: so its parameter files and sources move.
CHARGEFW2_COMMIT = re.compile(r"ChargeFW2 [0-9a-f]{40}\b")


def _rows() -> list[dict[str, str]]:
    with INVENTORY.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == COLUMNS, f"columns changed: {reader.fieldnames}"
        return list(reader)


def test_the_inventory_has_rows_to_check():
    """Asserted so that every per-row check below cannot pass by finding nothing."""
    rows = _rows()
    assert len(rows) >= 10
    assert {r["row_kind"] for r in rows} == {"failure", "extension"}


@pytest.mark.parametrize("row", _rows(), ids=lambda r: r["item"][:40])
def test_each_row_keeps_its_vocabulary_and_consistency(row):
    item = row["item"]
    assert item.strip() and row["failure_mode"].strip() and row["evidence_pointer"].strip(), item
    for field, allowed in VOCABULARY.items():
        assert row[field] in allowed, f"{item}: {field} = {row[field]!r}, not one of {sorted(allowed)}"

    roles = row["evidence_roles_needed"].split(";")
    assert roles and set(roles) <= EVIDENCE_ROLES, f"{item}: evidence roles {roles}"

    # TERMINAL means exactly that nothing blocks except the record itself, and it says when to reopen.
    terminal = row["evidence_state"] == "TERMINAL"
    assert terminal == (row["primary_blocker"] == "none-terminal"), f"{item}: TERMINAL and none-terminal disagree"
    if terminal:
        assert row["terminal_reason"].strip() and row["reopen_condition"].strip(), f"{item}: TERMINAL without reason or reopening condition"
        assert row["worth_chasing"] == "no", f"{item}: a terminal row cannot be worth chasing"
    else:
        assert not row["terminal_reason"] and not row["reopen_condition"], f"{item}: terminal fields on a live row"
    # RESOLVED means the question was answered: nothing blocks and nothing is left to chase.
    resolved = row["evidence_state"] == "RESOLVED"
    assert resolved == (row["primary_blocker"] == "none-resolved"), f"{item}: RESOLVED and none-resolved disagree"
    if resolved:
        assert row["worth_chasing"] == "no" and row["owner"] == "none", f"{item}: a resolved row still has work"

    # A G2 row must say how it would be judged, or that the oracle is not yet selected.
    if row["family"] in {"G2", "both"}:
        assert row["g2_status"] != "n/a", f"{item}: a G2 row with no G2 status"
        assert row["g2_oracle_options"].strip(), f"{item}: a G2 row with no oracle options"
    else:
        assert row["g2_status"] == "n/a" and row["worth_chasing"] != "g2-only", f"{item}: G2 fields on a G1-only row"

    # A bare mention is allowed only where the same row pins the commit somewhere.
    if "ChargeFW2" in " ".join(row.values()):
        assert CHARGEFW2_COMMIT.search(row["evidence_pointer"]), f"{item}: ChargeFW2 cited without a pinned commit in evidence_pointer"


def test_items_are_unique():
    items = [r["item"] for r in _rows()]
    assert len(items) == len(set(items))
