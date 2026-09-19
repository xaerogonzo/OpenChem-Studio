"""The retained-name registry's fields are claims, and the claims are checked.

`vendor/data/retained_names_expanded.json` began as `retained_pins`, a table
whose NAME asserted PIN status for 292 names while 161 of them had been
harvested from OPSIN's parsing dictionary -- "OPSIN can read it" recorded as
"IUPAC prefers it" (naming round 3). Round 4 adds what a generator needs to
use an entry as a PARENT, and each field is typed so a claim cannot outrun
its evidence:

    pin_status            PIN / RETAINED_NOT_PIN / absent (= unaudited)
    evidence_kind         NORMATIVE_RULE / ABSENT_FROM_SOURCE / STRUCTURE_PARSE_ONLY
    evidence_source, rule_id
    may_be_parent, may_be_substituted, substitution_scope, whole_molecule_only

`tools/retained_name_audit.validate` fails closed on impossible combinations.
These tests hold the registry to it, prove each rule fires, and tie the
assembler's substitutable-parent table to the data it must agree with.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import retained_name_audit as audit  # noqa: E402

from openchem.vendor.iupac_namer import assembly  # noqa: E402
from openchem.vendor.iupac_namer.types import OutputForm  # noqa: E402


@pytest.fixture(scope="module")
def registry() -> dict:
    return audit.registry()


def test_the_registry_validates(registry):
    assert audit.validate(registry) == []


def test_every_partition_sums_to_the_total(registry):
    for field, counts in audit.partitions(registry).items():
        assert sum(counts.values()) == len(registry), field


BB = "BLUEBOOK_2013_CORRECTED_2022"


@pytest.mark.parametrize("entry,why", [
    ({"name": "x", "pin_status": "PIN", "evidence_kind": "STRUCTURE_PARSE_ONLY"},
     "a PIN backed only by a parser"),
    ({"name": "x", "may_be_parent": True, "evidence_kind": "STRUCTURE_PARSE_ONLY"},
     "a parent backed only by a parser"),
    ({"name": "x", "pin_status": "PIN", "evidence_kind": "ABSENT_FROM_SOURCE",
      "evidence_source": BB}, "absence of evidence supporting a PIN"),
    ({"name": "x", "pin_status": "PIN", "evidence_kind": "NORMATIVE_RULE"},
     "a normative claim with no rule or source"),
    ({"name": "x", "pin_status": "PIN", "evidence_kind": "NORMATIVE_RULE", "rule_id": "P-1",
      "evidence_source": BB, "whole_molecule_only": True, "may_be_parent": True},
     "whole-molecule-only and a parent at once"),
    ({"name": "x", "may_be_substituted": True, "may_be_parent": False},
     "substitutable without being a parent"),
    ({"name": "x", "pin_status": "PREFERRED"}, "an undeclared status"),
])
def test_each_rule_fires(entry, why):
    """Mutation check, one rule per row: each broken entry must be refused."""
    assert audit.validate({"C": entry}), why


def _tail_replacements(table) -> set[str]:
    return {replacement for (_base, form), (_pattern, replacement) in table.items()
            if form == OutputForm.STANDALONE}


def test_every_substituted_retained_parent_the_assembler_emits_is_licensed(registry):
    """The assembler rewrites a substituted benzene/ethane tail to a retained
    name. Every such name that the registry also holds must be licensed there
    as a substitutable parent -- otherwise the code and the data disagree about
    what the book allows, which is how `retained_pins` went wrong."""
    by_name = {entry["name"]: entry for entry in registry.values()}
    emitted = (_tail_replacements(assembly._BENZENE_RETAINED_TAIL)
               | _tail_replacements(assembly._ETHANE_RETAINED_TAIL))
    unlicensed = sorted(
        name for name in emitted
        if name in by_name and not by_name[name].get("may_be_substituted")
    )
    assert not unlicensed, unlicensed


def test_a_whole_molecule_only_name_is_never_emitted_as_a_substituted_parent(registry):
    """anisole ('no substitution on anisole for PINs') and toluene ('not
    freely substitutable') must never appear in the rewrite tables."""
    emitted = (_tail_replacements(assembly._BENZENE_RETAINED_TAIL)
               | _tail_replacements(assembly._ETHANE_RETAINED_TAIL))
    forbidden = {entry["name"] for entry in registry.values() if entry.get("whole_molecule_only")}
    assert not (emitted & forbidden), emitted & forbidden
