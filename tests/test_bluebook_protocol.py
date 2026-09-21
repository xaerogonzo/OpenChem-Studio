"""The Blue Book harvest's protocol is a committed contract with numbers in it, not a description.

`benchmarks/naming/bluebook_protocol.toml` holds every threshold that decides whether B1 is trusted, abandoned or reported with a caveat, and it
is committed BEFORE any harvested row is looked at. The point of that ordering is that a stop rule chosen after seeing the rows is a stop rule
chosen to fit them. These tests keep the file well-formed and, once the harvest exists, tie its output to the exact protocol it was run under.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "benchmarks" / "naming" / "bluebook_protocol.toml"
HARVEST_META = ROOT / "benchmarks" / "naming" / "bluebook_tuning.meta.json"


def protocol_bytes() -> bytes:
    """LF text, because that is what git stores and the harvest hashed; a Windows checkout is CRLF under autocrlf."""
    return PROTOCOL.read_bytes().replace(b"\r\n", b"\n")


def protocol_sha256() -> str:
    return hashlib.sha256(protocol_bytes()).hexdigest()


def load() -> dict:
    return tomllib.loads(protocol_bytes().decode("utf-8"))


def test_every_stop_rule_is_a_number_in_a_sensible_range():
    stop = load()["stop"]
    assert isinstance(stop["min_usable_rows"], int) and stop["min_usable_rows"] >= 100
    for key in ("max_name_join_error", "max_overall_structure_disagreement", "max_rejected_stratum_share"):
        assert isinstance(stop[key], float) and 0 < stop[key] < 1, key


def test_the_stratum_failure_rule_needs_both_a_count_and_a_rate():
    """One bad row in a small stratum must not condemn it, and a large stratum with a low rate must not be condemned by two rows."""
    rule = load()["stratum_failure"]
    assert rule["min_checked"] >= 3 and rule["min_disagreements"] >= 2
    assert isinstance(rule["min_rate"], float) and 0 < rule["min_rate"] < 1
    assert rule["min_disagreements"] <= rule["min_checked"]


def test_the_sample_is_seeded_and_covers_every_declared_feature():
    sample = load()["sample"]
    assert isinstance(sample["seed"], int)
    assert sample["per_chapter"] >= 1 and sample["per_feature"] >= 1
    assert sample["features"] and len(set(sample["features"])) == len(sample["features"])
    # about 60 hand-checked rows: ten chapters times per_chapter plus the features times per_feature, before overlap
    planned = 10 * sample["per_chapter"] + len(sample["features"]) * sample["per_feature"]
    assert 50 <= planned <= 90, planned


def test_each_scope_filter_is_a_distinct_named_reason():
    reasons = load()["filters"]["reasons"]
    assert len(reasons) == len(set(reasons))
    assert {"opsin_unparsable", "opsin_ambiguous", "page_or_column_split", "stereodescriptor"} <= set(reasons)


def test_only_validated_and_stratum_accepted_rows_may_count():
    counting = set(load()["statuses"]["counts_toward_engine_scores"])
    assert counting == {"ORACLE_VALIDATED", "ORACLE_STRATUM_ACCEPTED"}
    assert not {"ORACLE_UNCERTAIN", "ORACLE_REJECTED"} & counting


def test_the_protocol_names_its_source_and_tag():
    protocol = load()["protocol"]
    assert protocol["source_file"] == "BlueBookV2.pdf" and protocol["tag"] == "(PIN)"
    assert protocol["version"] == 1


@pytest.mark.skipif(not HARVEST_META.exists(), reason="the harvest has not been run yet")
def test_the_harvest_was_run_under_exactly_this_protocol():
    """If either moves after the other was recorded, the round's thresholds were chosen after the rows: fail."""
    meta = json.loads(HARVEST_META.read_text(encoding="utf-8"))
    assert meta["protocol_sha256"] == protocol_sha256(), "the protocol changed after the harvest was run"


def test_the_committed_numbers_are_the_ones_written_down_before_the_harvest():
    """A COPY of the thresholds, on purpose. Changing a stop rule now means editing this test as well, in the same commit, where a reviewer
    sees it: the range checks above would let 0.05 quietly become 0.9. Once the harvest has run, `protocol_sha256` in its meta closes the
    same door from the other side."""
    protocol = load()
    assert protocol["stop"] == {
        "min_usable_rows": 300,
        "max_name_join_error": 0.05,
        "max_overall_structure_disagreement": 0.10,
        "max_rejected_stratum_share": 0.50,
    }
    assert protocol["stratum_failure"] == {"min_checked": 4, "min_disagreements": 2, "min_rate": 0.25}
    assert protocol["sample"]["seed"] == 20260921
    assert protocol["sample"]["per_chapter"] == 3 and protocol["sample"]["per_feature"] == 6
