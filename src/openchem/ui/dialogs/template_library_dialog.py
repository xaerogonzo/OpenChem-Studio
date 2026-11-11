"""Browse shipped and user structure templates and insert them on the canvas."""

from __future__ import annotations

import uuid
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from openchem.chem.engine import ChemistryEngine, InvalidStructureError
from openchem.chem.structure_templates import import_mol_file, load_shipped, molblock_for
from openchem.domain.structure_template import (
    MY_TEMPLATES_ID,
    TemplateCategory,
    TemplateEntry,
    TemplateError,
    TemplateKind,
    TemplateOrigin,
)
from openchem.domain.structure_template_store import StructureTemplateStore
from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip
from openchem.ui.theme import paper

_TOPIC = "templates"
_ANCHOR = "template-library"


def _help(help_id: str, text: str, tier: int = 1) -> HelpTooltip:
    return HelpTooltip(text=text, tier=tier, help_id=help_id, topic=_TOPIC, help_anchor=_ANCHOR)


class TemplateLibraryDialog(QDialog):
    """Modeless library: insert, save the current drawing, import a category."""

    def __init__(
        self,
        editor,
        engine: ChemistryEngine,
        parent: QWidget | None = None,
        store: StructureTemplateStore | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Template Library")
        self.setObjectName("TemplateLibraryDialog")
        self.setModal(False)
        self.resize(720, 480)
        self._editor = editor
        self._engine = engine
        self._store = store if store is not None else StructureTemplateStore()
        self._shipped = load_shipped(engine)
        self._entries_by_id: dict[str, TemplateEntry] = {}
        self._name_for_save: str | None = None
        self._status = QLabel(self)
        self._status.setWordWrap(True)
        self._search = QLineEdit(self)
        self._search.setPlaceholderText("Search names, tags, descriptions")
        apply_help_tooltip(self._search, _help(
            "templates.search",
            "Filters every category at once by name, tag or description.",
        ))
        self._search.textChanged.connect(self._refill_templates)
        self._categories = QListWidget(self)
        self._categories.setObjectName("templateCategories")
        apply_help_tooltip(self._categories, _help(
            "templates.categories",
            "Shipped catalogs and your own categories. Titles can match; ids do not.",
        ))
        self._categories.currentItemChanged.connect(self._refill_templates)
        self._templates = QListWidget(self)
        self._templates.setObjectName("templateEntries")
        apply_help_tooltip(self._templates, _help(
            "templates.entries",
            "Templates in the selected category, or every match when a search is typed.",
        ))
        self._templates.currentItemChanged.connect(self._preview)
        self._preview_view = QSvgWidget(self)
        paper(self._preview_view)
        self._preview_view.setMinimumHeight(160)
        self._target = QLabel(self)
        self._insert = QPushButton("Insert", self)
        apply_help_tooltip(self._insert, _help(
            "templates.insert",
            "Places the selected complete molecule to the right of the current drawing. One undo step.",
            tier=2,
        ))
        self._insert.clicked.connect(self._on_insert)
        self._save = QPushButton("Add current drawing to My Templates", self)
        apply_help_tooltip(self._save, _help(
            "templates.save_drawing",
            "Stores the live 2D canvas, not the last saved molecule, as a user template.",
            tier=2,
        ))
        self._save.clicked.connect(self._on_save)
        self._remove = QPushButton("Remove", self)
        apply_help_tooltip(self._remove, _help(
            "templates.remove",
            "Deletes a user template. Shipped catalog entries cannot be removed.",
        ))
        self._remove.clicked.connect(self._on_remove)
        self._add_category = QPushButton("Add category…", self)
        apply_help_tooltip(self._add_category, _help(
            "templates.add_category",
            "Imports .mol, .sdf or a folder of those into a new user category in the application data folder.",
            tier=2,
        ))
        self._add_category.clicked.connect(self._on_add_category)
        lists = QHBoxLayout()
        lists.addWidget(self._categories, 1)
        lists.addWidget(self._templates, 2)
        lists.addWidget(self._preview_view, 2)
        buttons = QHBoxLayout()
        buttons.addWidget(self._insert)
        buttons.addWidget(self._save)
        buttons.addWidget(self._remove)
        buttons.addWidget(self._add_category)
        layout = QVBoxLayout(self)
        layout.addWidget(self._target)
        layout.addWidget(self._search)
        layout.addLayout(lists)
        layout.addLayout(buttons)
        layout.addWidget(self._status)
        self.refresh()

    def refresh(self) -> None:
        self._shipped = load_shipped(self._engine)
        self._store.load()
        self._categories.blockSignals(True)
        self._categories.clear()
        for category in (*self._shipped, *self._store.categories()):
            item = QListWidgetItem(f"{category.title} ({len(category.entries)})")
            item.setData(Qt.ItemDataRole.UserRole, category.id)
            self._categories.addItem(item)
        self._categories.blockSignals(False)
        if self._categories.count() and self._categories.currentRow() < 0:
            self._categories.setCurrentRow(0)
        self._refill_templates()
        self._update_target()

    def _all_categories(self) -> tuple[TemplateCategory, ...]:
        return (*self._shipped, *self._store.categories())

    def _refill_templates(self) -> None:
        query = self._search.text()
        current = self._categories.currentItem()
        category_id = current.data(Qt.ItemDataRole.UserRole) if current else None
        self._templates.blockSignals(True)
        self._templates.clear()
        self._entries_by_id = {}
        for category in self._all_categories():
            if not query.strip() and category.id != category_id:
                continue
            for entry in category.entries:
                if not entry.matches(query):
                    continue
                self._entries_by_id[entry.id] = entry
                label = entry.name if not query.strip() else f"{entry.name} ({category.title})"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, entry.id)
                self._templates.addItem(item)
        self._templates.blockSignals(False)
        if self._templates.count():
            self._templates.setCurrentRow(0)
        else:
            self._preview()
        self._sync_buttons()
        self._update_target()

    def _selected_entry(self) -> TemplateEntry | None:
        item = self._templates.currentItem()
        if item is None:
            return None
        return self._entries_by_id.get(item.data(Qt.ItemDataRole.UserRole))

    def _preview(self) -> None:
        entry = self._selected_entry()
        self._sync_buttons()
        if entry is None:
            self._preview_view.load(QByteArray())
            return
        try:
            molblock = molblock_for(entry, self._engine)
            svg = self._engine.render_2d_svg(molblock, {}, {})
        except (TemplateError, InvalidStructureError) as exc:
            self._status.setText(str(exc))
            self._preview_view.load(QByteArray())
            return
        self._preview_view.load(QByteArray(svg.encode("utf-8")))
        self._status.clear()

    def _sync_buttons(self) -> None:
        entry = self._selected_entry()
        self._insert.setEnabled(entry is not None)
        user = entry is not None and entry.category_id.startswith("user:")
        self._remove.setEnabled(user)

    def _update_target(self) -> None:
        molecule = getattr(self._editor, "_molecule", None)
        name = molecule.display_name if molecule is not None else "(no molecule selected)"
        self._target.setText(f"Inserts into: {name}")

    def _on_insert(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        self._update_target()
        try:
            molblock = molblock_for(entry, self._engine)
        except TemplateError as exc:
            self._status.setText(str(exc))
            return
        self._insert.setEnabled(False)
        self._editor.insert_template_molblock(molblock, self._insert_finished)

    def _insert_finished(self, error: str | None) -> None:
        self._insert.setEnabled(self._selected_entry() is not None)
        self._status.setText(error or "Inserted.")

    def _on_save(self) -> None:
        self._editor.get_molblock(self._save_molblock)

    def _save_molblock(self, molblock: str | None) -> None:
        if not molblock or not molblock.strip():
            self._status.setText("The canvas is empty.")
            return
        if self._name_for_save is not None:
            name = self._name_for_save
            self._name_for_save = None
            ok = bool(name.strip())
        else:
            name, ok = QInputDialog.getText(self, "My Templates", "Name:")
        if not ok or not name.strip():
            return
        entry = TemplateEntry(
            id=f"{MY_TEMPLATES_ID}:{uuid.uuid4().hex}",
            name=name.strip(),
            category_id=MY_TEMPLATES_ID,
            molblock=molblock,
            kind=TemplateKind.COMPLETE_MOLECULE,
        )
        try:
            molblock_for(entry, self._engine)
            self._store.add_entry(entry)
        except TemplateError as exc:
            self._status.setText(str(exc))
            return
        self.refresh()
        self._status.setText(f"Saved {entry.name}.")

    def _on_remove(self) -> None:
        entry = self._selected_entry()
        if entry is None or not entry.category_id.startswith("user:"):
            return
        try:
            self._store.remove_entry(entry.category_id, entry.id)
        except TemplateError as exc:
            self._status.setText(str(exc))
            return
        self.refresh()

    def _on_add_category(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, "Import templates", "", "Structure files (*.sdf *.mol *.mdl);;All files (*)"
        )
        if not path:
            folder = QFileDialog.getExistingDirectory(self, "Import a folder of templates")
            if not folder:
                return
            sources = list(Path(folder).glob("*.sdf")) + list(Path(folder).glob("*.mol"))
            title = Path(folder).name
        else:
            sources = [Path(path)]
            title = Path(path).stem
        name, ok = QInputDialog.getText(self, "New category", "Category name:", text=title)
        if not ok or not name.strip():
            return
        category_id = f"user:{uuid.uuid4().hex}"
        added: list[TemplateEntry] = []
        skipped: list[tuple[str, str]] = []
        for source in sources:
            more, bad = import_mol_file(source, category_id, self._engine)
            added.extend(more)
            skipped.extend(bad)
        if not added:
            self._status.setText("Nothing could be imported:\n" + "\n".join(f"{n}: {r}" for n, r in skipped))
            return
        category = TemplateCategory(
            id=category_id,
            title=name.strip(),
            origin=TemplateOrigin.USER,
            description=f"Imported {len(added)} structure(s).",
            entries=tuple(added),
        )
        try:
            self._store.add_category(category)
        except TemplateError as exc:
            self._status.setText(str(exc))
            return
        self.refresh()
        summary = f"Imported {len(added)}."
        if skipped:
            summary += " Skipped: " + "; ".join(f"{n}: {r}" for n, r in skipped)
        self._status.setText(summary)
        QMessageBox.information(self, "Import", summary)
