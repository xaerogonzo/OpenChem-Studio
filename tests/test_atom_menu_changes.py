"""Changing one atom from the right-click menu: its element, its charge, or deleting it.

Ketcher's own menu had these on an atom and ours did not, so replacing its menu took them away.
The first attempt armed Ketcher's atom and charge tools and delivered synthetic clicks: the tool
armed and nothing changed, because its tools read pointer state a synthetic event does not carry.
The change is now an edit of the STRUCTURE made by the chemistry engine and pushed as an
`EditStructureCommand` -- one undo entry, recomputed like any deliberate change -- which is also
what the project's own rule says a structure-modifying action must be.

`benchmarks/visual/atom_menu_changes.json` drives the real menu in the running application.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from openchem.chem.engine import ChemistryEngine, StructureEditError
from openchem.domain.molecule import MoleculeModel


def _molblock(smiles: str) -> str:
    return ChemistryEngine().mol_to_molblock(ChemistryEngine().mol_from_smiles(smiles))


def _smiles(molblock: str) -> str:
    return Chem.MolToSmiles(ChemistryEngine().mol_from_molblock(molblock))


ENGINE = ChemistryEngine()


# --- the engine ----------------------------------------------------------------------------


def test_an_oxygen_turned_nitrogen_gains_the_hydrogen_nitrogen_needs():
    """Ethanol's oxygen (atom 3) as nitrogen is ethylamine, not a two-valent nitrogen radical."""
    assert _smiles(ENGINE.edit_atom(_molblock("CCO"), 2, "element", "N")) == "CCN"


def test_a_charge_is_added_to_the_charge_the_atom_has():
    charged = ENGINE.edit_atom(_molblock("CCN"), 2, "charge", "+1")
    assert _smiles(charged) == "CC[NH3+]"


def test_a_negative_charge_and_a_positive_one_cancel():
    plus = ENGINE.edit_atom(_molblock("CCO"), 2, "charge", "+1")
    back = ENGINE.edit_atom(plus, 2, "charge", "-1")
    assert _smiles(back) == "CCO"


def test_deleting_an_atom_removes_it_and_its_bonds():
    assert _smiles(ENGINE.edit_atom(_molblock("CCO"), 2, "delete")) == "CC"


def test_the_other_atoms_keep_their_coordinates_after_a_change():
    before = ENGINE.mol_from_molblock(_molblock("CCO"))
    after = ENGINE.mol_from_molblock(ENGINE.edit_atom(_molblock("CCO"), 2, "element", "N"))
    for index in (0, 1):
        a, b = before.GetConformer().GetAtomPosition(index), after.GetConformer().GetAtomPosition(index)
        assert (a.x, a.y) == pytest.approx((b.x, b.y)), "an edit must not re-lay-out the drawing"


def test_a_change_that_would_not_be_a_molecule_is_refused_with_the_reason():
    """The centre of neopentane as nitrogen is a four-bonded neutral nitrogen."""
    with pytest.raises(StructureEditError) as raised:
        ENGINE.edit_atom(_molblock("CC(C)(C)C"), 1, "element", "N")
    assert "atom 2" in str(raised.value) and "not a valid structure" in str(raised.value)


def test_an_unknown_element_is_refused():
    with pytest.raises(StructureEditError, match="not an element"):
        ENGINE.edit_atom(_molblock("CCO"), 2, "element", "Zz")


def test_an_atom_that_is_not_there_is_refused():
    with pytest.raises(StructureEditError, match="no atom 9"):
        ENGINE.edit_atom(_molblock("CCO"), 8, "delete")


def test_the_only_atom_cannot_be_deleted():
    with pytest.raises(StructureEditError, match="only atom"):
        ENGINE.edit_atom(_molblock("C"), 0, "delete")


def test_an_unknown_change_is_refused():
    with pytest.raises(StructureEditError, match="Unknown"):
        ENGINE.edit_atom(_molblock("CCO"), 0, "explode")


