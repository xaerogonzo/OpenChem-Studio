"""`tools/naming_bluebook_harvest.py`: the pure parts of the Blue Book harvest (no PDF, no OPSIN, no network).

Each rule here was measured on the book's own text before it was written down. The names used below are ORDINARY strings chosen to hit one rule
each, including the shapes the first draft of the extraction got wrong (a formula line, a non-preferred name and an index number joined onto a
preferred name; 465 wrong joins out of 4,260). The tests do not name the frozen population's file: they go through the tool's constants, because
`tests/test_naming_heldout_lock.py` allows only the drawing script to name it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import naming_bluebook_harvest as harvest  # noqa: E402


# --- joining a name from its lines --------------------------------------------------------------------------------------------------------------

def test_a_line_is_joined_only_when_the_name_itself_is_broken():
    tail = ["c][1,4]oxaazacyclohentriacontine"]  # closes a bracket it never opened
    assert harvest.continues("9,10,12-hexadecahydro-3H-23,27-epoxypyrido[2,1-", tail)
    assert harvest.continues("2,5,8-trioxa-", ["decane"])  # the previous line ends in a hyphen
    assert harvest.continues("7-(1,1,1,3,3,3-hexafluoro-2-methylpropan-2-", ["yl)dodecane"])  # a bracket left open
    assert harvest.continues("2-methylpropane-1,2,3-tricarboxylic", ["acid"])  # the tail is a bare class word


@pytest.mark.parametrize(
    "previous",
    [
        "CH3-COOH",  # a condensed formula: the shape that made the first draft wrong 465 times
        "acetone",  # a non-preferred name printed above the preferred one
        "1",  # an index number
        "at the third character the nonalphanumerical { is preferred to [",  # prose
        "X = P",  # not a name at all
        "methyl alcohol (PIN)",  # another tagged name
    ],
)
def test_an_adjacent_line_that_is_not_part_of_the_name_is_never_joined(previous):
    assert not harvest.continues(previous, ["phenylacetonitrile"])


def test_a_full_name_is_not_a_tail_just_because_the_previous_line_is_a_name():
    assert not harvest.continues("acetone", ["propan-2-one"])
    assert not harvest.continues("benzyl cyanide", ["phenylacetonitrile"])


def test_pieces_are_glued_the_way_a_name_wraps():
    assert harvest.join_name(["3,6,9-tetraoxa-", "pentadecan-1-oic acid"]) == "3,6,9-tetraoxa-pentadecan-1-oic acid"
    assert harvest.join_name(["cyclopenta[4,5]oxepino[3′,2′-c:2″,3″-", "h]phenazine"]) == "cyclopenta[4,5]oxepino[3′,2′-c:2″,3″-h]phenazine"
    assert harvest.join_name(["2-methylpropane-1,2,3-tricarboxylic", "acid"]) == "2-methylpropane-1,2,3-tricarboxylic acid"
    assert harvest.join_name(["7-(chloro", ")heptane"]) == "7-(chloro)heptane"
    # a space the text layer put after a hyphen inside a name is never valid, so it goes
    assert harvest.join_name(["pentacosafluoro-7- (1,1,1-trifluoro"]) == "pentacosafluoro-7-(1,1,1-trifluoro"


def test_list_markers_the_typesetting_adds_are_stripped_and_nothing_else():
    assert harvest.clean_name("(1) (chloroacetyl)oxy") == "(chloroacetyl)oxy"
    assert harvest.clean_name("Step 2: 2,4,6-trithia") == "2,4,6-trithia"
    assert harvest.clean_name("cyclohexane (I)") == "cyclohexane"
    assert harvest.clean_name("(2,4-dimethylphenyl)methanol") == "(2,4-dimethylphenyl)methanol"  # a substituent's own bracket is not a marker
    assert harvest.clean_name("1H-indene") == "1H-indene"


def test_primes_and_dashes_are_normalised_for_the_parser_and_a_lambda_is_not_invented_into_ascii():
    assert harvest.normalise_for_opsin("[3′,2′-c:2″,3″-h]") == "[3',2'-c:2'',3''-h]"
    assert harvest.normalise_for_opsin("2–methyl—x") == "2-methyl-x"
    assert not harvest.normalise_for_opsin("methyl-λ6-sulfane").isascii(), "py2opsin cannot write a lambda: the row is reported, not rewritten"


# --- the scope filters: one reason per row, and the false positives that were measured ---------------------------------------------------------

@pytest.mark.parametrize(
    "name, reason",
    [
        ("(2R)-butan-2-ol", "stereodescriptor"),
        ("(2Z,5E)-hepta-2,5-dienedioic acid", "stereodescriptor"),
        ("rel-(1R,2S)-cyclohexane-1,2-diol", "stereodescriptor"),
        ("cis-but-2-ene", "stereodescriptor"),
        ("(2H6)propane", "isotope"),
        ("(4-2H1,2-3H1)pentane", "isotope"),
        ("(131I)iodo-3-iodopropan-2-ol", "isotope"),
        ("[13C]methane", "isotope"),
        ("[U-14C]butanoic acid", "isotope"),
        ("(3-2H)pyridine", "isotope"),
        ("(O-2H)acetic acid", "isotope"),
        ("(N-2H1)acetamide", "isotope"),
        ("1-chloro-3-fluoro(2-2H)benzene", "isotope"),
        ("(4aR,8aR,9aS,10aS)-tetradecahydroanthracene", "stereodescriptor"),
        ("(3aR,7aS)-octahydro-1H-indole", "stereodescriptor"),
        ("coronene—1,3,5-trinitrobenzene (1/1)", "not_a_structure_name"),
        ("benzene-1,2,3-triol — quinolin-8-ol (1/2)", "not_a_structure_name"),
        ("methylidyne", "radical_or_ion_wildcard"),
        ("polyethene", "polymer"),
        ("ferrocene", "organometallic"),
        ("X = P phosphanthrene", "not_a_structure_name"),
        ("", "not_a_structure_name"),
        ("ab", "not_a_structure_name"),
    ],
)
def test_each_scope_filter_names_its_reason(name, reason):
    assert harvest.scope_reason(name, False) == reason


@pytest.mark.parametrize(
    "name",
    [
        "1,3,5-trithiane",  # `trit` inside `trithiane` is not a tritium name (an early regex made 60 false isotope hits)
        "sodium methoxide",  # a simple salt is not an organometallic compound
        "2,4,6-trithia-1-azaheptane",
        "acetic acid",
        "N,N-dimethylformamide",
        "(2,4-dimethylphenyl)methanol",
        # indicated hydrogen has the shape of an isotope and is not one (an earlier pattern dropped every such name)
        "pyrimidin-4(3H)-one",
        "anthracen-9(10H)-one",
        "naphthalen-2(1H)-one",
        "1,3-benzodioxole-5,6(2H)-dione",
        # a hydrogen or a letter locant inside parentheses is not always an isotope or a descriptor
        "anthracene-1,9,10(2H)-trione",
        "quinolin-6(2H)-one",
        "1,1'-carbonothioyldi(pyridin-2(1H)-one)",
        "4a-methyl-1,2,3,4,4a,9,9a,10-octahydroanthracene",
        "N-methyl-N-(propan-2-yl)acetamide",
    ],
)
def test_ordinary_names_pass_every_filter(name):
    assert harvest.scope_reason(name, False) is None


def test_unbalanced_brackets_are_a_page_or_column_split_and_take_precedence():
    assert harvest.scope_reason("tetracyclo[5.4.2.22,6.18,11hexadecane", True) == "page_or_column_split"
    assert harvest.scope_reason("(2R)-butan-2-ol", True) == "page_or_column_split"


def test_what_opsin_could_not_read_is_classified_for_reporting():
    assert harvest.chemistry_class("1(4)-pyridina-7(2)-furana-3,5(1,4)-dibenzenaheptaphane") == "phane"
    assert harvest.chemistry_class("1(9)aH-1(9)a-homo(C60-Ih)[5,6]fullerene") == "fullerene"
    assert harvest.chemistry_class("acetic butanedioic dianhydride") == "anhydride"
    assert harvest.chemistry_class("cyclohexanecarbonyl") == "substituent_group"
    assert harvest.chemistry_class("propan-2-one") == "other"


# --- chapters and the split -------------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("section, chapter", [("P-1", 1), ("P-25.3.3", 2), ("P-65.1.2", 6), ("P-93.5", 9), ("P-101.2", 10)])
def test_the_chapter_is_the_leading_digits_of_the_section(section, chapter):
    assert harvest.chapter_of(section) == chapter


def test_a_non_section_is_refused_not_guessed():
    with pytest.raises(ValueError):
        harvest.chapter_of("Table 4.1")


def _records(per_chapter: dict[int, int]) -> list[dict]:
    return [
        {"label": f"bb-{chapter}-{i}", "inchikey": f"KEY{chapter:02d}{i:05d}AAAAAA-BBBBBBBBBB-N", "chapter": chapter}
        for chapter, n in per_chapter.items() for i in range(n)
    ]


def test_the_two_halves_cover_every_chapter_and_differ_by_at_most_one_row_in_each():
    records = _records({1: 11, 2: 40, 6: 200, 9: 2})
    halves = harvest.assign_halves(records)
    assert set(halves.values()) == {"tuning", "frozen"}
    for chapter in (1, 2, 6, 9):
        in_chapter = [halves[r["label"]] for r in records if r["chapter"] == chapter]
        assert abs(in_chapter.count("tuning") - in_chapter.count("frozen")) <= 1, chapter
        assert {"tuning", "frozen"} <= set(in_chapter), f"chapter {chapter} lost a half"


def test_the_assignment_does_not_depend_on_the_order_the_rows_arrive_in():
    records = _records({1: 30, 6: 50})
    forward = harvest.assign_halves(records)
    assert harvest.assign_halves(list(reversed(records))) == forward


def test_the_assignment_is_by_structure_identity_not_by_label():
    """Renaming a row's label must not move it between halves: the hash is over the InChIKey (and the chapter)."""
    records = _records({6: 40})
    before = harvest.assign_halves(records)
    renamed = [{**r, "label": "renamed-" + r["label"]} for r in records]
    after = harvest.assign_halves(renamed)
    assert {label.removeprefix("renamed-"): half for label, half in after.items()} == before


