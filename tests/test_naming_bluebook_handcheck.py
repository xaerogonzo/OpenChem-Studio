"""`tools/naming_bluebook_handcheck.py`: how a hand check of the oracle becomes row statuses and a stop-rule verdict.

The check compares OPSIN's structure for a printed name with the structure the book draws. These tests exercise the arithmetic that turns those
verdicts into `ORACLE_*` statuses, on synthetic rows, because a wrong rule here silently decides which rows count toward every B1 number.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import naming_bluebook_handcheck as hc  # noqa: E402

RULES = {
    "stop": {"min_usable_rows": 300, "max_name_join_error": 0.05, "max_overall_structure_disagreement": 0.10, "max_rejected_stratum_share": 0.50},
    "stratum_failure": {"min_checked": 4, "min_disagreements": 2, "min_rate": 0.25},
}
SAMPLE = {"seed": 7, "per_chapter": 2, "per_feature": 3, "features": ["wrapped", "long_name"]}


def row(label: str, chapter: int = 6, risk=(), **features) -> dict:
    base = {"wrapped": False, "long_name": False}
    base.update(features)
    return {"label": label, "chapter": chapter, "features": base, "oracle_risk": list(risk)}


def verdict(cls="SAME", join_ok=True) -> dict:
    return {"class": cls, "join_ok": join_ok}


def test_a_row_belongs_to_its_chapter_and_to_each_feature_it_has():
    assert hc.strata_of(row("a", 6, wrapped=True)) == ["chapter:6", "feature:wrapped"]
    assert hc.strata_of(row("b", 2)) == ["chapter:2"]


def test_the_sample_is_seeded_stratified_and_never_repeats_a_row():
    rows = [row(f"r{i:03d}", chapter=1 + i % 3, wrapped=(i % 7 == 0), long_name=(i % 5 == 0)) for i in range(120)]
    labels = hc.draw_sample(rows, SAMPLE)
    assert len(labels) == len(set(labels)), "a row is drawn once"
    assert len(labels) <= 3 * SAMPLE["per_chapter"] + 2 * SAMPLE["per_feature"]
    by_label = {r["label"]: r for r in rows}
    for chapter in (1, 2, 3):
        assert sum(1 for label in labels if by_label[label]["chapter"] == chapter) >= SAMPLE["per_chapter"]
    for feature in SAMPLE["features"]:
        assert sum(1 for label in labels if by_label[label]["features"][feature]) >= SAMPLE["per_feature"]
    assert hc.draw_sample(rows, SAMPLE) == labels, "the same seed draws the same sample"
    assert hc.draw_sample(list(reversed(rows)), SAMPLE) == labels, "the draw does not depend on the order the rows arrive in"
    assert hc.draw_sample(rows, {**SAMPLE, "seed": 8}) != labels, "the seed is what decides"


def test_a_checked_row_that_agrees_is_validated_and_one_that_disagrees_or_misjoins_is_rejected():
    rows = [row("ok"), row("bad"), row("misjoined"), row("tautomer")]
    verdicts = {"ok": verdict(), "bad": verdict("DIFFERENT_STRUCTURE"), "misjoined": verdict(join_ok=False), "tautomer": verdict("DIFFERENT_TAUTOMER")}
    statuses = hc.evaluate(rows, verdicts, RULES)["statuses"]
    assert statuses["ok"] == hc.VALIDATED
    assert statuses["tautomer"] == hc.VALIDATED, "a different tautomer is the same compound: the round-trip gate already says so"
    assert statuses["bad"] == hc.REJECTED
    assert statuses["misjoined"] == hc.REJECTED


def test_a_charge_or_hydrogen_difference_is_a_disagreement_and_an_unreadable_drawing_is_not_counted():
    rows = [row("a"), row("b"), row("c")]
    result = hc.evaluate(rows, {"a": verdict("DIFFERENT_CHARGE_OR_H"), "b": verdict("UNREADABLE_DRAWING"), "c": verdict()}, RULES)
    assert result["statuses"]["a"] == hc.REJECTED
    assert result["summary"]["checked"] == 2 and result["summary"]["unreadable_drawings"] == 1
    assert result["summary"]["disagreements"] == 1
    assert result["statuses"]["b"] != hc.VALIDATED, "an unreadable drawing validates nothing"


def test_an_unchecked_row_is_accepted_only_when_every_stratum_it_is_in_had_enough_clean_checks():
    checked = [row(f"c{i}", 6, wrapped=True) for i in range(4)]
    rows = checked + [row("plain", 6), row("wrapped", 6, wrapped=True), row("other_chapter", 2), row("risky", 6, risk=["retained_name_only"])]
    verdicts = {f"c{i}": verdict() for i in range(4)}
    statuses = hc.evaluate(rows, verdicts, RULES)["statuses"]
    assert statuses["plain"] == hc.ACCEPTED
    assert statuses["wrapped"] == hc.ACCEPTED
    assert statuses["other_chapter"] == hc.UNCERTAIN, "chapter 2 was never checked, so it can be neither accepted nor failed"
    assert statuses["risky"] == hc.UNCERTAIN, "a risk flag keeps a row out of the counted set even in an accepted stratum"


def test_a_stratum_fails_only_on_both_a_count_and_a_rate():
    rows = [row(f"r{i}", 6) for i in range(20)]
    one_bad = {f"r{i}": verdict("DIFFERENT_STRUCTURE" if i == 0 else "SAME") for i in range(5)}
    result = hc.evaluate(rows, one_bad, RULES)
    assert not result["strata"]["chapter:6"]["failed"], "one bad row in five does not condemn a stratum"
    assert result["strata"]["chapter:6"]["accepted"]
    two_bad = {f"r{i}": verdict("DIFFERENT_STRUCTURE" if i < 2 else "SAME") for i in range(5)}
    failed = hc.evaluate(rows, two_bad, RULES)
    assert failed["strata"]["chapter:6"]["failed"]
    assert failed["statuses"]["r10"] == hc.REJECTED, "an UNCHECKED row in a failed stratum is rejected"
    small = hc.evaluate(rows, {"r0": verdict("DIFFERENT_STRUCTURE"), "r1": verdict("DIFFERENT_STRUCTURE"), "r2": verdict()}, RULES)
    assert not small["strata"]["chapter:6"]["failed"], "fewer than min_checked rows can neither fail nor be accepted"
    assert not small["strata"]["chapter:6"]["accepted"]


def test_the_stop_rules_abandon_b1_and_say_why():
    many = [row(f"r{i}", 1 + i % 3) for i in range(400)]
    clean = {f"r{i}": verdict() for i in range(60)}
    assert hc.evaluate(many, clean, RULES)["summary"]["b1_trusted"]

    few = hc.evaluate(many[:100], {f"r{i}": verdict() for i in range(60)}, RULES)["summary"]
    assert "fewer than 300 usable rows" in few["abandon_reasons"]

    misjoined = {f"r{i}": verdict(join_ok=(i % 10 != 0)) for i in range(60)}  # 10% join errors
    assert "name-join error over the stop rule" in hc.evaluate(many, misjoined, RULES)["summary"]["abandon_reasons"]

    disagreeing = {f"r{i}": verdict("DIFFERENT_STRUCTURE" if i % 5 == 0 else "SAME") for i in range(60)}  # 20%
    assert "OPSIN-vs-drawn disagreement over the stop rule" in hc.evaluate(many, disagreeing, RULES)["summary"]["abandon_reasons"]


def test_failed_strata_holding_most_of_the_rows_abandon_b1():
    rows = [row(f"r{i}", 6) for i in range(400)]
    verdicts = {f"r{i}": verdict("DIFFERENT_STRUCTURE" if i < 3 else "SAME") for i in range(8)}
    summary = hc.evaluate(rows, verdicts, RULES)["summary"]
    assert summary["rejected_share_of_eligible"] > 0.5
    assert "failed strata hold more than the allowed share of rows" in summary["abandon_reasons"]


def test_rates_are_none_not_zero_when_nothing_was_checked():
    summary = hc.evaluate([row("a")], {}, RULES)["summary"]
    assert summary["join_error_rate"] is None and summary["disagreement_rate"] is None


def test_one_disagreement_in_four_is_a_quarter_and_still_not_a_failed_stratum():
    """The rate alone (0.25) would fail it; the count rule (two disagreements) is what protects a small stratum from one bad row."""
    rows = [row(f"r{i}", 6) for i in range(20)]
    result = hc.evaluate(rows, {f"r{i}": verdict("DIFFERENT_STRUCTURE" if i == 0 else "SAME") for i in range(4)}, RULES)
    cell = result["strata"]["chapter:6"]
    assert cell["checked"] == 4 and cell["disagreements"] == 1
    assert not cell["failed"] and cell["accepted"]


def test_a_misjoined_name_counts_against_its_strata_like_a_structure_disagreement():
    """Two extraction errors in a stratum of five make it fail, so the unchecked rows that share its extraction shape are rejected."""
    rows = [row(f"r{i}", 6, wrapped=True) for i in range(20)]
    verdicts = {f"r{i}": verdict(join_ok=(i >= 2)) for i in range(5)}
    result = hc.evaluate(rows, verdicts, RULES)
    assert result["strata"]["feature:wrapped"]["failed"]
    assert result["statuses"]["r10"] == hc.REJECTED