def test_an_isotope_is_cleared_when_the_element_changes():
    """A carbon-13 turned nitrogen must not become an impossible 13N."""
    labelled = _molblock("[13CH3]CO")
    changed = ENGINE.mol_from_molblock(ENGINE.edit_atom(labelled, 0, "element", "N"))
    assert changed.GetAtomWithIdx(0).GetIsotope() == 0


# --- the menu ------------------------------------------------------------------------------


@pytest.fixture
def window(qapp, tmp_path):
    from openchem.app.main_window import MainWindow
    from openchem.app.session import SessionManager
    from openchem.app.settings import Settings
    from openchem.bootstrap import build_service_container
    from openchem.domain.project import ProjectModel

    services = build_service_container()
    settings = Settings(services.event_bus)
    settings.set("plugins/project_directory", str(tmp_path / "none"))
    settings.set("plugins/user_directory", str(tmp_path / "none2"))
    session = SessionManager()
    built = MainWindow(services, settings, session)
    molecule = MoleculeModel(display_name="Ethanol")
    services.chemistry_engine.set_structure_from_smiles(molecule, "CCO")
    session.set_project(ProjectModel(molecules=[molecule]))
    session.select_molecule(molecule.uuid)
    yield built, molecule
    built.close()


def _action(menu, text, submenu=None):
    holder = menu
    if submenu:
        holder = next(a.menu() for a in menu.actions() if a.menu() is not None and a.text().startswith(submenu))
    return next(a for a in holder.actions() if a.text().startswith(text))


def test_the_menu_offers_element_charge_and_delete(window):
    built, _molecule = window
    menu = built.build_atom_context_menu(2)
    labels = [a.text() for a in menu.actions() if a.text()]
    assert any(label.startswith("Change O to") for label in labels), labels
    assert "Add positive charge (+1)" in labels
    assert any(label.startswith("Add negative charge") for label in labels)
    assert "Delete this O" in labels
    submenu = next(a.menu() for a in menu.actions() if a.text().startswith("Change O to"))
    assert [a.text() for a in submenu.actions()][:4] == ["C", "N", "O", "S"]


def test_it_still_offers_the_editors_own_edit(window):
    """Kept by decision: replacing Ketcher's menu must not cost its own dialog."""
    built, _molecule = window
    labels = [a.text() for a in built.build_atom_context_menu(2).actions()]
    assert "Edit... (the editor's own)" in labels


def test_an_element_change_is_one_undo_entry_and_the_canvas_follows(window):
    built, molecule = window
    before = built._undo_stack.count()

    _action(built.build_atom_context_menu(2), "N", submenu="Change").trigger()

    assert molecule.canonical_smiles == "CCN"
    assert built._undo_stack.count() == before + 1
    built._undo_stack.undo()
    assert molecule.canonical_smiles == "CCO", "one undo puts the oxygen back"


def test_delete_and_charge_go_through_the_same_command(window):
    built, molecule = window
    _action(built.build_atom_context_menu(2), "Add positive charge").trigger()
    assert "+" in molecule.canonical_smiles
    built._undo_stack.undo()
    _action(built.build_atom_context_menu(2), "Delete this").trigger()
    assert molecule.canonical_smiles == "CC"


def test_an_invalid_change_says_why_and_changes_nothing(window):
    built, molecule = window
    services = built._services
    services.chemistry_engine.set_structure_from_smiles(molecule, "CC(C)(C)C")
    before = built._undo_stack.count()

    _action(built.build_atom_context_menu(1), "N", submenu="Change").trigger()

    assert molecule.canonical_smiles == "CC(C)(C)C"
    assert built._undo_stack.count() == before, "a refused change is not an undo entry"
    assert "not a valid structure" in built.statusBar().currentMessage()


def test_the_atom_and_the_change_travel_on_the_action_not_in_a_closure(window):
    """A menu is built per right-click, and a self-capturing lambda would root one more object
    on every one (see the note in `build_atom_context_menu`)."""
    built, _molecule = window
    menu = built.build_atom_context_menu(2)
    change = _action(menu, "Delete this")
    assert change.data() == (2, "delete", "")
