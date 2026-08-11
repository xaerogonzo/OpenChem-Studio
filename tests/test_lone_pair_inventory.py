"""What the app can actually tell you about lone pairs, and where.

*"I also think we may have lost the ability to view lone pairs, or it was
lost for me in the menus. It should at least be on the dropdown view
tab."*

**NOTHING WAS LOST: the 2D canvas has never drawn them and cannot.**
`lonePair`, `LonePair`, `lone_pair` and `electronPair` each appear **zero
times** in the vendored Ketcher bundle (`radicalElectron` appears five, so
the search is finding what is there). A View-menu item would therefore be
a control that does nothing -- the exact failure this line of work keeps
finding -- so there is deliberately no menu entry, and
`test_no_menu_entry_pretends_the_canvas_can_draw_lone_pairs` fails if one
appears.

They exist as DATA, per atom, in the Atom Inspector. This file is the
inventory of what that count is worth: every case is asserted against the
textbook number rather than against whatever the code returns, so a
regression shows up as a chemistry error and not as a diff.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.atom_report import build_atom_report
from openchem.chem.lewis import analyse

#: (case, SMILES, symbol, textbook non-bonding pairs on that atom)
#:
#: Written from the chemistry, not from a run. The one case that
#: disagreed with a first draft of this table was the CARBENE, and the
#: table was wrong rather than the code -- see the radical test below.
COUNTS = [
    ("amine N", "CN", "N", 1),
    ("ammonium N+", "C[NH3+]", "N", 0),
    ("amide N", "CC(=O)N", "N", 1),
    ("nitro N+", "C[N+](=O)[O-]", "N", 0),
    ("nitrile N", "CC#N", "N", 1),
    ("carbonyl O", "CC=O", "O", 2),
    ("ether O", "COC", "O", 2),
    ("hydroxyl O", "CO", "O", 2),
    ("alkoxide O-", "C[O-]", "O", 3),
    ("water O", "O", "O", 2),
    ("thioether S", "CSC", "S", 2),
    ("sulfoxide S", "CS(=O)C", "S", 1),
    ("sulfone S", "CS(=O)(=O)C", "S", 0),
    ("phosphine P", "CP(C)C", "P", 1),
    ("phosphine oxide P", "CP(=O)(C)C", "P", 0),
    ("pyridine N", "c1ccncc1", "N", 1),
    ("pyrrole N", "c1cc[nH]c1", "N", 1),
    ("furan O", "c1ccoc1", "O", 2),
    ("fluorine on carbon", "CF", "F", 3),
    ("chloride ion", "[Cl-]", "Cl", 4),
    ("borane B", "B(F)(F)F", "B", 0),
]

#: Atoms the arithmetic must DECLINE rather than guess at. RDKit reports
#: no defined valence for these (`GetValenceList` contains -1), and
#: running `outer - bonds - charge` anyway gives high-spin Fe(III) "two
#: lone pairs" when it is d5 with five UNPAIRED electrons.
NO_ANSWER = [
    ("iron(III)", "[Fe+3]", "Fe"),
    ("zinc(II)", "[Zn+2]", "Zn"),
    ("sodium ion", "[Na+]", "Na"),
    ("copper(II)", "[Cu+2]", "Cu"),
]


def _atom(smiles: str, symbol: str):
    mol = Chem.MolFromSmiles(smiles)
    assert mol is not None, smiles
    index = next(a.GetIdx() for a in mol.GetAtoms() if a.GetSymbol() == symbol)
    return mol, index


def _lone_pair_fact(mol, index: int):
    report = build_atom_report(mol, index)
    return next((f for f in report.facts if f.label == "Lone pairs"), None)


@pytest.mark.parametrize("case,smiles,symbol,expected", COUNTS, ids=[c[0] for c in COUNTS])
def test_the_atom_inspector_reports_the_textbook_lone_pair_count(
    case, smiles, symbol, expected
):
    """Through `build_atom_report`, which is what the panel calls -- not
    through `lewis.lone_pairs`, which is a helper the analysis guards.

    The distinction is load-bearing: `lone_pairs` answers `1` for a
    carbene while `analyse` refuses the whole molecule, so a test written
    against the helper would report a count the app never shows.
    """
    mol, index = _atom(smiles, symbol)
    fact = _lone_pair_fact(mol, index)

    assert fact is not None, f"{case}: the inspector reports no lone-pair count at all"
    assert fact.value == expected, f"{case}: {fact.value} pairs, expected {expected}"


@pytest.mark.parametrize("case,smiles,symbol", NO_ANSWER, ids=[c[0] for c in NO_ANSWER])
def test_a_metal_gets_no_lone_pair_count_rather_than_a_wrong_one(case, smiles, symbol):
    """**A refusal, not a gap.** Answering here would be worse than
    silence: the arithmetic has no way to know whether two electrons are
    a donor pair or two unpaired d electrons, and for the most common
    Lewis acids in coordination chemistry they are the latter."""
    mol, index = _atom(smiles, symbol)

    assert _lone_pair_fact(mol, index) is None


def test_an_unpaired_electron_is_refused_because_a_PAIR_is_the_whole_model():
    """The one case a naive count gets wrong, and it is refused upstream.

    `[CH2]` has two non-bonding electrons. Halving them gives "one lone
    pair", which is right for the SINGLET and wrong for the TRIPLET,
    whose two electrons are unpaired and are not a donor pair at all.
    The drawing does not say which, so `analyse` refuses the molecule
    rather than picking one -- and the inspector shows no count.
    """
    mol, index = _atom("[CH2]", "C")

    result = analyse(mol)
    assert result.refused
    assert "unpaired electron" in result.reason.lower(), result.reason
    assert "carbene" in result.reason.lower(), result.reason
    assert _lone_pair_fact(mol, index) is None


def test_a_metal_with_no_lewis_role_still_gets_no_count(monkeypatch):
    """The guard on the fallback, asserted directly because nothing
    reaches it today.

    Every metal the analysis accepts is classified as an ACCEPTOR, so it
    has a Lewis site and never falls through to the raw arithmetic; the
    ones it does not accept (`C[Fe]C`) are refused outright and return
    earlier still. Measured, both ways -- so a mutation that drops the
    `pairs is None` check survives every end-to-end test in this file.

    That makes it a question about where to assert, not dead code: the
    acceptor rules are heuristics, and one stopping matching some metal
    is an ordinary future change. What must not happen then is iron
    reported as having a definite number of lone pairs -- it is d5 with
    five UNPAIRED electrons, and "two pairs" would be a fabricated answer
    rather than a missing one.
    """
    import openchem.chem.lewis as lewis

    mol, index = _atom("[Fe+3]", "Fe")

    # **CAPTURED BEFORE THE PATCH.** The first version of this called
    # `lewis.analyse` from inside the replacement, which by then WAS the
    # replacement -- so it recursed, `build_atom_report` swallowed the
    # RecursionError the way it swallows any collector failure, and the
    # test passed on both arms of the mutation it exists to catch.
    original = lewis.analyse

    def no_sites(m, molecule_uuid=""):
        result = original(m, molecule_uuid)
        return type(result)(
            molecule_uuid=result.molecule_uuid,
            sites=(),
            summary=result.summary,
            assumptions=result.assumptions,
        )

    monkeypatch.setattr(lewis, "analyse", no_sites)

    report = build_atom_report(mol, index)
    # The collector really RAN -- otherwise this asserts on a report the
    # exception handler emptied, which is how the first version passed.
    assert report.facts, "no facts at all: the collector was skipped"
    assert not any(f.label == "Lone pairs" for f in report.facts)


def test_the_count_follows_the_CHARGE_not_just_the_element():
    """The pair of cases that a per-element lookup table would get wrong,
    asserted together so the table cannot creep back in: the same nitrogen
    and the same oxygen, differing only in formal charge."""
    neutral_n = _lone_pair_fact(*_atom("CN", "N"))
    cationic_n = _lone_pair_fact(*_atom("C[NH3+]", "N"))
    neutral_o = _lone_pair_fact(*_atom("CO", "O"))
    anionic_o = _lone_pair_fact(*_atom("C[O-]", "O"))

    assert (neutral_n.value, cationic_n.value) == (1, 0)
    assert (neutral_o.value, anionic_o.value) == (2, 3)


def test_no_menu_entry_pretends_the_canvas_can_draw_lone_pairs(qapp, tmp_path):
    """**Ketcher cannot draw them, so there is no control that says it
    can.** A "Show Lone Pairs" item that only pointed at another panel
    would be a control that does nothing, which is the failure this whole
    line of work keeps finding. The count lives in the Atom Inspector,
    which is a panel you open rather than a toggle that lies.
    """
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "none"))
    settings.set("plugins/user_directory", str(tmp_path / "none"))
    window = MainWindow(services, settings, SessionManager())

    labels = []

    def walk(menu):
        for action in menu.actions():
            labels.append(action.text())
            if action.menu() is not None:
                walk(action.menu())

    for menu_action in window.menuBar().actions():
        if menu_action.menu() is not None:
            walk(menu_action.menu())

    offenders = [label for label in labels if "lone pair" in label.lower()]
    assert not offenders, (
        f"{offenders} promises something the 2D canvas cannot draw -- "
        "'lonePair' appears zero times in the Ketcher bundle"
    )
    window.close()
