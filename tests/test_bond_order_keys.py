"""A number key over a hovered bond sets its order, as one undoable edit of the structure.

Ketcher does nothing with that key over a bond (measured: `benchmarks/visual/ketcher_hover_keys.json`),
and its bond tool cannot be driven by a synthetic event, so the application makes the change itself --
`ChemistryEngine.edit_bond` through an `EditStructureCommand`, exactly as the atom menu's changes are made.
The page only reports the hovered bond's molfile position and the order asked for.

`benchmarks/visual/bond_order_keys.json` drives the real page: a hover set through the editor's own API, the
real key, and the structure and undo stack afterwards.
"""

from __future__ import annotations

import pytest
from rdkit import Chem
from rdkit.Chem import rdDepictor

from openchem.app.settings import DRAWING_BOND_KEYS, Settings
from openchem.chem.engine import ChemistryEngine, StructureEditError
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus

ENGINE = ChemistryEngine()


def _molblock(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    rdDepictor.Compute2DCoords(mol)
    return Chem.MolToMolBlock(mol)


def _smiles(molblock: str) -> str:
    return Chem.MolToSmiles(Chem.MolFromMolBlock(molblock))


# --- the engine ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("smiles", "bond", "order", "expected"),
    [
        ("CC", 0, 2, "C=C"),
        ("CC", 0, 3, "C#C"),
        ("C=C", 0, 1, "CC"),
        ("C#C", 0, 2, "C=C"),
        ("CCO", 1, 2, "CC=O"),
        ("C1CCCCC1", 0, 2, "C1=CCCCC1"),
    ],
)
def test_a_bond_takes_the_order_asked_for(smiles, bond, order, expected):
    assert _smiles(ENGINE.edit_bond(_molblock(smiles), bond, order)) == expected


def test_the_same_order_again_changes_nothing_and_says_so_by_returning_the_input():
    block = _molblock("CC")
    assert ENGINE.edit_bond(block, 0, 1) == block


def test_only_the_chosen_bond_moves_and_no_atom_moves():
    """A kekulé benzene drawn as file bonds: one bond changes, the other five keep their type, and
    nothing is re-laid-out. Sanitising first would have made all six aromatic and rewritten them."""
    kekule = Chem.MolFromSmiles("C1=CC=CC=C1")
    rdDepictor.Compute2DCoords(kekule)
    Chem.Kekulize(kekule, clearAromaticFlags=True)
    block = Chem.MolToMolBlock(kekule, kekulize=False)
    before = Chem.MolFromMolBlock(block, sanitize=False)

    after = Chem.MolFromMolBlock(ENGINE.edit_bond(block, 0, 1), sanitize=False)

    types_before = [b.GetBondType() for b in before.GetBonds()]
    types_after = [b.GetBondType() for b in after.GetBonds()]
    assert [i for i, (x, y) in enumerate(zip(types_before, types_after, strict=True)) if x != y] == [0]
    for index in range(before.GetNumAtoms()):
        a, b = before.GetConformer().GetAtomPosition(index), after.GetConformer().GetAtomPosition(index)
        assert (a.x, a.y) == pytest.approx((b.x, b.y))


def test_a_change_that_breaks_a_valence_is_refused_with_the_reason():
    with pytest.raises(StructureEditError) as raised:
        ENGINE.edit_bond(_molblock("CC(C)(C)C"), 0, 2)
    assert "not a valid structure" in str(raised.value) and "C1-C2" in str(raised.value)


def test_a_bond_to_an_explicit_hydrogen_is_refused_rather_than_deleting_it():
    block = Chem.MolToMolBlock(Chem.AddHs(Chem.MolFromSmiles("C")))   # methane, its hydrogens explicit
    with pytest.raises(StructureEditError, match="not a valid structure"):
        ENGINE.edit_bond(block, 0, 2)


def _wedged_block() -> str:
    mol = Chem.MolFromSmiles("C[C@H](F)CC")
    rdDepictor.Compute2DCoords(mol)
    Chem.WedgeMolBonds(mol, mol.GetConformer())
    return Chem.MolToMolBlock(mol)


def test_a_wedge_bond_is_left_as_drawn():
    """RDKit turns a wedge into a chiral tag and leaves the bond's own direction NONE, so the check
    reads the molfile's stereo column; asking the parsed molecule would never see one."""
    block = _wedged_block()
    wedged = next(i for i, line in enumerate(l for l in block.splitlines()[9:] if len(l.split()) == 4)
                  if line.split()[3] != "0")
    with pytest.raises(StructureEditError, match="wedge, hash or either"):
        ENGINE.edit_bond(block, wedged, 2)


def test_a_bond_next_to_a_wedge_changes_and_the_wedge_stays():
    """Editing one bond must not strip the stereo drawing of another."""
    block = _wedged_block()
    after = ENGINE.edit_bond(block, 3, 2)      # the terminal C-C, not the wedged bond
    assert _smiles(after) == "C=C[C@H](C)F"
    assert [l.split()[3] for l in after.splitlines() if len(l) < 15 and len(l.split()) == 4].count("0") == 3, \
        "exactly one bond still carries a wedge or hash flag"


