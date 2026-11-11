"""Template Library dialog: search, insert, live-canvas save, user-only remove."""

from __future__ import annotations

from openchem.chem.engine import ChemistryEngine
from openchem.chem.structure_templates import molblock_for
from openchem.domain.molecule import MoleculeModel
from openchem.domain.structure_template import (
    MY_TEMPLATES_ID,
    TemplateEntry,
    TemplateKind,
)
from openchem.domain.structure_template_store import StructureTemplateStore
from openchem.ui.dialogs.template_library_dialog import TemplateLibraryDialog


class _RecordingEditor:
    def __init__(self, molblock: str = "") -> None:
        self._molecule = MoleculeModel(display_name="Benzene")
        self._molblock = molblock
        self.inserted: list[str] = []
        self.insert_error: str | None = None

    def get_molblock(self, callback) -> None:
        callback(self._molblock)

    def insert_template_molblock(self, molblock: str, callback) -> None:
        self.inserted.append(molblock)
        callback(self.insert_error)


def _dialog(tmp_path, editor=None, molblock: str = "\n  Ketcher canvas\n"):
    engine = ChemistryEngine()
    store = StructureTemplateStore(tmp_path)
    host = editor or _RecordingEditor(molblock)
    dialog = TemplateLibraryDialog(host, engine, store=store)
    return dialog, host, store, engine


def test_shipped_categories_are_listed(qapp, tmp_path):
    dialog, _host, _store, _engine = _dialog(tmp_path)
    titles = [dialog._categories.item(i).text() for i in range(dialog._categories.count())]
    assert any(text.startswith("Rings") for text in titles)
    assert any("Amino" in text for text in titles)
    assert any("My Templates" in text for text in titles)


def test_global_search_is_not_limited_to_the_selected_category(qapp, tmp_path):
    dialog, _host, _store, _engine = _dialog(tmp_path)
    dialog._categories.setCurrentRow(0)
    dialog._search.setText("adenine")
    names = [dialog._templates.item(i).text().casefold() for i in range(dialog._templates.count())]
    assert names and any("adenine" in name for name in names)


def test_insert_hands_the_molblock_to_the_editor(qapp, tmp_path):
    dialog, host, _store, _engine = _dialog(tmp_path)
    dialog._search.setText("pyridine")
    assert dialog._templates.count() >= 1
    dialog._insert.click()
    assert host.inserted and "N" in host.inserted[0]
    assert dialog._status.text() == "Inserted."


def test_add_current_drawing_uses_the_live_molblock(qapp, tmp_path):
    live = _molblock("CCO")
    dialog, host, store, _engine = _dialog(tmp_path, molblock=live)
    dialog._name_for_save = "Ethanol from canvas"
    dialog._save.click()
    names = [entry.name for entry in store.entries()]
    assert names == ["Ethanol from canvas"]
    saved = store.entries()[0]
    assert saved.category_id == MY_TEMPLATES_ID
    assert saved.molblock
    assert saved.smiles is None
    assert host._molblock == live


def test_remove_is_disabled_for_shipped_entries(qapp, tmp_path):
    dialog, _host, _store, _engine = _dialog(tmp_path)
    dialog._search.setText("benzene")
    dialog._templates.setCurrentRow(0)
    assert not dialog._remove.isEnabled()


def test_a_user_template_can_be_removed(qapp, tmp_path):
    dialog, _host, store, _engine = _dialog(tmp_path)
    store.add_entry(
        TemplateEntry(
            id=f"{MY_TEMPLATES_ID}:keep",
            name="Keep me",
            category_id=MY_TEMPLATES_ID,
            molblock=_molblock("c1ccccc1"),
            kind=TemplateKind.COMPLETE_MOLECULE,
        )
    )
    dialog.refresh()
    dialog._search.setText("Keep me")
    assert dialog._remove.isEnabled()
    dialog._remove.click()
    assert store.entries() == ()


def _molblock(smiles: str) -> str:
    return molblock_for(TemplateEntry(id="x", name="x", category_id="x", smiles=smiles), ChemistryEngine())
