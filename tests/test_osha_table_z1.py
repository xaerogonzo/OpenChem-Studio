"""OSHA Table Z-1, and the four things that make a limit auditable.

Stage 6b. `tests/test_quantitative_limits.py` guards the MODEL -- what a
limit may be, and that the 91 rules shipped before it existed are
untouched. This file guards the DATA: that the numbers came off the
regulation, that a reader is told what each one is a limit ON, and that
the rows the ruleset does not encode are counted rather than silently
absent.

**THE SOURCE IS THE REGULATION, NOT AN ANNOTATED PAGE.** OSHA publishes
annotated PEL tables that print NIOSH, Cal/OSHA and ACGIH values beside
the statutory ones; a row lifted from there would look identical in the
artefact and would not be law. The extractor reads the eCFR XML of
29 CFR 1910.1000 and nothing else, the snapshot records that document's
sha256, and `test_the_ruleset_was_built_from_the_committed_regulation`
is what ties the shipped numbers to the committed bytes.

**AND IT IS A REGULATION, NOT A STATUTE.** 29 CFR 1910.1000 is a rule
made under the OSH Act. This project's "an identity comes from the CAS
the statute prints" note was written about the CWC Annex, which is an
actual treaty text; the wording does not carry over, and footnote (c)
says the opposite here -- the CAS is informational and enforcement is on
the printed NAME.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

import pytest

from openchem.chem.regulatory.calculator import _LIMIT_TYPE_LABELS, _limit_lines
from openchem.chem.regulatory.loader import SHIPPED_ROOT, load_ruleset
from openchem.chem.regulatory.types import (
    NORMALIZED_UNITS,
    LimitPrecision,
    LimitType,
)

REPO = pathlib.Path(__file__).resolve().parent.parent
SOURCE_ROOT = REPO / "src" / "openchem" / "chem" / "data" / "regulatory" / "sources"
XML = SOURCE_ROOT / "osha_1910_1000.xml"
SOURCE_JSON = SOURCE_ROOT / "osha_table_z1.json"
GENERATED = SHIPPED_ROOT / "osha_table_z1.json"


@pytest.fixture(scope="module")
def source() -> dict:
    return json.loads(SOURCE_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def ruleset():
    return load_ruleset(GENERATED)


def _by_name(ruleset, prefix: str):
    """The rule whose display name starts with `prefix`.

    Asserted to be unique, because Table Z-1 prints several substances
    whose names share a stem and a fixture silently matching a different
    row would be a test of the wrong number.
    """
    hits = [r for r in ruleset.rules if r.display_name.startswith(prefix)]
    assert len(hits) == 1, f"{prefix!r} matched {len(hits)} rules, not 1"
    return hits[0]


# --- the source is the regulation ----------------------------------------


def test_the_ruleset_was_built_from_the_committed_regulation(source, ruleset):
    """The chain the whole ruleset's authority rests on, in one assertion.

    The committed XML hashes to the sha256 the extractor recorded, and the
    generated ruleset records the same digest -- so "these numbers came
    off that document" is checkable rather than asserted. A later rebuild
    can then say *same snapshot, different code* rather than *different
    snapshot*, which a date alone cannot distinguish.
    """
    digest = hashlib.sha256(XML.read_bytes()).hexdigest()

    assert source["source_snapshot"]["document"] == XML.name
    assert source["source_snapshot"]["sha256"] == digest

    # THE SHIPPED RULESET, not merely our intermediate. `source_snapshot`
    # is a distinct field from `provenance.source_document_sha256`
    # precisely because the OSHA source JSON is ITSELF generated: that
    # field hashes our transcription and would stop the chain one link
    # short of the regulation.
    assert ruleset.source_snapshot is not None
    assert ruleset.source_snapshot.sha256 == digest
    assert ruleset.source_snapshot.document == XML.name


def test_the_two_provenance_hashes_answer_different_questions(ruleset):
    """They must not be the same number, or one of them is redundant.

    `provenance.source_document_sha256` hashes the source JSON in this
    repository and says whether OUR build input changed;
    `source_snapshot.sha256` hashes the regulation as served and says
    whether the LAW changed. Collapsing them makes "the regulation was
    amended" and "we regenerated our copy" indistinguishable.
    """
    assert ruleset.provenance.source_document_sha256
    assert ruleset.source_snapshot is not None
    assert ruleset.provenance.source_document_sha256 != ruleset.source_snapshot.sha256


def test_a_ruleset_transcribed_by_hand_claims_no_snapshot():
    """The narrow half, and the one that keeps the field honest.

    "Every ruleset has a snapshot" is satisfied by defaulting an empty one
    onto the four that predate it, which would claim a retrieval that
    never happened for a regulation somebody typed in by hand. `None` is
    the answer there, and the loader refuses a partial snapshot rather
    than filling the gaps.
    """
    for name in (
        "cwc_schedule_1.json",
        "cwc_schedule_2.json",
        "cwc_schedule_3.json",
        "dea_listed_chemicals.json",
    ):
        assert load_ruleset(SHIPPED_ROOT / name).source_snapshot is None


def test_the_committed_snapshot_is_not_translated_by_git():
    """A CI-BREAKING TRAP THIS REPOSITORY HAS ALREADY PAID FOR ONCE.

    `core.autocrlf=true` is set here, so a text file is stored LF and
    checked out CRLF on Windows. The snapshot carries 4763 bare LFs and
    its sha256 is the evidence tying the shipped numbers to the
    regulation, so without an exception a fresh Windows clone would hash
    a different document than Linux CI does -- and the guard above would
    go red on one platform for a reason having nothing to do with the
    regulation.

    Asserted on `.gitattributes` rather than on the working tree, because
    the working tree is right on the machine that wrote the file and
    wrong on the next clone, which is exactly why this is easy to miss.
    """
    attributes = (REPO / ".gitattributes").read_text(encoding="utf-8")
    declared = [
        line.split()[0]
        for line in attributes.splitlines()
        if line.strip() and not line.startswith("#") and "-text" in line
    ]

    assert any(
        XML.match(pattern) or XML.name.endswith(pattern.rsplit("*", 1)[-1])
        for pattern in declared
    ), f"{XML.name} is not exempted from newline translation: {declared}"


def test_the_snapshot_records_a_status_and_not_a_boolean(source):
    """Retrieved today, current as of retrieval, official but historical
    and superseded are four states. A bool collapses them, and the one it
    loses is the one that matters -- a ruleset built from a superseded
    revision looks exactly like a current one."""
    snapshot = source["source_snapshot"]

    assert snapshot["retrieved"]
    assert isinstance(snapshot["status"], str) and snapshot["status"]


def test_the_committed_xml_is_the_regulation_and_carries_no_advisory_column(source):
    """The annotated-page hazard, asserted on the bytes rather than trusted.

    OSHA's annotated tables print NIOSH and ACGIH recommendations beside
    the statutory PELs. Those organisations do not appear in the eCFR text
    of this section at all, so their absence is what says the extractor
    read the regulation. If a future snapshot mentions them, this fails
    and the source must be re-examined before its numbers are believed.
    """
    text = XML.read_text(encoding="utf-8")

    assert "1910.1000" in text
    for advisory in ("NIOSH", "ACGIH", "Cal/OSHA"):
        assert advisory not in text, f"{advisory} appears in the snapshot"

    assert source["source_citation"].startswith(
        "United States Code of Federal Regulations"
    )


# --- the rows the ruleset does not encode --------------------------------


def test_the_row_census_accounts_for_every_row_of_the_table(source):
    """FOUR classes, and they must sum to the table.

    A ruleset that encodes 390 of 500 rows and reports only the 390 is
    indistinguishable from one that read a 390-row table -- so the rows
    that became no rule are counted, by class, in the artefact. The sum is
    the check that no row fell out of the taxonomy entirely.
    """
    census = source["row_census"]
    classes = (
        "encoded",
        "no_limit_printed",
        "cross_reference",
        "limit_in_another_table",
    )

    assert sum(census[name] for name in classes) == census["total_rows"]
    assert census["encoded"] == len(source["rules"])
    for name in classes:
        assert census[name] > 0, f"{name} has no live row, so it is untested"


def test_the_stated_limitations_are_derived_from_the_census(source):
    """A number typed into a sentence inside shipped data is the failure
    this project records most, and this file's own prose carried one: it
    said 26 where the table has 22 rows deferring to Z-2/Z-3 and 87
    cross-references. Nothing could see it, because no guard reads prose.

    So the counts are DERIVED, and this asserts they still agree. It is a
    weak check by construction -- it can only catch the two drifting -- and
    that is the point: the strong version is that there is one source for
    the number, not two.
    """
    census = source["row_census"]
    prose = " ".join(source["known_limitations"])

    for count in (
        census["total_rows"],
        census["encoded"],
        census["cross_reference"],
        census["limit_in_another_table"],
        census["no_limit_printed"],
    ):
        assert str(count) in prose, f"{count} is not stated anywhere"

    assert "26 rows" not in prose


def test_a_row_deferring_to_another_table_is_not_encoded_as_unlimited(source):
    """Carbon disulfide's Z-1 entry gives its value as `(2)`: Table Z-2
    holds the number. Encoding that row with no limit would say OSHA sets
    none, which is the opposite of what the table says -- so it is counted
    and omitted, and the ruleset's own limitations say so."""
    names = [r["display_name"] for r in source["rules"]]

    assert not any(n.startswith("Carbon disulfide") for n in names)
    assert source["row_census"]["limit_in_another_table"] > 0
    assert any(
        "Z-2" in limitation for limitation in source["known_limitations"]
    ), "nothing tells the reader those substances are not covered here"


