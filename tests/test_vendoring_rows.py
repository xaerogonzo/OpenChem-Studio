"""Every naming round from 34 on has its `VENDORING.md` row in the same pull request as its code.

The older rows cite the fork's merge commit and this repository's squash commit, which exist only after both pull requests merge, so each round needed a second,
documentation-only PR to record itself. From round 34 the row is a `| fork pull request |` row that cites PULL REQUEST NUMBERS (known when the PRs are opened),
written into the application PR (see VENDORING.md, "Recording a sync"). This test is what makes that a rule rather than a habit: a `naming round N` section in the vendor
CHANGELOG (N >= 34) without its row is a red test in the PR that adds the section.
"""
from __future__ import annotations

import re
from pathlib import Path

VENDOR = Path(__file__).resolve().parent.parent / "src" / "openchem" / "vendor"
FIRST_ROUND_BY_PULL_REQUEST = 34


def _rounds_in_changelog() -> list[int]:
    text = (VENDOR / "CHANGELOG.md").read_text(encoding="utf-8")
    rounds = {int(m.group(1)) for m in re.finditer(r"^## [0-9-]+ -- naming round (\d+)\b", text, re.MULTILINE)}
    return sorted(r for r in rounds if r >= FIRST_ROUND_BY_PULL_REQUEST)


def _pull_request_rows() -> list[str]:
    text = (VENDOR / "VENDORING.md").read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line.startswith("| fork pull request |")]


def test_every_round_from_34_has_a_row_that_cites_both_pull_requests():
    rows = _pull_request_rows()
    for n in _rounds_in_changelog():
        mine = [row for row in rows if re.search(rf"naming round {n}\b", row)]
        assert mine, (
            f"CHANGELOG.md has a 'naming round {n}' section and VENDORING.md has no '| fork pull request |' row for it. Add the row in THIS pull request "
            "(VENDORING.md, 'Recording a sync'): a second, docs-only PR to record a sync is what this rule exists to stop."
        )
        row = mine[0]
        assert re.search(r"open-iupac-namer#\d+", row), f"round {n}'s row does not cite the fork pull request as open-iupac-namer#<number>"
        assert re.search(r"this repository's pull request #\d+", row), f"round {n}'s row does not cite the application pull request as 'this repository's pull request #<number>'"


def test_the_rule_does_not_reach_back_to_rounds_that_were_recorded_by_commit():
    """Rounds before 34 keep their `| fork commit |` rows; the guard must not ask them for a pull-request row."""
    assert all(n >= FIRST_ROUND_BY_PULL_REQUEST for n in _rounds_in_changelog())


def test_the_guard_can_fail():
    """Mutation guard: the parser finds a round heading and a row of the documented shape, so a missing row is a failure and not an empty loop."""
    sample_changelog = "## 2026-10-10 -- naming round 34: something\n"
    assert re.findall(r"^## [0-9-]+ -- naming round (\d+)\b", sample_changelog, re.MULTILINE) == ["34"]
    sample_row = ("| fork pull request | xaerogonzo/open-iupac-namer#34 — synced 2026-10-10, corresponding to this repository's pull request #267 "
                  "(`branch`, base `abc`): naming round 34, x. |")
    assert re.search(r"naming round 34\b", sample_row) and re.search(r"open-iupac-namer#\d+", sample_row) and re.search(r"this repository's pull request #\d+", sample_row)
