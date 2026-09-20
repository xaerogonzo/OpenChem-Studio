"""The charged-species panel is frozen, well-formed, and its hole set can only shrink.

`benchmarks/naming/charged_panel.toml` was built BY CLASS after naming round 7
found a defect in no corpus, and frozen when its baseline was committed
(`charged_panel_baseline.json`). These tests keep it honest:

* the panel is well-formed (every SMILES parses, ids are unique, every target has a
  basis and a source, `NONE_VERIFIED` carries the scope of the search);
* it is FROZEN: its hash is the one the baseline recorded, so a row cannot be
  added, dropped or retargeted to fit a fix;
* each row's DECLARED semantic owner agrees with the structure (a row declared
  ACID_ANION has an acid-anion site), so the panel cannot drift from its own
  classes;
* the ownership RATCHET: `KNOWN_HOLES` is the exact set of isolated-ion rows whose
  anion site no route claims. A new hole fails; a hole that gets fixed also fails,
  until it is removed from the list in the same commit as the fix. Naming round 7's
  R3 acceptance is this list becoming empty;
* no row is claimed twice, and none is claimed by a route the engine does not take.

Static except for the last group, which runs the real engine (not OPSIN).
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
PANEL = ROOT / "benchmarks" / "naming" / "charged_panel.toml"
BASELINE = ROOT / "benchmarks" / "naming" / "charged_panel_baseline.json"

ROWS = tomllib.loads(PANEL.read_text(encoding="utf-8"))["row"]
BY_ID = {r["id"]: r for r in ROWS}

REQUIRED = ("id", "class", "charge_state", "secondary_group", "context", "smiles",
            "expected_owner", "target_basis", "source", "why")
BASES = {"PRINTED", "DERIVED", "NONE_VERIFIED"}
OWNERS = {"ACID_ANION", "OLATE_ANION", "N_ANION", "ZWITTERION", "CATION", "per_component", "none"}
CONTEXTS = {"isolated_ion", "salt_inorganic_cation", "salt_organic_cation", "hydrate"}

#: The isolated-ion rows whose anion site NO route claims, as of the round-7 baseline.
#: A ratchet, not a target list: R3 removes ids from it as it fixes them, in the same
#: commit, and the round is done when it is empty. Sorted for a readable diff.
KNOWN_HOLES = frozenset({
    "A0-4-nitrobenzoate", "A1-3-hydroxybenzoate", "A1-3-hydroxybutanoate",
    "A1-4-hydroxybenzoate", "A1-4-hydroxybutanoate", "A1-gluconate", "A1-glycolate",
    "A1-lactate", "A1-mandelate", "A1-salicylate", "A2-3-aminopropanoate",
    "A2-4-aminobenzoate", "A2-N-methylglycinate", "A2-alaninate", "A2-anthranilate",
    "A2-cysteinate", "A2-glycinate", "A2-prolinate", "A2-tyrosinate",
    "A3-3-sulfanylpropanoate", "A3-sulfanylacetate", "A4-2-carboxybenzoate",
    "A4-3-carboxy-2-hydroxypropanoate", "A4-3-carboxypropanoate", "A4-5-carboxypentanoate",
    "A4-oxalate-mono", "A5-3-carbamoylpropanoate", "A5-citrate-diester-anion",
    "A6-2-hydroxybutanedioate-dianion", "B1-2-hydroxybenzenesulfonate", "B1-isethionate",
    "B1-sulfanilate", "B1-taurinate", "B3-hydrogen-phenylphosphonate",
    "B3-phenyl-hydrogen-phosphate", "B4-4-carboxybenzenesulfonate", "B4-4-sulfobenzoate",
    "D2-carbamate", "E2-glutamate-dianion",
})


def _isolated():
    return [r for r in ROWS if r["context"] == "isolated_ion"]


# ------------------------------------------------------------ well-formed
def test_the_panel_is_well_formed():
    assert len({r["id"] for r in ROWS}) == len(ROWS), "duplicate ids"
    for r in ROWS:
        missing = [k for k in REQUIRED if k not in r]
        assert not missing, (r.get("id"), missing)
        assert Chem.MolFromSmiles(r["smiles"]) is not None, r["id"]
        assert r["target_basis"] in BASES, r["id"]
        assert r["expected_owner"] in OWNERS, (r["id"], r["expected_owner"])
        assert r["context"] in CONTEXTS, r["id"]


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


# ------------------------------------------------------------ frozen
def test_the_panel_is_the_one_the_baseline_recorded():
    recorded = json.loads(BASELINE.read_text(encoding="utf-8"))["panel_sha256"]
    text = PANEL.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(text).hexdigest() == recorded, (
        "the panel changed after its baseline was committed; a row is never added, dropped or "
        "retargeted to fit a fix (log a new failure as R7-UNPLANNED instead)"
    )


def test_the_panel_has_the_rows_it_had_when_it_was_frozen():
    assert len(ROWS) == 108
    recorded = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert recorded["rows"] == len(ROWS)
    assert {r["id"] for r in recorded["records"]} == set(BY_ID)


# ------------------------------------------------------------ a target must denote its own row
#: Retained amino-acid names denote the L-isomer and the rows are drawn flat, so the two differ
#: by stereochemistry and by nothing else.
_STEREO_ONLY = {"A2-alaninate", "A2-prolinate", "A2-tyrosinate", "A2-cysteinate", "E2-glutamate-dianion"}
#: A printed PIN that OPSIN cannot parse: the oracle cannot say, and the book is the authority.
_OPSIN_CANNOT_READ = {"E1-betaine"}


def test_every_target_denotes_its_own_structure():
    """ENGINE-INDEPENDENT check on the panel itself: parse each printed or derived target with
    OPSIN and require the structure to be the row's. It caught the panel's one wrong target
    (a four-carbon acid for a three-carbon row) before any fix existed, which is what this
    test is for: a target that does not denote its row would score a CORRECT name as wrong.
    """
    from openchem.chem import naming_providers as providers

    if not providers.opsin_available():
        pytest.skip("OPSIN (a JRE on PATH) is required to check that targets denote their rows")
    with_target = [r for r in ROWS if r.get("target")]
    parsed = providers.opsin_structures_for_names([r["target"] for r in with_target])
    problems = []
    for r, result in zip(with_target, parsed):
        if result is None:
            if r["id"] not in _OPSIN_CANNOT_READ:
                problems.append((r["id"], r["target"], "OPSIN could not parse it"))
            continue
        want = Chem.MolFromSmiles(r["smiles"])
        got = Chem.MolFromSmiles(result.smiles)
        if got is not None and Chem.MolToSmiles(got) == Chem.MolToSmiles(want):
            continue
        if got is not None and r["id"] in _STEREO_ONLY:
            Chem.RemoveStereochemistry(got)
            Chem.RemoveStereochemistry(want)
            if Chem.MolToSmiles(got) == Chem.MolToSmiles(want):
                continue
        problems.append((r["id"], r["target"], result.smiles))
    assert not problems, problems


# ------------------------------------------------------------ declared class versus structure
def test_a_declared_anion_class_agrees_with_the_structure():
    """A row declared ACID_ANION must have an acid-anion site, and only that kind."""
    for r in _isolated():
        if r["expected_owner"] not in ("ACID_ANION", "OLATE_ANION"):
            continue
        classes = set(own.structural_sites(Chem.MolFromSmiles(r["smiles"])).values())
        assert classes == {r["expected_owner"]}, (r["id"], r["expected_owner"], classes)


def test_a_row_that_declares_no_anion_class_has_no_acid_anion_site():
    for r in _isolated():
        if r["expected_owner"] in ("CATION", "N_ANION"):
            assert not own.structural_sites(Chem.MolFromSmiles(r["smiles"])), r["id"]


# ------------------------------------------------------------ the ownership ratchet
def _static(r):
    return own.charged_owners(Chem.MolFromSmiles(r["smiles"]), r["smiles"], measure=False)


def test_the_hole_set_is_exactly_the_recorded_one():
    """No NEW hole, and a fixed hole must be removed from KNOWN_HOLES with its fix."""
    holes = {r["id"] for r in _isolated() if _static(r).verdict is own.Verdict.HOLE}
    assert holes - KNOWN_HOLES == set(), f"NEW unowned classes: {sorted(holes - KNOWN_HOLES)}"
    assert KNOWN_HOLES - holes == set(), (
        f"now owned, so remove from KNOWN_HOLES: {sorted(KNOWN_HOLES - holes)}"
    )


def test_no_anion_site_is_claimed_twice_or_left_inconsistent():
    bad = {
        r["id"]: _static(r).verdict.value
        for r in _isolated()
        if _static(r).verdict in (own.Verdict.OVERLAP, own.Verdict.INCONSISTENT)
    }
    assert not bad, bad


def test_the_baseline_recorded_the_same_holes():
    """The committed baseline was produced by the same diagnostic; if they disagree one of
    them is stale."""
    recorded = json.loads(BASELINE.read_text(encoding="utf-8"))
    baseline_holes = {
        r["id"] for r in recorded["records"]
        if r["context"] == "isolated_ion" and r["ownership"]["verdict"] == "HOLE"
    }
    assert baseline_holes == set(KNOWN_HOLES)


def test_the_engine_takes_the_route_the_static_claim_names():
    """For every isolated-ion row with an anion site that is OWNED, the route the engine
    actually recorded is the one predicted. The mirrored `fg_anion` predicate is what this
    would catch drifting."""
    checked = 0
    for r in _isolated():
        report = own.charged_owners(Chem.MolFromSmiles(r["smiles"]), r["smiles"], measure=True)
        if report.verdict is None or report.verdict is own.Verdict.HOLE:
            continue
        assert report.verdict is own.Verdict.OWNED, (r["id"], report.verdict, report.observed.route)
        checked += 1
    assert checked >= 20, checked


# ------------------------------------------------------------ salts
def test_a_salt_is_named_the_same_whichever_component_comes_first():
    """Recorded at baseline over every salt row (reversed order changes no name)."""
    recorded = json.loads(BASELINE.read_text(encoding="utf-8"))
    salts = [r for r in recorded["records"] if r.get("permutations")]
    assert len(salts) == 17
    dependent = [r["id"] for r in salts if not r["order_independent"]]
    assert dependent == [], dependent


# ------------------------------------------------------------ the adjudication of the non-correct rows
ADJUDICATION = ROOT / "benchmarks" / "naming" / "charged_panel_adjudication.toml"
LAYERS = {"CANDIDATE_ABSENT", "RANKED_OR_ASSIGNED_WRONG", "IMPLEMENTATION_GAP", "SCOPE_UNSUPPORTED",
          "SOURCE_UNRESOLVED"}
STAGES = {"R3", "R4", "R5", "DEFERRED"}
FIX_STATUS = {"OPEN", "PARTLY_FIXED", "FIXED", "NOT_APPLICABLE"}


def _families():
    return tomllib.loads(ADJUDICATION.read_text(encoding="utf-8"))["family"]


def _needs_adjudication(record) -> bool:
    return (record["status"] in ("WRONG_MOLECULE", "STRUCTURALLY_CORRECT/NON_PREFERRED")
            or record["ownership"]["verdict"] == "HOLE")


def test_every_non_correct_baseline_row_is_adjudicated_into_a_family():
    """A finding cannot be omitted: the adjudication lists every wrong molecule, every
    non-preferred name and every unowned anion site the baseline recorded."""
    recorded = json.loads(BASELINE.read_text(encoding="utf-8"))["records"]
    listed = {row for fam in _families() for row in fam["rows"]}
    needed = {r["id"] for r in recorded if _needs_adjudication(r)}
    assert needed <= listed, f"not adjudicated: {sorted(needed - listed)}"
    assert listed <= set(BY_ID), f"unknown panel rows: {sorted(listed - set(BY_ID))}"


def test_the_adjudication_uses_the_declared_vocabulary():
    for fam in _families():
        assert fam["layer"] in LAYERS, fam["id"]
        assert fam["target_stage"] in STAGES, fam["id"]
        assert fam["fix_status"] in FIX_STATUS, fam["id"]
        assert fam["mechanism"].strip() and fam["sources"].strip(), fam["id"]
        assert fam["rows"], fam["id"]


def test_a_source_unresolved_family_is_not_confused_with_a_row_with_no_verified_target():
    """`SOURCE_UNRESOLVED` says the pages read do not settle a family's target; `NONE_VERIFIED`
    is a property of one ROW's string. They are different fields and must stay different."""
    assert "SOURCE_UNRESOLVED" not in BASES and "NONE_VERIFIED" not in LAYERS