def test_the_one_row_with_no_printed_limit_is_absent_rather_than_zero(source):
    """`n/a` is not 0, on the one row of Table Z-1 that exercises it.

    Respirable crystalline silica is listed and its Z-1 cell prints no
    PEL. A rule carrying a limit of zero would be a claim the regulation
    does not make, and the strictest one available.
    """
    assert source["row_census"]["no_limit_printed"] == 1
    assert not any(
        r["display_name"].startswith("Silica, crystalline, respirable")
        for r in source["rules"]
    )


# --- what the table prints, read off the table ---------------------------


def test_an_unmarked_value_is_an_eight_hour_average(ruleset):
    """Footnote 1: "The PELs are 8-hour TWAs unless otherwise noted."

    Acetaldehyde prints 200 ppm with no marking, so both of its limits are
    TWAs and the ppm string carries no notation at all.
    """
    limits = _by_name(ruleset, "Acetaldehyde").quantitative_limits

    assert [limit.limit_type for limit in limits] == [LimitType.TWA_8H] * 2
    assert limits[0].source.value == "200"
    assert limits[0].source.unit == "ppm"
    assert limits[0].source.raw_notation == ""


def test_a_C_marked_value_is_a_ceiling_and_the_marking_survives(ruleset):
    """Chlorine prints `(C)1` ppm. The reading is CEILING and the `(C)`
    that produced it is kept beside it, so an auditor can see the token
    and not merely our conclusion from it.

    The `(C)` also stays inside `source.value`, because that field is the
    characters the regulation printed -- stripping it would make the
    stored string something the table does not contain.
    """
    limits = _by_name(ruleset, "Boron trifluoride").quantitative_limits

    assert [limit.limit_type for limit in limits] == [LimitType.CEILING] * 2
    assert limits[0].source.value == "(C)1"
    assert limits[0].source.raw_notation == "(C)"


