"""The melting / normal-boiling-point corpus builder's parser, frozen (`benchmarks/mp_bp/PREREGISTRATION.md` section 7 and Amendment 1).

Every positive case is a cell as the two handbooks print it (read off the rendered page, not remembered); every
negative case is a plausible-but-wrong reading that the parser must refuse. The full corpus needs the maintainer's
PDF library and is not built here: `test_a_built_corpus_...` runs only when `OPENCHEM_MP_BP_CORPUS` names one, and an
ordinary run without it is NOT_RUN, never a pass.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks" / "mp_bp"


def _load(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


cells = _load("mpbp_cells", BENCH / "mpbp_cells.py")
identity = _load("mpbp_identity", BENCH / "mpbp_identity.py")
lange = _load("mpbp_lange", BENCH / "mpbp_lange.py")
build = _load("mpbp_build", BENCH / "mpbp_build.py")
vr = _load("validation_rows", ROOT / "tools" / "validation_rows.py")

M = cells.MINUS


# ---------------------------------------------------------------------------------------------- Lange cells
@pytest.mark.parametrize(
    ("column", "lines", "event", "value", "notation"),
    [
        ("mp", ["93.4"], "melting", 93.4, "plain"),
        ("mp", [f"{M}123"], "melting", -123.0, "plain"),                  # acetaldehyde, a4
        ("mp", ["286 d"], "melting_with_decomposition", 286.0, "value then d"),
        ("mp", ["220 dec"], "melting_with_decomposition", 220.0, "value then d"),
        ("mp", ["d 250"], "decomposition", 250.0, "d then value"),        # decomposes ONLY at 250 and above
        ("mp", ["subl 402"], "sublimation", 402.0, "subl with value"),
        ("bp", ["279"], "boiling", 279.0, "plain"),
        ("bp", ["subl"], "sublimation", None, "subl alone"),
        ("bp", ["100 d"], "decomposition", 100.0, "value then d"),
        ("bp", ["explodes"], "decomposition", None, "explodes"),
    ],
)
def test_lange_cells_read_to_the_event_the_table_defines(column, lines, event, value, notation):
    reading = cells.read_lange(column, lines)
    assert reading.readable
    assert (reading.event, reading.value, reading.notation) == (event, value, notation)


def test_a_lange_range_is_an_interval_not_a_midpoint():
    reading = cells.read_lange("mp", ["172–175"])
    assert (reading.low, reading.high, reading.value) == (172.0, 175.0, None)
    assert reading.has_temperature


def test_a_lange_boiling_cell_with_a_superscript_is_a_reduced_pressure():
    reading = cells.read_lange("bp", ["143^{1mm}"])
    assert (reading.event, reading.value, reading.pressure_mmhg) == ("boiling", 143.0, 1.0)


def test_a_wrapped_lange_cell_joins_only_if_the_joined_text_is_a_cell():
    ok = cells.read_lange("mp", [f"{M}23 to", f"{M}20"])
    assert ok.readable and (ok.low, ok.high) == (-23.0, -20.0)
    # two values (polymorphs) do not join: refused, not read as the first
    two = cells.read_lange("mp", ["46.5(�)", "12(�)"])
    assert not two.readable


@pytest.mark.parametrize(
    ("column", "lines", "problem"),
    [
        ("mp", ["�220 dec"], "unreadable_glyph"),            # a symbol that is not a minus sign
        ("mp", ["ca. 100"], "unrecognised"),                       # approximate
        ("mp", ["02.9"], "unrecognised"),                          # triethylborane's -92.9 with its 9 lost
        ("mp", [f"{M}5 to", f"{M}9"], "bad_range"),                # low above high
        ("mp", ["105^{3}"], "superscript"),                        # a superscript means nothing in a melting-point cell
        ("bp", ["145^{15}"], "bad_pressure"),                      # a pressure without its unit
        ("bp", ["120", "b123"], "multiple_lines"),                 # cross-reference debris
    ],
)
def test_a_cell_outside_the_grammar_is_refused_with_its_reason(column, lines, problem):
    reading = cells.read_lange(column, lines)
    assert not reading.readable and reading.problem == problem and reading.event == "unreadable"


def test_an_empty_cell_is_the_source_being_silent():
    assert cells.read_lange("mp", []) is None
    assert cells.read_lange("bp", [" "]) is None


# ---------------------------------------------------------------------------------------------- CRC cells
@pytest.mark.parametrize(
    ("column", "lines", "event", "value", "uncertainty", "pressure"),
    [
        ("mp", ["31.6(0.5)"], "melting", 31.6, 0.5, None),
        ("mp", ["-123.4(0.7)"], "melting", -123.4, 0.7, None),     # acetaldehyde
        ("mp", ["173.5"], "melting", 173.5, None, None),
        ("bp", ["277.5(0.8)"], "boiling", 277.5, 0.8, None),
        ("bp", ["250^{9}"], "boiling", 250.0, None, 9.0),          # abietic acid: 9 mmHg, not a normal boiling point
        ("bp", ["120 sub"], "sublimation", 120.0, None, None),
        ("bp", ["300 dec"], "decomposition", 300.0, None, None),
        ("mp", ["245 dec"], "melting_with_decomposition", 245.0, None, None),
        ("mp", ["25 tp"], "unknown", 25.0, None, None),            # a triple point is not a normal melting point
    ],
)
def test_crc_cells_read_to_the_event_the_table_defines(column, lines, event, value, uncertainty, pressure):
    reading = cells.read_crc(column, lines)
    assert reading.readable
    assert (reading.event, reading.value, reading.uncertainty, reading.pressure_mmhg) == (event, value, uncertainty, pressure)


def test_a_crc_cell_that_is_only_sub_is_a_sublimation_with_no_temperature():
    reading = cells.read_crc("bp", ["sub"])
    assert reading.event == "sublimation" and not reading.has_temperature


@pytest.mark.parametrize(
    ("column", "lines"),
    [("mp", [">350"]), ("mp", ["≈100"]), ("bp", ["<-20"]), ("mp", ["25 (hyd)"]), ("mp", ["115(α)", "99(β)"])],
)
def test_a_crc_qualified_or_two_form_cell_is_refused(column, lines):
    assert not cells.read_crc(column, lines).readable


# ---------------------------------------------------------------------------------------------- glyph classification
def _bar(rows, cols):
    return [[1] * cols for _ in range(rows)]


def test_a_solid_bar_is_a_minus_sign_and_nothing_else_is():
    assert lange.classify_ink(_bar(3, 28)) == "minus"
    assert lange.classify_ink(_bar(28, 3)) == "minus"                       # the page may be set sideways
    assert lange.classify_ink([[0] * 5 for _ in range(5)]) == "blank"
    assert lange.classify_ink(_bar(20, 20)) == "other"                      # a block
    plus = [[1 if r == 10 or c == 10 else 0 for c in range(21)] for r in range(21)]
    assert lange.classify_ink(plus) == "other"                              # a plus sign
    dashed = [[1 if c % 4 else 0 for c in range(28)] for _ in range(3)]
    assert lange.classify_ink(dashed) == "other"                            # a dashed line is not a minus
    assert lange.classify_ink(_bar(8, 40)) == "other"                       # too thick to be a minus
    assert lange.classify_ink(_bar(3, 12)) == "minus"                       # exactly 4:1
    assert lange.classify_ink(_bar(5, 12)) == "other"                       # a short stub (2.4:1) is not a bar


# ---------------------------------------------------------------------------------------------- identity
def test_formulas_and_weights():
    assert identity.parse_formula("C20H30O2") == {"C": 20, "H": 30, "O": 2}
    assert identity.parse_formula("C2H6O") == {"C": 2, "H": 6, "O": 1}
    assert identity.parse_formula("C6H12O6·H2O") is None               # a hydrate is not a plain formula
    assert identity.parse_formula("") is None
    weight, tol = identity.weight_tolerance("302.451")
    assert weight == 302.451 and tol == pytest.approx(max(0.0005, 2e-4 * 302.451))
    assert identity.weight_tolerance("44.05")[1] == pytest.approx(max(0.005, 2e-4 * 44.05))
    assert identity.weight_tolerance("n/a") is None


def test_name_spellings_try_both_readings_of_a_line_ending_in_a_hyphen():
    spellings, problem = identity.name_spellings(["4-Acetamidobenzalde-", "hyde"])
    assert problem == "" and spellings[0] == "4-Acetamidobenzaldehyde" and "4-Acetamidobenzalde-hyde" in spellings
    spellings, _ = identity.name_spellings(["N-(2-Acetamido)-2-", "aminoethanesulfonic", "acid"])
    assert "N-(2-Acetamido)-2-aminoethanesulfonic acid" in spellings
    soft = identity.SOFT_HYPHEN
    assert identity.name_spellings([f"Bis(2-hydroxyethyl){soft}", "methylamine"])[0] == ["Bis(2-hydroxyethyl)methylamine"]


def test_optical_signs_are_removed_but_a_lost_locant_is_never_dropped():
    assert identity.name_spellings([f"({M})-Abietic acid"])[0] == ["Abietic acid"]
    assert identity.name_spellings(["Acebutolol, (±)-"])[0] == ["Acebutolol"]
    assert identity.name_spellings(["�-Naphthol"]) == ([], "lost_character_in_name")
    assert identity.name_spellings(["β-Naphthol"])[0] == ["beta-Naphthol"]
    assert identity.name_spellings(["Café"]) == ([], "name_has_characters_opsin_cannot_be_sent")


def test_identity_needs_the_formula_the_weight_and_exactly_one_structure():
    ethanol = "CCO"
    assert identity.check([("ethanol", ethanol)], "C2H6O", "46.069").status == "ok"
    assert identity.check([("ethanol", ethanol)], "C2H6O", "46.069").smiles == ethanol
    assert identity.check([("ethanol", ethanol)], "C2H6O", "99.9").status == "mismatch"          # weight wrong
    assert identity.check([("ethanol", ethanol)], "C3H8O", "46.069").status == "mismatch"        # formula wrong
    assert identity.check([("x", None)], "C2H6O", "46.069").status == "unresolved"
    assert identity.check([("ethanol", ethanol)], None, "46.069").status == "unchecked"          # no formula: not a pass
    assert identity.check([("ethanol", ethanol)], "C2H6O", "").status == "unchecked"
    # two spellings, two different isomers, both fit the formula and the weight: NOT accepted
    ambiguous = identity.check([("a", "CCO"), ("b", "COC")], "C2H6O", "46.069")
    assert ambiguous.status == "ambiguous"
    # two spellings of the SAME structure are fine
    assert identity.check([("a", "CCO"), ("b", "OCC")], "C2H6O", "46.069").status == "ok"
    # one passing spelling beside a failing one: the passing one is the structure
    assert identity.check([("a", "CCO"), ("b", "CCCO")], "C2H6O", "46.069").smiles == "CCO"


# ---------------------------------------------------------------------------------------------- dispositions
def _decide(prop, reading):
    record = {"record_id": "t:1", "smiles": "CCO", "property": prop, "source": "crc97", "pdf_page": 1, "entry": "1"}
    build._decide(record, reading, vr)
    return record


def test_a_clean_melting_point_is_accepted_and_converted_to_kelvin():
    record = _decide("melting_point", cells.read_crc("mp", ["-114.1(0.1)"]))
    assert record["disposition"] == "accepted_melting_point"
    assert record["value_k"] == pytest.approx(159.05)


def test_a_boiling_point_with_no_printed_pressure_rests_on_the_tables_convention():
    record = _decide("normal_boiling_point", cells.read_crc("bp", ["78.2(0.3)"]))
    assert record["disposition"] == "accepted_normal_boiling_point"
    assert record["pressure_basis"] == "table_convention_normal"


def test_a_reduced_pressure_boiling_point_is_excluded_not_converted():
    record = _decide("normal_boiling_point", cells.read_crc("bp", ["250^{9}"]))
    assert record["disposition"] == "pressure_incomparable"
    assert "value_k" not in record


def test_a_stated_pressure_inside_the_tolerance_is_admitted():
    # 750 mmHg = 99.99 kPa, 1.3 kPa under normal: inside the +-1.5 kPa of the preregistration
    record = _decide("normal_boiling_point", cells.read_lange("bp", ["100^{750mm}"]))
    assert record["disposition"] == "accepted_normal_boiling_point" and record["pressure_basis"] == "stated"
    assert _decide("normal_boiling_point", cells.read_lange("bp", ["100^{735mm}"]))["disposition"] == "pressure_incomparable"


@pytest.mark.parametrize(
    ("prop", "column", "text", "reader"),
    [
        ("melting_point", "mp", ["245 dec"], cells.read_crc),
        ("melting_point", "mp", ["d 250"], cells.read_lange),
        ("normal_boiling_point", "bp", ["120 sub"], cells.read_crc),
        ("normal_boiling_point", "bp", ["300 dec"], cells.read_crc),
    ],
)
def test_decomposition_and_sublimation_are_evidence_only_never_a_label(prop, column, text, reader):
    record = _decide(prop, reader(column, text))
    assert record["disposition"] == "evidence_only_decomposition_or_sublimation"
    assert "value_k" not in record


def test_a_triple_point_is_not_a_normal_melting_point():
    assert _decide("melting_point", cells.read_crc("mp", ["25 tp"]))["disposition"] == "event_not_comparable"


def test_a_row_whose_melting_point_is_not_below_its_boiling_point_is_refused():
    shifted = build._implausible_row(cells.read_lange("mp", ["82"]), cells.read_lange("bp", ["82"]))
    assert shifted == "implausible_row"
    assert build._implausible_row(cells.read_lange("mp", ["93.4"]), cells.read_lange("bp", ["279"])) == ""
    # a reduced-pressure boiling point can legitimately sit below a melting point
    assert build._implausible_row(cells.read_lange("mp", ["120"]), cells.read_lange("bp", ["100^{1mm}"])) == ""
    assert build._implausible_row(cells.read_lange("mp", ["120"]), None) == ""


def _obs(low, high=None):
    return {"low_k": low, "high_k": high if high is not None else low, "is_range": high is not None}


def test_the_primary_label_rule_calls_values_more_than_one_kelvin_apart_a_conflict():
    assert not build._conflict([_obs(300.0), _obs(301.0)])
    assert build._conflict([_obs(300.0), _obs(301.1)])
    assert not build._conflict([_obs(300.0, 305.0), _obs(303.0, 310.0)])      # ranges that overlap
    assert build._conflict([_obs(300.0, 305.0), _obs(305.5, 310.0)])           # ranges that do not
    assert not build._conflict([_obs(300.0, 305.0), _obs(305.8)])              # a point within 1 K of a range


def test_every_disposition_the_builder_can_assign_is_in_the_documented_list():
    text = (BENCH / "mpbp_build.py").read_text(encoding="utf-8")
    for name in build.DISPOSITIONS:
        assert name in text
    assert len(set(build.DISPOSITIONS)) == len(build.DISPOSITIONS)


# ---------------------------------------------------------------------------------------------- a built corpus
CORPUS = os.environ.get("OPENCHEM_MP_BP_CORPUS")


@pytest.mark.skipif(not CORPUS, reason="NOT_RUN: set OPENCHEM_MP_BP_CORPUS to a corpus built from the local PDF library")
def test_a_built_corpus_gives_every_candidate_row_exactly_one_known_disposition():
    summary = json.loads((Path(CORPUS) / "summary.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (Path(CORPUS) / "observations.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == summary["candidate_rows"] == sum(summary["dispositions"].values())
    assert all(r["disposition"] in build.DISPOSITIONS for r in rows)
    assert len({r["record_id"] for r in rows}) == len(rows)
    manifest = json.loads((Path(CORPUS) / "manifest.json").read_text(encoding="utf-8"))
    assert vr.manifest_checksum(manifest) == summary["manifest_checksum"]
    assert set(manifest.values()) <= vr.PARTITIONS


# ---------------------------------------------------------------------------------------------- committed artifacts
def _committed():
    manifest = json.loads((BENCH / "split_manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((BENCH / "corpus_summary.json").read_text(encoding="utf-8"))
    return manifest, summary


def test_the_committed_manifest_matches_its_checksum_and_every_partition_is_recomputable():
    manifest, summary = _committed()
    assert vr.manifest_checksum(manifest) == summary["manifest_checksum"]
    # a partition depends on the key alone: nothing about the other rows or the order they were read in
    assert all(vr.partition_for(key) == partition for key, partition in manifest.items())
    shares = {p: sum(1 for v in manifest.values() if v == p) / len(manifest) for p in vr.PARTITIONS}
    assert shares["development"] == pytest.approx(0.60, abs=0.02)
    assert shares["selection"] == pytest.approx(0.20, abs=0.02)
    assert shares["holdout"] == pytest.approx(0.20, abs=0.02)


def test_the_committed_summary_accounts_for_every_candidate_row_once():
    _, summary = _committed()
    assert set(summary["dispositions"]) == set(build.DISPOSITIONS)
    assert sum(summary["dispositions"].values()) == summary["candidate_rows"]
    by_source = sum(sum(c.values()) for c in summary["dispositions_by_source"].values())
    assert by_source == summary["candidate_rows"]
    # the manifest holds exactly the primary-stratum entities with a resolved label for at least one property
    manifest, _ = _committed()
    assert len(manifest) <= sum(summary["entities_with_resolved_label_in_primary_stratum"].values())
    assert len(manifest) >= max(summary["entities_with_resolved_label_in_primary_stratum"].values())


def test_the_committed_report_is_what_the_generator_makes_from_the_committed_summary():
    _, summary = _committed()
    text = (BENCH / "CORPUS_REPORT.md").read_text(encoding="utf-8")
    assert text == build.render_report(summary)


def test_the_committed_summary_names_both_source_files_by_hash_and_scores_no_method():
    _, summary = _committed()
    assert set(summary["source_files"]) == {"lange15", "crc97"}
    assert all(len(v["sha256"]) == 64 for v in summary["source_files"].values())
    assert not any("mae" in key.lower() or "score" in key.lower() for key in summary)
