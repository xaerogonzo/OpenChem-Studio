"""The addendum charged-species panel (naming round 8) is frozen, well-formed, and honest.

`benchmarks/naming/charged_panel_r8.toml` is a SECOND panel, built after round 7's final evaluation
showed the first one had the classes its author thought of and no others (no row had three acid
groups, so the citrate trianion and a biguanidium cation were named wrong and nothing saw it). It is
frozen when its baseline (`charged_panel_r8_baseline.json`) is committed, exactly as round 7's was,
and it does NOT replace it: `tests/test_charged_panel.py` still pins the first panel.

* it is FROZEN: its hash is the one the baseline recorded, so a row cannot be added, dropped or
  retargeted to fit a fix (log a new failure as R8-UNPLANNED instead);
* it is well-formed, and carries the columns that make it a coverage design rather than a list
  of interesting molecules (`site_vector`, `structural_context`, `coverage_reason`);
* every target denotes its OWN row (parsed by OPSIN), so a correct name cannot be scored wrong by
  a wrong target;
* the ownership ratchet: `KNOWN_HOLES` is the exact set of isolated-ion rows whose anion site no route
  claims. Round 7 ended with none on ITS panel; this one has two, and a fixed hole must leave the
  list in the commit that fixes it;
* every row the baseline recorded as not correct is adjudicated into a family, with a primary
  layer and its dependencies, and a family whose layer is UNTRACED says its mechanism is a hypothesis.

Static except the ownership and OPSIN groups, which run the real engine and a JRE.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

import pytest
from rdkit import Chem, RDLogger

from openchem.vendor.iupac_namer.perception import charge_ownership as own

RDLogger.DisableLog("rdApp.*")

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "benchmarks" / "naming" / "charged_panel_r8.toml"
BASELINE = ROOT / "benchmarks" / "naming" / "charged_panel_r8_baseline.json"
ADJUDICATION = ROOT / "benchmarks" / "naming" / "charged_panel_r8_adjudication.toml"

ROWS = tomllib.loads(PANEL.read_text(encoding="utf-8"))["row"]
BY_ID = {r["id"]: r for r in ROWS}

REQUIRED = ("id", "class", "charge_state", "site_vector", "secondary_group", "context", "structural_context",
            "smiles", "expected_owner", "target_basis", "source", "coverage_reason", "why")
BASES = {"PRINTED", "DERIVED", "NONE_VERIFIED"}
OWNERS = {"ACID_ANION", "OLATE_ANION", "N_ANION", "ZWITTERION", "CATION", "per_component", "none"}
CONTEXTS = {"neutral", "isolated_ion", "salt_inorganic_cation", "salt_organic_cation", "salt_inorganic_anion",
            "salt_organic_anion", "zwitterion", "hydrate"}
STRUCTURAL_CONTEXTS = {"acyclic", "aromatic", "heterocyclic", "fused", "salt", "zwitterion"}

#: The isolated-ion rows whose anion site NO route claims and that no scope declaration covers. A RATCHET:
#: both are mixed-class polyanions (an olate and a carboxylate; `acid_anion_route` returns None for two anion
#: classes). A new entry is a new unowned class and fails; a fixed one must be removed in the commit that fixes it.
KNOWN_HOLES = frozenset({"Q3-serinate-as-drawn", "Q3-salicylate-dianion"})


def _isolated():
    """Every single-component row: an isolated ion OR a zwitterion (the serinate row is drawn as one
    molecule and its context is `zwitterion`, so filtering on `isolated_ion` alone would skip a hole)."""
    return [r for r in ROWS if "." not in r["smiles"] and r["context"] != "neutral"]


# ------------------------------------------------------------ well-formed
def test_the_panel_is_well_formed():
    assert len({r["id"] for r in ROWS}) == len(ROWS), "duplicate ids"
    for r in ROWS:
        missing = [k for k in REQUIRED if k not in r]
        assert not missing, (r.get("id"), missing)
        assert Chem.MolFromSmiles(r["smiles"]) is not None, r["id"]
        assert r["target_basis"] in BASES, r["id"]
        assert r["expected_owner"] in OWNERS, (r["id"], r["expected_owner"])
        assert r["context"] in CONTEXTS, (r["id"], r["context"])
        assert r["structural_context"] in STRUCTURAL_CONTEXTS, (r["id"], r["structural_context"])
        assert r["coverage_reason"].strip() and r["site_vector"].strip(), r["id"]


def test_a_target_exists_exactly_when_the_book_gives_one():
    for r in ROWS:
        if r["target_basis"] == "NONE_VERIFIED":
            assert not r.get("target"), r["id"]
            assert "not found in the pages searched" in r["source"], r["id"]
        else:
            assert r.get("target"), r["id"]
            assert "pdf p" in r["source"] or r["source"].startswith("P-"), (r["id"], r["source"])


def test_a_printed_row_cites_a_page():
    for r in ROWS:
        if r["target_basis"] == "PRINTED":
            assert "pdf p" in r["source"], (r["id"], r["source"])


def test_a_target_uses_the_ascii_apostrophe_the_engine_emits():
    """The book prints primed locants with U+2032; the engine (and every other target in this repository)
    uses the ASCII apostrophe, so an exact comparison is not defeated by a character."""
    for r in ROWS:
        assert "′" not in (r.get("target") or ""), r["id"]


def test_the_panel_covers_the_contexts_the_round_is_about():
    """Not every class needs every context, but the round's two seams must each be tested in a salt and
    on their own: a polyacid and a cation."""
    by_class = {}
    for r in ROWS:
        by_class.setdefault(r["class"], set()).add(r["structural_context"])
    assert "salt" in by_class["polyacid_salt"]
    assert {"acyclic", "aromatic"} <= by_class["polyacid_neutral"] | by_class["polyacid_anion"]
    assert {"heterocyclic", "fused"} <= {c for k, v in by_class.items() if k.startswith(("protonated", "azolium")) for c in v}
    assert "zwitterion" in {r["structural_context"] for r in ROWS}


# ------------------------------------------------------------ frozen
def test_the_panel_is_the_one_the_baseline_recorded():
    recorded = json.loads(BASELINE.read_text(encoding="utf-8"))["panel_sha256"]
    text = PANEL.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(text).hexdigest() == recorded, (
        "the addendum panel changed after its baseline was committed; a row is never added, dropped or "
        "retargeted to fit a fix (log a new failure as R8-UNPLANNED instead)"
    )


def test_the_panel_has_the_rows_it_had_when_it_was_frozen():
    assert len(ROWS) == 60
    recorded = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert recorded["rows"] == len(ROWS) and recorded["panel"] == PANEL.name
    assert {r["id"] for r in recorded["records"]} == set(BY_ID)


def test_the_round_7_panel_was_not_touched():
    """The first panel is immutable. Its own test pins its hash; this asserts it from here too, so a
    change to it fails in the round that is most tempted to make one."""
    first = ROOT / "benchmarks" / "naming" / "charged_panel.toml"
    recorded = json.loads((ROOT / "benchmarks" / "naming" / "charged_panel_baseline.json")
                          .read_text(encoding="utf-8"))["panel_sha256"]
    assert hashlib.sha256(first.read_bytes().replace(b"\r\n", b"\n")).hexdigest() == recorded


# ------------------------------------------------------------ a target must denote its own row
def test_every_target_denotes_its_own_structure():
    """ENGINE-INDEPENDENT check on the panel itself: parse each target with OPSIN and require the
    structure to be the row's. It ran BEFORE the panel was frozen (round 7 found its one wrong target
    only afterwards), and stays as a standing test."""
    from openchem.chem import naming_providers as providers

    if not providers.opsin_available():
        pytest.skip("OPSIN (a JRE on PATH) is required to check that targets denote their rows")
    with_target = [r for r in ROWS if r.get("target")]
    parsed = providers.opsin_structures_for_names([r["target"] for r in with_target])
    problems = []
    for r, result in zip(with_target, parsed):
        if result is None:
            problems.append((r["id"], r["target"], "OPSIN could not parse it"))
            continue
        want = Chem.MolFromSmiles(r["smiles"])
        got = Chem.MolFromSmiles(result.smiles)
        if got is None or Chem.MolToSmiles(got) != Chem.MolToSmiles(want):
            problems.append((r["id"], r["target"], result.smiles))
    assert not problems, problems


# ------------------------------------------------------------ declared class versus structure
def test_a_declared_anion_class_agrees_with_the_structure():
    """A row declared ACID_ANION has an acid-anion site. (A mixed-class row may also carry an olate site, so the
    declared class must be PRESENT among the structural classes, not the only one.)"""
    for r in _isolated():
        if r["expected_owner"] not in ("ACID_ANION", "OLATE_ANION"):
            continue
        classes = set(own.structural_sites(Chem.MolFromSmiles(r["smiles"])).values())
        assert r["expected_owner"] in classes, (r["id"], r["expected_owner"], classes)


def test_a_row_that_declares_a_cation_has_no_acid_anion_site():
    for r in _isolated():
        if r["expected_owner"] == "CATION":
            assert not own.structural_sites(Chem.MolFromSmiles(r["smiles"])), r["id"]


# ------------------------------------------------------------ the ownership ratchet
def _static(r):
    return own.charged_owners(Chem.MolFromSmiles(r["smiles"]), r["smiles"], measure=False)


def test_the_hole_set_is_exactly_the_recorded_one():
    """No NEW hole, and a fixed hole must be removed from KNOWN_HOLES with its fix."""
    holes = {r["id"] for r in _isolated() if _static(r).verdict is own.Verdict.HOLE}
    assert holes - KNOWN_HOLES == set(), f"NEW unowned classes: {sorted(holes - KNOWN_HOLES)}"
    assert KNOWN_HOLES - holes == set(), f"now owned, so remove from KNOWN_HOLES: {sorted(KNOWN_HOLES - holes)}"


def test_no_anion_site_is_claimed_twice_or_left_inconsistent():
    bad = {
        r["id"]: _static(r).verdict.value
        for r in _isolated()
        if _static(r).verdict in (own.Verdict.OVERLAP, own.Verdict.INCONSISTENT)
    }
    assert not bad, bad


def test_the_baseline_recorded_the_holes_this_round_started_from():
    recorded = json.loads(BASELINE.read_text(encoding="utf-8"))
    baseline_holes = {
        r["id"] for r in recorded["records"]
        if "." not in r["smiles"] and r["context"] != "neutral" and r["ownership"]["verdict"] == "HOLE"
    }
    # The BEFORE is never rewritten: the hole set at baseline is these two rows, whatever KNOWN_HOLES says later.
    assert baseline_holes == {"Q3-serinate-as-drawn", "Q3-salicylate-dianion"}, baseline_holes


# ------------------------------------------------------------ salts
def test_a_salt_is_named_the_same_whichever_component_comes_first():
    """Recorded at baseline over every salt row (reversed order changes no name)."""
    recorded = json.loads(BASELINE.read_text(encoding="utf-8"))
    salts = [r for r in recorded["records"] if r.get("permutations")]
    assert len(salts) == 6
    dependent = [r["id"] for r in salts if not r["order_independent"]]
    assert dependent == [], dependent


# ------------------------------------------------------------ the adjudication of the non-correct rows
LAYERS = {"CANDIDATE_ABSENT", "RANKED_OR_ASSIGNED_WRONG", "IMPLEMENTATION_GAP", "SCOPE_UNSUPPORTED",
          "SOURCE_UNRESOLVED", "SERIALIZATION", "UNTRACED"}
STAGES = {"W1", "W2", "W3", "W4", "DEFERRED"}
FIX_STATUS = {"OPEN", "PARTLY_FIXED", "FIXED", "NOT_APPLICABLE"}
NOT_CORRECT = ("WRONG_MOLECULE", "ENGINE_ERROR", "ORACLE_ERROR", "STRUCTURALLY_CORRECT/NON_PREFERRED")


def _families():
    return tomllib.loads(ADJUDICATION.read_text(encoding="utf-8"))["family"]


def test_every_non_correct_baseline_row_is_adjudicated_into_a_family():
    """A finding cannot be omitted: the adjudication lists every wrong molecule, every error, every
    non-preferred name and every unowned anion site the baseline recorded."""
    recorded = json.loads(BASELINE.read_text(encoding="utf-8"))["records"]
    listed = {row for fam in _families() for row in fam["rows"]}
    needed = {r["id"] for r in recorded if r["status"] in NOT_CORRECT or r["ownership"]["verdict"] == "HOLE"}
    assert needed <= listed, f"not adjudicated: {sorted(needed - listed)}"
    assert listed <= set(BY_ID), f"unknown panel rows: {sorted(listed - set(BY_ID))}"


def test_the_adjudication_uses_the_declared_vocabulary():
    ids = set()
    for fam in _families():
        assert fam["id"] not in ids, f"duplicate family {fam['id']}"
        ids.add(fam["id"])
        assert fam["primary_layer"] in LAYERS, fam["id"]
        assert fam["target_stage"] in STAGES, fam["id"]
        assert fam["fix_status"] in FIX_STATUS, fam["id"]
        assert fam["mechanism"].strip() and fam["sources"].strip(), fam["id"]
        assert fam["rows"], fam["id"]
        assert isinstance(fam["dependencies"], list), fam["id"]
    for fam in _families():
        assert set(fam["dependencies"]) <= ids, (fam["id"], fam["dependencies"])


def test_an_untraced_family_says_its_mechanism_is_a_hypothesis():
    """The round's first W1 claim was a mechanism nobody had traced, and it was wrong. A family whose layer is
    UNTRACED must say so in its mechanism text, so a hypothesis cannot read as a finding."""
    for fam in _families():
        if fam["primary_layer"] == "UNTRACED":
            assert "HYPOTHESIS" in fam["mechanism"], fam["id"]


def test_a_row_is_in_at_most_one_family():
    seen: dict[str, str] = {}
    for fam in _families():
        for row in fam["rows"]:
            assert row not in seen, f"{row} is in {seen[row]} and {fam['id']}"
            seen[row] = fam["id"]