def test_the_two_kinds_are_both_present_and_are_told_apart(ruleset):
    """The setup assertion for the pair above.

    A ruleset that classified every row as a TWA would satisfy the
    acetaldehyde test and say nothing, so the population is asserted:
    both kinds occur, and neither is a rounding error.
    """
    kinds = {
        limit.limit_type
        for rule in ruleset.rules
        for limit in rule.quantitative_limits
    }

    assert kinds == {LimitType.TWA_8H, LimitType.CEILING}


def test_footnote_b_decides_precision_and_the_same_column_carries_both(ruleset):
    """The sharpest thing in Table Z-1, and it is invisible in a cell.

    Footnote (b): a mg/m3 entry "is exact" when it stands alone and "is
    approximate" when a ppm entry accompanies it. So two mg/m3 numbers,
    printed identically, mean different things -- which is why
    `LimitPrecision` has three values rather than a bool, and why the ppm
    entries are UNSTATED rather than being guessed into one of the two.

    Acrylamide prints 0.3 mg/m3 alone; acetaldehyde prints 360 mg/m3
    beside 200 ppm.
    """
    alone = _by_name(ruleset, "Acrylamide ").quantitative_limits
    accompanied = _by_name(ruleset, "Acetaldehyde").quantitative_limits

    assert len(alone) == 1
    assert alone[0].source.unit == "mg/m3"
    assert alone[0].precision is LimitPrecision.EXACT

    assert accompanied[1].source.unit == "mg/m3"
    assert accompanied[1].precision is LimitPrecision.APPROXIMATE
    assert accompanied[0].source.unit == "ppm"
    assert accompanied[0].precision is LimitPrecision.UNSTATED