# --- what counts as seen ------------------------------------------------------------------------------------------------------------------------------

def test_structures_a_python_file_mentions_are_found_by_parsing_its_string_constants():
    from rdkit import Chem

    aspirin, citric = "CC(=O)Oc1ccccc1C(=O)O", "OC(=O)CC(O)(CC(O)=O)C(O)=O"
    source = "\n".join([f'ROWS = ["{aspirin}", "not a smiles", "CC", "aspirin"]', f'X = "{citric}"'])
    found = harvest.structure_strings(source)
    assert found == {Chem.MolToSmiles(Chem.MolFromSmiles(aspirin)), Chem.MolToSmiles(Chem.MolFromSmiles(citric))}
    # "CC" is below the three-heavy-atom floor: without it half of chemistry would be marked seen, and "aspirin" is not a SMILES


def test_the_protocol_hash_is_of_the_committed_file():
    import hashlib

    assert harvest.protocol_sha256() == hashlib.sha256(harvest.PROTOCOL.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


# --- seen ------------------------------------------------------------------------------------------------------------------------------------------------

def _membership(**populations):
    import naming_populations as registry

    return {key: (registry.MEMBERSHIP_SALT, frozenset(registry.membership_hash(s) for s in structures)) for key, structures in populations.items()}


def test_a_structure_is_seen_by_smiles_by_inchikey_by_printed_name_or_by_another_populations_hash():
    empty = _membership()
    assert not harvest.seen("CCO", "KEY1", ["ethanol"], set(), set(), "", empty)
    assert harvest.seen("CCO", "KEY1", ["ethanol"], {"CCO"}, set(), "", empty)  # the same canonical SMILES
    assert harvest.seen("CCO", "KEY1", ["ethanol"], set(), {"KEY1"}, "", empty)  # a tautomer or another spelling: the same InChIKey
    assert harvest.seen("CCO", "KEY1", ["ethanol"], set(), set(), "the target ethanol appears in a panel", empty)  # the printed name
    assert harvest.seen("CCO", "KEY1", ["ethanol"], set(), set(), "", _membership(heldout_v6=["CCO"]))  # another frozen population, by hash


def test_the_harvests_own_frozen_half_is_never_read_as_seen():
    """A rebuild found its previous output in the registry and lost half of its pool: 2,273 unseen structures became 1,137. Its own frozen
    half must not count, and any OTHER frozen population still must."""
    own = _membership(bluebook_frozen=["CCO"])
    assert not harvest.seen("CCO", "KEY1", ["ethanol"], set(), set(), "", own)
    both = {**own, **_membership(heldout_v6=["CCO"])}
    assert harvest.seen("CCO", "KEY1", ["ethanol"], set(), set(), "", both)