def test_a_double_bond_drawn_crossed_is_left_as_drawn():
    lines = _molblock("C=C").splitlines()
    bond_line = next(i for i, line in enumerate(lines) if line.split()[:3] == ["1", "2", "2"])
    lines[bond_line] = "  1  2  2  3"
    with pytest.raises(StructureEditError, match="wedge, hash or either"):
        ENGINE.edit_bond("\n".join(lines) + "\n", 0, 1)


def test_a_query_bond_is_left_as_drawn():
    """Bond type 5 in a molfile is "single or double", which has no order to replace."""
    lines = _molblock("CC").splitlines()
    bond_line = next(i for i, line in enumerate(lines) if line.split()[:3] == ["1", "2", "1"])
    lines[bond_line] = "  1  2  5  0"
    with pytest.raises(StructureEditError, match="query bond"):
        ENGINE.edit_bond("\n".join(lines) + "\n", 0, 2)


def test_an_aromatic_bond_is_left_as_drawn():
    """Bond type 4 is aromatic; its order is not a number to set."""
    lines = _molblock("CC").splitlines()
    bond_line = next(i for i, line in enumerate(lines) if line.split()[:3] == ["1", "2", "1"])
    lines[bond_line] = "  1  2  4  0"
    with pytest.raises(StructureEditError, match="aromatic"):
        ENGINE.edit_bond("\n".join(lines) + "\n", 0, 2)


def test_a_bond_that_is_not_there_and_an_order_that_is_not_one_are_refused():
    with pytest.raises(StructureEditError, match="no bond 6"):
        ENGINE.edit_bond(_molblock("CC"), 5, 2)
    with pytest.raises(StructureEditError, match="1, 2 or 3"):
        ENGINE.edit_bond(_molblock("CC"), 0, 4)


# --- the bridge ----------------------------------------------------------------------------------


def test_the_bridge_slot_hands_the_position_and_the_order_on():
    from openchem.ui.widgets.ketcher_editor_backend import _Bridge

    seen = []
    bridge = _Bridge(lambda _m: None, lambda: None, lambda _r, _m: None,
                     on_bond_order_key=lambda position, order: seen.append((position, order)))
    bridge.bondOrderKey(3, 2)
    assert seen == [(3, 2)]


# --- the window ----------------------------------------------------------------------------------


@pytest.fixture
def window(qapp, tmp_path):
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.bootstrap import build_service_container
    from openchem.domain.project import ProjectModel

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "none"))
    settings.set("plugins/user_directory", str(tmp_path / "none2"))
    session = SessionManager()
    built = MainWindow(services, settings, session)
    molecule = MoleculeModel(display_name="Ethane")
    services.chemistry_engine.set_structure_from_smiles(molecule, "CC")
    session.set_project(ProjectModel(molecules=[molecule]))
    session.select_molecule(molecule.uuid)
    yield built, molecule, settings
    built.close()


def test_a_key_is_one_undo_entry_and_undo_puts_the_bond_back(window):
    built, molecule, _settings = window
    before = built._undo_stack.count()

    built._on_bond_order_key(0, 2)

    assert molecule.canonical_smiles == "C=C"
    assert built._undo_stack.count() == before + 1
    built._undo_stack.undo()
    assert molecule.canonical_smiles == "CC"


def test_the_order_it_already_has_is_not_an_undo_entry(window):
    built, molecule, _settings = window
    before = built._undo_stack.count()
    built._on_bond_order_key(0, 1)
    assert molecule.canonical_smiles == "CC" and built._undo_stack.count() == before


def test_a_refused_change_says_why_and_changes_nothing(window):
    built, molecule, _settings = window
    built._services.chemistry_engine.set_structure_from_smiles(molecule, "CC(C)(C)C")
    before = built._undo_stack.count()

    built._on_bond_order_key(0, 2)

    assert molecule.canonical_smiles == "CC(C)(C)C" and built._undo_stack.count() == before
    assert "not a valid structure" in built.statusBar().currentMessage()


def test_turning_the_setting_off_tells_the_page_and_turning_it_on_tells_it_again(window):
    """The page swallows the key BEFORE Ketcher sees it, so the setting must reach the page; it is not
    read at the moment of the key."""
    built, _molecule, settings = window
    backend = built._editor._backend
    assert backend._bond_keys_enabled is True

    settings.set_preference(DRAWING_BOND_KEYS, False)
    assert backend._bond_keys_enabled is False

    settings.set_preference(DRAWING_BOND_KEYS, True)
    assert backend._bond_keys_enabled is True


def test_a_page_started_with_the_setting_off_is_told_when_it_is_ready(qapp, tmp_path):
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.bootstrap import build_service_container

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "none"))
    settings.set("plugins/user_directory", str(tmp_path / "none2"))
    settings.set_preference(DRAWING_BOND_KEYS, False)
    built = MainWindow(services, settings, SessionManager())
    try:
        assert built._editor._backend._bond_keys_enabled is False
    finally:
        built.close()


# --- the setting ---------------------------------------------------------------------------------


def test_the_drawing_page_shows_and_stores_the_setting(qapp):
    from openchem.ui.dialogs.settings_dialog import DRAWING, SettingsDialog

    settings = Settings(EventBus())
    dialog = SettingsDialog(settings, section=DRAWING)
    try:
        assert dialog._bond_keys.isChecked(), "on by default"
        dialog._bond_keys.setChecked(False)
        assert settings.preference(DRAWING_BOND_KEYS) is False
    finally:
        dialog.deleteLater()