def test_all_three_precisions_occur_in_the_shipped_table(ruleset):
    """The population behind the fixture above. A build that collapsed
    footnote (b) into one answer would still pass a single-row check."""
    seen = {
        limit.precision
        for rule in ruleset.rules
        for limit in rule.quantitative_limits
    }

    assert seen == set(LimitPrecision)


def test_a_skin_designation_reaches_the_reader_as_a_limitation(ruleset):
    """95 substances carry it, and it was filed where nothing renders.

    `MachineInterpretation.assumptions` has no reader on the regulatory
    path, so a skin designation recorded there is a fact the table prints
    and the application never shows. It is a limitation on how the
    airborne number may be read, and `_finding_lines` renders those.
    """
    flagged = [
        rule
        for rule in ruleset.rules
        if any("SKIN DESIGNATION" in text for text in rule.interpretation.limitations)
    ]

    assert len(flagged) > 50, f"only {len(flagged)} rules carry it"
    assert any(rule.display_name.startswith("Acrylamide ") for rule in flagged)

    # ...and it says what the consequence IS, not merely that a column was
    # ticked. "Skin" alone is a word off a heading; a reader needs to know
    # the number above it does not cover that route.
    text = next(
        t
        for t in flagged[0].interpretation.limitations
        if "SKIN DESIGNATION" in t
    )
    assert "absorbed through the skin" in text
    assert "does not account" in text


# --- nothing is converted ------------------------------------------------


def test_no_shipped_limit_carries_a_normalized_value(ruleset):
    """ppm to mg/m3 is not a unit conversion: it needs the substance's
    molar mass as well as the 25 C and 760 torr footnote (a) states. The
    model refuses a normalized value without a stated method, and this
    asserts the build never supplied one -- so every number on screen is
    the regulation's own."""
    for rule in ruleset.rules:
        for limit in rule.quantitative_limits:
            assert limit.normalized_value is None
            assert limit.normalized_unit == ""
            assert limit.normalization_method == ""


def test_the_source_unit_is_verbatim_and_not_drawn_from_the_closed_set(ruleset):
    """`NORMALIZED_UNITS` is owned by a conversion layer that does not
    exist yet. The source unit is whatever the column heading printed --
    here the two happen to coincide as strings, so this asserts the
    RELATIONSHIP rather than a difference: the source units are the
    table's, and nothing has been mapped onto the closed vocabulary."""
    units = {
        limit.source.unit
        for rule in ruleset.rules
        for limit in rule.quantitative_limits
    }

    assert units == {"ppm", "mg/m3"}
    assert all(limit_unit in NORMALIZED_UNITS for limit_unit in units), (
        "the coincidence this test documents no longer holds"
    )


