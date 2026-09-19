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


# --- The OPSIN gate (naming round 5, N5) ------------------------------------
#
# A name whose RECORD came from OPSIN's parse dictionary is emitted only with
# NORMATIVE_RULE evidence. "fluorouracil" and "tabun" were reaching the output
# as whole-molecule names on nothing but a parser's ability to read them.

from openchem.vendor.iupac_namer import name_smiles  # noqa: E402
from openchem.vendor.iupac_namer.data_loader import (  # noqa: E402
    OPSIN_REGISTRY_SOURCES,
    OPSIN_VOCABULARY_TABLE,
    get_retained_names_from_opsin,
    lookup_retained_name,
)
from openchem.vendor.iupac_namer.engine import retained_gate_refusal  # noqa: E402
from openchem.vendor.iupac_namer.strategy import default_strategy  # noqa: E402


def _record(smiles: str, entry: dict) -> dict:
    return {"smiles": smiles, **entry, "table": "retained_pins"}


def test_every_untyped_opsin_sourced_registry_entry_is_refused(registry):
    strategy = default_strategy()
    untyped = [(s, e) for s, e in registry.items()
               if e.get("source") in OPSIN_REGISTRY_SOURCES
               and e.get("evidence_kind") != "NORMATIVE_RULE"]
    assert len(untyped) > 150  # the population the gate exists for
    for smiles, entry in untyped:
        assert retained_gate_refusal(_record(smiles, entry), strategy) is not None, entry["name"]


def test_every_standalone_vocabulary_name_is_refused():
    strategy = default_strategy()
    refused = [retained_gate_refusal({**e, "table": OPSIN_VOCABULARY_TABLE}, strategy)
               for e in get_retained_names_from_opsin()]
    assert None not in refused
    assert "OPSIN_VOCABULARY_UNTYPED" in refused


def test_book_evidence_opens_the_gate():
    """The gate asks for evidence, not for a different source string."""
    typed = {"name": "x", "source": "opsin", "pin_status": "PIN",
             "evidence_kind": "NORMATIVE_RULE", "rule_id": "P-0", "evidence_source": BB}
    assert retained_gate_refusal(_record("C", typed), default_strategy()) is None


def test_the_gate_is_not_a_lexical_blacklist():
    """The same SPELLING from a record without OPSIN provenance passes: the
    rule is about where a record came from. And azepane's SMILES carries
    OPSIN's 'hexamethyleneimine' in the registry, yet the curated table's
    'azepane' is untouched, because the registry row is matched by name too."""
    strategy = default_strategy()
    curated = {"smiles": "X", "name": "fluorouracil", "table": "ring_curated"}
    assert retained_gate_refusal(curated, strategy) is None
    azepane = lookup_retained_name("C1CCCNCC1")
    assert azepane["name"] == "azepane"
    assert retained_gate_refusal(azepane, strategy) is None


@pytest.mark.parametrize("smiles,refused_name", [
    ("O=c1[nH]cc(F)c(=O)[nH]1", "fluorouracil"),
    ("CCOP(=O)(C#N)N(C)C", "tabun"),
    ("OCCN(CCO)CCO", "triethanolamine"),
    ("Nc1ncnc2[nH]cnc12", "adenine"),
])
def test_a_gated_name_never_reaches_the_output(smiles, refused_name):
    assert refused_name not in name_smiles(smiles)


def test_the_loader_says_a_record_came_from_the_vocabulary():
    """The gate reads the loader's `table` tag, so the tag must be there: a
    SMILES only OPSIN's vocabulary knows comes back labelled as such."""
    for entry in get_retained_names_from_opsin():
        found = lookup_retained_name(entry["smiles"])
        if found is not None and found.get("name") == entry["name"]:
            assert found["table"] == OPSIN_VOCABULARY_TABLE
            return
    pytest.fail("no vocabulary-only SMILES found to check the tag on")


def test_a_curated_copy_of_an_opsin_entry_inherits_its_provenance(registry):
    """A record from another table, at the same structure AND name as an
    untyped OPSIN-sourced registry entry, is that entry and is refused. No
    live record takes this branch today (the four nucleobases that did are
    audited demotions, refused by name first), so it is driven directly."""
    smiles, entry = next((s, e) for s, e in registry.items()
                         if e["name"] == "fluorouracil")
    copy = {"smiles": smiles, "name": entry["name"], "table": "ring_curated"}
    assert retained_gate_refusal(copy, default_strategy()) == "OPSIN_VOCABULARY_UNTYPED"
