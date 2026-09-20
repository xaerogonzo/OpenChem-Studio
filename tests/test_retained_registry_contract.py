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


def test_a_standalone_vocabulary_name_passes_only_on_book_evidence():
    """The gate asks the registry about each vocabulary name. Until N9 nothing
    in the registry typed one, so every name was refused and this test said
    so flatly. The N9 audit typed "ammonia" from P-21.1.1.2, and the gate let
    that one name through -- which is the rule working, not an escape from it.
    What must stay true is that the ONLY names it passes are the ones the
    registry types with NORMATIVE_RULE evidence."""
    strategy = default_strategy()
    entries = list(get_retained_names_from_opsin())
    refused = [retained_gate_refusal({**e, "table": OPSIN_VOCABULARY_TABLE}, strategy)
               for e in entries]
    assert "OPSIN_VOCABULARY_UNTYPED" in refused
    typed_names = {
        entry["name"]
        for entry in audit.registry().values()
        if entry.get("evidence_kind") == "NORMATIVE_RULE"
    }
    passed = {e.get("name") for e, why in zip(entries, refused) if why is None}
    assert passed <= typed_names, f"passed the gate untyped: {passed - typed_names}"


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


# --- Naming round 5 (N9): the name and the structure must be the same thing --
#
# The audit of the usable backlog found three entries whose name was bound to
# the WRONG STRUCTURE -- "L-proline" on D-proline, "L-threonine" on
# L-allothreonine, "L-isoleucine" on L-alloisoleucine -- and found them only
# because each name happened to appear under a second SMILES too. Nothing was
# checking the pair. OPSIN reads the name independently of this registry, so
# it can: wherever OPSIN's own parse fixes the stereocentres, the registry's
# structure must be that structure.
#
# Where OPSIN returns no stereochemistry the registry may be more specific
# ("nicotine" is the (S) enantiomer in nature), so those are compared without
# it. The three nucleobases differ from OPSIN's parse by a TAUTOMER, not a
# structure, and are named as the tautomer set; they are listed here so the
# exemption is visible rather than silent.
_TAUTOMER_EXEMPT = {"adenine", "guanine", "hypoxanthine"}


def test_every_registry_name_denotes_its_own_structure(registry):
    from py2opsin import py2opsin
    from rdkit import Chem

    def canonical(smiles: str, *, stereo: bool) -> str | None:
        mol = Chem.MolFromSmiles(smiles) if smiles else None
        if mol is None:
            return None
        return Chem.MolToSmiles(mol, isomericSmiles=stereo)

    entries = list(registry.items())
    parsed = py2opsin([entry["name"] for _smiles, entry in entries])
    if isinstance(parsed, str):  # a single-name result
        parsed = [parsed]
    wrong = []
    for (smiles, entry), opsin_smiles in zip(entries, parsed):
        name = entry["name"]
        if name in _TAUTOMER_EXEMPT or not opsin_smiles:
            continue
        # Compare with stereochemistry only where OPSIN fixed it.
        stereo = canonical(opsin_smiles, stereo=True) != canonical(
            opsin_smiles, stereo=False
        )
        theirs = canonical(opsin_smiles, stereo=stereo)
        ours = canonical(smiles, stereo=stereo)
        if theirs != ours:
            wrong.append(f"{name}: registry {ours} but the name reads as {theirs}")
    assert not wrong, "registry entries whose name is not their structure:\n" + "\n".join(wrong)


def test_no_name_is_bound_to_two_structures(registry):
    """One name, one structure. The three amino-acid defects above sat in the
    registry as a name under two different SMILES, one of them wrong."""
    from collections import Counter

    names = Counter(entry["name"] for entry in registry.values())
    duplicated = {name: count for name, count in names.items() if count > 1}
    assert not duplicated, f"names bound to more than one structure: {duplicated}"