# --- the number reaches a reader with its meaning attached ---------------


def test_every_limit_type_has_a_label(ruleset):
    """A member with no label is a `KeyError` at render time, on a
    calculator that reaches the Property panel, the batch table and the
    inspector. Derived from the enum so a seventh member cannot be added
    without one."""
    assert set(_LIMIT_TYPE_LABELS) == set(LimitType)
    assert all(_LIMIT_TYPE_LABELS[member] for member in LimitType)


def test_a_rendered_limit_carries_its_value_its_unit_and_its_kind(ruleset):
    """`Benzene 10` is dangerous in a way `Benzene 10 ppm, 8-hour TWA` is
    not, and a reader cannot recover the difference.

    This project has shipped that failure once already -- `Fact.units` was
    populated, read by three exporters and never rendered in the row, so
    *Copy report* carried units the screen did not. So the assertion is on
    the RENDERED LINE and not on the JSON.
    """
    limit = _by_name(ruleset, "Acetaldehyde").quantitative_limits[0]

    (line,) = _limit_lines(limit)

    assert "200" in line
    assert "ppm" in line
    assert "8-hour TWA" in line


def test_a_ceiling_never_renders_as_an_average(ruleset):
    """The two are opposite claims and the numbers look identical, so the
    label is the only thing telling them apart. `(C)1 ppm` must not read
    as an 8-hour average anywhere in the string."""
    limit = _by_name(ruleset, "Boron trifluoride").quantitative_limits[0]

    (line,) = _limit_lines(limit)

    assert "ceiling" in line
    assert "TWA" not in line
    assert "(C)1" in line


def test_an_approximate_value_says_so_on_the_line(ruleset):
    """Footnote (b) is on the rule's limitations, which is where the RULE
    is explained; without it on the line, two mg/m3 numbers of different
    epistemic status render identically."""
    exact = _by_name(ruleset, "Acrylamide ").quantitative_limits[0]
    approximate = _by_name(ruleset, "Acetaldehyde").quantitative_limits[1]

    assert "approximate" not in _limit_lines(exact)[0]
    assert "approximate" in _limit_lines(approximate)[0]


def test_a_qualifier_gets_its_own_line_and_is_verbatim(ruleset):
    """A footnote is prose of unknown length. Folded into the value line
    it makes the number unreadable beside its own caption -- which is the
    width defect this project has recorded in three separate panels -- so
    it is rendered underneath, unparsed and unshortened."""
    qualified = next(
        limit
        for rule in ruleset.rules
        for limit in rule.quantitative_limits
        if limit.source.qualifier
    )

    lines = _limit_lines(qualified)

    assert len(lines) == 2
    assert qualified.source.qualifier in lines[1]
    assert qualified.source.qualifier not in lines[0]


def test_every_rendered_limit_line_is_ascii(ruleset):
    """These reach Qt, logs and Windows console streams, and this project
    has recorded a cp437 console raising on a superscript three and a
    cp1252 one raising on a tick. The whole regulatory calculator already
    holds this rule; the new lines join it."""
    for rule in ruleset.rules:
        for limit in rule.quantitative_limits:
            for line in _limit_lines(limit):
                assert line.isascii(), line


# --- the two resolution rules, and why neither guesses -------------------
#
# Both were found by writing SMILES for 24 well-known substances by hand
# and asking whether they matched the rule OPSIN had derived from the
# printed name. 17 agreed; the disagreements were not noise.


