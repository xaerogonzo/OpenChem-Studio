"""Can a user FIND a feature using the words they arrived with?

The palette is the app's search-for-anything and it indexed display names
only, so it answered the vocabulary people actually have with either
nothing or noise. Measured against the real ranker before keywords
existed:

    cif        -> "Scientific Limitations", "Open Project Plugins Folder"
    pdb        -> "Periodic Table..."
    toxicity   -> "Toggle Explicit Hydrogens"
    sdf, xyz, mmcif, protein, lattice, spectrum -> NOTHING

The first three are the subsequence tier answering with confident
nonsense, which is worse than an empty list: it looks like the app
considered the question and that was its answer.

Two sources feed the fix and only one of them is hand-written.
Calculators carry `tags` already (45 of 58, 94 distinct) and those are
derived. The menu map is the hand-written half, so it gets a guard.
"""

from __future__ import annotations

import pytest

from openchem.app.main_window import _MENU_KEYWORDS
from openchem.ui.dialogs.command_palette import Command, rank, score


def _command(label: str, source: str = "Test", keywords: tuple[str, ...] = ()) -> Command:
    return Command(label=label, source=source, run=lambda: None, keywords=keywords)


@pytest.fixture(scope="module")
def main_window(qapp, tmp_path_factory):
    """One real window for the whole file.

    Module-scoped because building it is the expensive part and every
    test here only READS `_collect_commands()`. Retained rather than
    destroyed: `tests/conftest.py` keeps every MainWindow for the
    session on purpose -- collecting one corrupts the heap, which cost
    about fifteen full suite runs to find.
    """
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container

    directory = tmp_path_factory.mktemp("palette")
    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(directory / "none"))
    settings.set("plugins/user_directory", str(directory / "none2"))
    return MainWindow(services, settings, SessionManager())


# --- the ranking contract ----------------------------------------------


def test_a_keyword_finds_a_command_its_label_never_would():
    commands = [_command("Import Crystal Structure...", keywords=("cif", "lattice"))]

    assert [c.label for c in rank("cif", commands)] == ["Import Crystal Structure..."]


def test_a_label_match_still_beats_a_keyword_match():
    """"Batch" the panel must win over a calculator that merely lists
    `batch` among its tags. A keyword is a way in, not a promotion."""
    panel = _command("Batch", source="Panel")
    calculator = _command("Chemical Space", source="Calculator", keywords=("batch",))

    ordered = rank("batch", [calculator, panel])

    assert ordered[0] is panel


def test_a_keyword_match_beats_a_subsequence_match_on_a_label():
    """This is the "toxicity" case. `Toggle Explicit Hydrogens` matches
    t-o-x-i-c-i-t-y one letter at a time and is nonsense; a calculator
    tagged `toxicity` is the answer, and must outrank it."""
    noise = _command("Toggle Explicit Hydrogens")
    real = _command("ADMET (hERG, CYP, Ames, ADME)", keywords=("toxicity", "admet"))

    ordered = rank("toxicity", [noise, real])

    assert ordered[0] is real


def test_a_command_with_no_keywords_ranks_exactly_as_before():
    """Keywords are additive. A command that has none must score
    identically to what `score()` alone gives it, or this change has
    quietly reordered the whole palette."""
    for label in ("Batch", "Properties", "Structure Check", "Quantum Chemistry"):
        for query in ("bat", "str", "qc", "properties", ""):
            plain = _command(label)
            assert rank(query, [plain]) == ([plain] if score(query, label) > 0 else [])


def test_keywords_do_not_invent_matches_for_an_unrelated_query():
    commands = [_command("Import Crystal Structure...", keywords=("cif", "lattice"))]

    assert rank("zzzz", commands) == []


# --- the hand-written half ----------------------------------------------


def test_every_menu_keyword_names_a_live_action(qapp, main_window):
    """**THE MAP IS KEYED ON A MENU LABEL, WHICH IS THE SHAPE THAT ROTS.**

    `inapplicable_calculators` was 22-of-49 correct by the time anybody
    counted, because nothing ever compared its hand-written names against
    the live thing they described. This compares, and names the stale key.
    """
    live = {label for label, _source, _action in main_window._menu_actions()}
    stale = sorted(set(_MENU_KEYWORDS) - live)

    assert not stale, (
        f"{stale} have keywords but are no longer menu actions -- renamed or removed?"
    )


def test_no_menu_keyword_merely_repeats_its_own_label(qapp):
    """A keyword that is already a word of the label buys nothing and
    makes the map look bigger than it is. The label is searched
    directly."""
    redundant = {
        label: [k for k in keywords if k in label.lower()]
        for label, keywords in _MENU_KEYWORDS.items()
    }
    offenders = {label: words for label, words in redundant.items() if words}

    assert not offenders, f"already findable by label: {offenders}"


# --- the words people actually arrive with -------------------------------


#: Query -> the command that should come FIRST. Every one of these
#: returned nothing or noise before keywords existed; the file docstring
#: has the measurements.
_EXPECTED_FIRST = {
    "cif": "Import Crystal Structure...",
    "lattice": "Import Crystal Structure...",
    "unit cell": "Import Crystal Structure...",
    "protein": "Import Macromolecule...",
    "mmcif": "Import Macromolecule...",
    "sdf": "Import Molecule...",
    "xyz": "Import Molecule...",
    "isotope": "Periodic Table...",
    "pubchem": "Identify Structure Online...",
    "orca": "External Tools...",
    # NOT "valence": there is a real menu item called "Show Valence",
    # and it beating "Check Structure..." is the ranking working. The
    # keyword still gets Check Structure into the list, second.
    "sanitise": "Check Structure...",
}


@pytest.mark.parametrize("query,expected", sorted(_EXPECTED_FIRST.items()))
def test_a_real_word_finds_the_right_thing_first(qapp, main_window, query, expected):
    ordered = rank(query, main_window._collect_commands())

    assert ordered, f"{query!r} finds nothing at all"
    assert ordered[0].label == expected, (
        f"{query!r} -> {[c.label for c in ordered[:3]]}"
    )


def test_a_calculators_own_tags_are_searchable(qapp, main_window):
    """45 of the 58 calculators carry tags and the palette ignored every
    one. Derived from the registry, so this needs no list of its own --
    and `screening` is a real tag on `regulatory_screen`."""
    ordered = rank("screening", main_window._collect_commands())

    assert "Regulatory Screen" in [c.label for c in ordered]


def test_virtual_screening_is_reachable_at_all(qapp, main_window):
    """Its only door was a button inside the Batch panel, so it was in no
    menu and therefore in no palette. A whole feature reachable only by
    already knowing where it was."""
    ordered = rank("virtual", main_window._collect_commands())

    assert "Virtual Screening..." in [c.label for c in ordered]