def _resolve(name: str):
    """The build's own resolver, imported here rather than reimplemented.

    A second copy of "what structure does this name mean" is the drift
    this project has paid for five times.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_build_rulesets", REPO / "tools" / "build_regulatory_rulesets.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._resolve_name(name)


@pytest.mark.parametrize(
    ("printed", "expected_smiles"),
    [
        ("Chloroform (Trichloromethane)", "ClC(Cl)Cl"),
        ("Ethyl alcohol (Ethanol)", "CCO"),
    ],
)
def test_a_parenthetical_alias_does_not_ship_as_a_two_component_mixture(
    printed, expected_smiles
):
    """Table Z-1 prints aliases in parentheses and OPSIN reads them as a
    SECOND COMPONENT: `Chloroform (Trichloromethane)` came back as
    `ClC(Cl)Cl.C(Cl)(Cl)Cl`, whose InChIKey is not chloroform's.

    So the rule shipped as a verified identity that could never match a
    drawn chloroform -- a screen that says nothing, which is the exact
    silence this engine exists to prevent. Every fragment being the same
    substance is what licenses collapsing it: an alias names the compound
    it is an alias for.

    THE ORACLE IS A SMILES WRITTEN INDEPENDENTLY of the resolver, so
    agreement is two routes agreeing rather than a value compared with
    itself.
    """
    from rdkit import Chem

    key, note = _resolve(printed)
    expected = Chem.MolToInchiKey(Chem.MolFromSmiles(expected_smiles))

    assert key == expected, note


@pytest.mark.parametrize(
    ("printed", "expected_smiles"),
    [
        ("Calcium carbonate", "[Ca+2].[O-]C([O-])=O"),
        ("Barium sulfate", "[Ba+2].[O-]S([O-])(=O)=O"),
    ],
)
def test_the_alias_rule_does_not_swallow_the_salts(printed, expected_smiles):
    """THE LOAD-BEARING HALF, and it caught this rule being wrong.

    The first version refused ANY multi-component answer as a misparse.
    That read as a tidy safety check and dropped 18 rules -- calcium
    carbonate, barium sulfate, ammonium sulfamate -- because for a SALT
    the multi-component structure IS the identity, and OPSIN returning
    `[Ca+2].[O-]C([O-])=O` is it working correctly.

    Only counting the rules either side of the change showed it: 236 fell
    to 216, which is the green-suite-and-a-smaller-universe failure in
    miniature. So the survivors are asserted BY NAME rather than by a
    threshold that would read as stronger than it is.

    The rule collapses fragments only when they are the SAME substance --
    which is what an alias produces and what a salt never does.
    """
    from rdkit import Chem

    key, note = _resolve(printed)
    expected = Chem.MolToInchiKey(Chem.MolFromSmiles(expected_smiles))

    assert key == expected, note


def test_a_multi_component_name_keeps_every_component(ruleset):
    """The population behind the pair above: the shipped ruleset really
    does contain salts, so the guard is not asserting against a set the
    build could no longer produce."""
    salts = [
        rule
        for rule in ruleset.rules
        if rule.display_name.startswith(("Calcium ", "Barium ", "Ammonium "))
    ]

    assert len(salts) >= 5, f"only {len(salts)} salt rules survived"


@pytest.mark.parametrize("element", ["Chlorine", "Iodine"])
def test_an_element_name_that_gives_a_LONE_ATOM_is_refused(element):
    """OPSIN answers "Chlorine" with `[Cl]`, a chlorine atom, where the
    air contaminant carrying a 1 ppm ceiling is Cl2.

    **REFUSED, NEVER CORRECTED.** Writing Cl2 here would be a hand-typed
    structure standing in for a resolution, which is the one thing the
    build exists to prevent -- so the row becomes a counted unresolved
    entry a reader can see rather than a rule that can never fire.
    """
    key, note = _resolve(element)

    assert not key
    assert "standard state" in note


@pytest.mark.parametrize(
    ("printed", "expected_smiles"),
    [
        ("Copper", "[Cu]"),
        ("Ammonia", "N"),
        ("Hydrogen chloride", "Cl"),
        ("Acetaldehyde", "CC=O"),
    ],
)
def test_the_lone_atom_rule_does_not_swallow_what_it_must_not(
    printed, expected_smiles
):
    """THE LOAD-BEARING HALF. "Refuse a single-atom resolution" is
    satisfied by a rule that also refuses copper -- which really IS a lone
    atom, and whose Z-1 row says "as Cu" -- and the failure mode of an
    over-broad refusal is a GREEN suite and a smaller ruleset, which reads
    as tidier coverage rather than as lost rows.

    Ammonia and hydrogen chloride are the other trap: one heavy atom
    apiece, and the rule keys on hydrogens rather than on heavy-atom
    count for exactly that reason.
    """
    from rdkit import Chem

    key, note = _resolve(printed)
    expected = Chem.MolToInchiKey(Chem.MolFromSmiles(expected_smiles))

    assert key == expected, note


def test_the_refused_rows_are_counted_and_say_why(ruleset):
    """A refusal nobody can see is an absence. Both new rules report
    through the coverage the ruleset already carries, so "OSHA lists
    chlorine and we could not resolve it" is answerable without reading
    the build's console output."""
    reasons = " ".join(ruleset.coverage.unresolved)

    assert "standard state" in reasons
    assert any("chlorine" in entry.lower() for entry in ruleset.coverage.unresolved)


def test_the_coverage_counts_reconcile(ruleset):
    """`total_entries` is every row the build was handed; `resolved` plus
    `unresolved` must be that number. This project has already shipped a
    build that double-counted an unresolved entry, so the two halves are
    checked against the total rather than against each other."""
    coverage = ruleset.coverage

    assert coverage.resolved == len(ruleset.rules)
    assert coverage.resolved + len(coverage.unresolved) == coverage.total_entries


def test_a_display_name_is_ascii_while_its_quote_stays_verbatim(source):
    """THE SPLIT, on the one row that exercises it.

    Table Z-1 prints `4,4'-Thiobis (6-tert, Butyl-m-cresol)` with a U+2032
    PRIME. Two of that row's three name fields are OURS and are
    transliterated; the third is the regulation's and is not.

      display_name  rendered onto finding lines that reach Qt, logs and
                    console streams, where this project has recorded
                    cp1252 raising on a tick
      names         handed to OPSIN, which writes it to a temp file in
                    the console encoding -- the raw prime failed with
                    `UnicodeEncodeError` and was recorded as unresolved,
                    which reads as a chemistry failure and was an
                    environment one
      legal.quote   the regulation in its own words. Changing the
                    evidence to make it printable is a different thing
                    from rendering it.

    ASSERTED ON THE SOURCE, not the generated ruleset, because this row
    does not resolve: transliterated it fails with `NamingError`, since
    "6-tert, Butyl" is not valid nomenclature. That is an honest reason
    for the same outcome, and the point of the fix -- the name was
    deliberately NOT rewritten into one OPSIN accepts.
    """
    thiobis = next(
        rule for rule in source["rules"] if "Thiobis" in rule["display_name"]
    )

    assert thiobis["display_name"].isascii()
    assert all(name.isascii() for name in thiobis["names"])
    assert not thiobis["legal"]["quote"].isascii(), (
        "the quote no longer carries the character this test exists for"
    )
    assert "\u2032" in thiobis["legal"]["quote"]


def test_the_unresolved_reason_describes_the_name_not_our_pipeline(ruleset):
    """An `UnicodeEncodeError` in a coverage note tells a reader the
    substance could not be read, when what happened is that our temp file
    could not be written. A refusal that misattributes its own cause is
    worse than a vague one -- it sends somebody to look at the chemistry.
    """
    assert not any(
        "UnicodeEncodeError" in entry for entry in ruleset.coverage.unresolved
    )


def test_every_display_name_the_report_renders_is_ascii(ruleset):
    """The population behind the fixture above, because one transliterated
    row says nothing about the next revision's typography. The extractor
    RAISES on an unmapped non-ASCII character rather than dropping it, so
    this is the shipped half of a rule that fails closed at build time."""
    for rule in ruleset.rules:
        assert rule.display_name.isascii(), rule.display_name
