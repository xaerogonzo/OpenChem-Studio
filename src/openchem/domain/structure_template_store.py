"""The user's structure-template library: one versioned JSON file.

Imports are copied in. The original folder is provenance, not a live path.
No RDKit, no Qt.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from openchem.domain.structure_template import (
    LIBRARY_VERSION,
    MY_TEMPLATES_ID,
    MY_TEMPLATES_TITLE,
    TemplateCategory,
    TemplateEntry,
    TemplateError,
    TemplateKind,
    TemplateOrigin,
    USER_ID_PREFIX,
    parse_kind,
    parse_origin,
)
from openchem.paths import data_root

LIBRARY_FILENAME = "library.json"
LIBRARY_DIRNAME = "structure_templates"


def library_path(root: Path | None = None) -> Path:
    return (root if root is not None else data_root()) / LIBRARY_DIRNAME / LIBRARY_FILENAME


@dataclass
class ImportReport:
    """What an import kept and what it refused, for the dialog to show."""

    added: tuple[str, ...] = ()
    skipped: tuple[tuple[str, str], ...] = ()


class StructureTemplateStore:
    """My Templates and extra user categories, on disk."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root
        self._categories: dict[str, TemplateCategory] = {}
        self.load()

    @property
    def path(self) -> Path:
        return library_path(self._root)

    def categories(self) -> tuple[TemplateCategory, ...]:
        ordered = []
        if MY_TEMPLATES_ID in self._categories:
            ordered.append(self._categories[MY_TEMPLATES_ID])
        for category_id in sorted(self._categories):
            if category_id == MY_TEMPLATES_ID:
                continue
            ordered.append(self._categories[category_id])
        return tuple(ordered)

    def category(self, category_id: str) -> TemplateCategory | None:
        return self._categories.get(category_id)

    def entries(self) -> tuple[TemplateEntry, ...]:
        return tuple(entry for category in self.categories() for entry in category.entries)

    def load(self) -> None:
        path = self.path
        self._categories = {MY_TEMPLATES_ID: _empty_my_templates()}
        if not path.is_file():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TemplateError(f"the template library could not be read: {exc}") from exc
        if not isinstance(raw, dict):
            raise TemplateError("the template library is not an object")
        version = raw.get("version")
        if version != LIBRARY_VERSION:
            raise TemplateError(
                f"the template library is version {version!r}, not {LIBRARY_VERSION}"
            )
        categories = raw.get("categories")
        if not isinstance(categories, list):
            raise TemplateError("the template library has no categories list")
        loaded: dict[str, TemplateCategory] = {}
        for item in categories:
            category = _category_from_json(item)
            if category.id in loaded:
                raise TemplateError(f"duplicate category id {category.id!r}")
            loaded[category.id] = category
        if MY_TEMPLATES_ID not in loaded:
            loaded[MY_TEMPLATES_ID] = _empty_my_templates()
        self._categories = loaded

    def save(self) -> None:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": LIBRARY_VERSION,
            "categories": [_category_to_json(c) for c in self.categories()],
        }
        text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        fd, tmp = tempfile.mkstemp(prefix="library.", suffix=".json", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def add_entry(self, entry: TemplateEntry) -> None:
        if not entry.category_id.startswith(USER_ID_PREFIX):
            raise TemplateError("only a user category can take a new template")
        category = self._categories.get(entry.category_id)
        if category is None:
            raise TemplateError(f"unknown category {entry.category_id!r}")
        if any(existing.id == entry.id for existing in category.entries):
            raise TemplateError(f"duplicate template id {entry.id!r}")
        self._categories[entry.category_id] = TemplateCategory(
            id=category.id,
            title=category.title,
            origin=TemplateOrigin.USER,
            description=category.description,
            entries=category.entries + (entry,),
        )
        self.save()

    def remove_entry(self, category_id: str, entry_id: str) -> None:
        category = self._categories.get(category_id)
        if category is None or category.origin is not TemplateOrigin.USER:
            raise TemplateError("only a user template can be removed")
        kept = tuple(entry for entry in category.entries if entry.id != entry_id)
        if len(kept) == len(category.entries):
            raise TemplateError(f"no user template {entry_id!r}")
        self._categories[category_id] = TemplateCategory(
            id=category.id,
            title=category.title,
            origin=TemplateOrigin.USER,
            description=category.description,
            entries=kept,
        )
        self.save()

    def add_category(self, category: TemplateCategory) -> None:
        if category.origin is not TemplateOrigin.USER:
            raise TemplateError("only a user category can be added")
        if category.id in self._categories:
            raise TemplateError(f"duplicate category id {category.id!r}")
        self._categories[category.id] = category
        self.save()

    def remove_category(self, category_id: str) -> None:
        if category_id == MY_TEMPLATES_ID:
            raise TemplateError("My Templates cannot be removed")
        category = self._categories.get(category_id)
        if category is None or category.origin is not TemplateOrigin.USER:
            raise TemplateError("only a user category can be removed")
        if category.entries:
            raise TemplateError(
                f"{category.title} still has templates; remove them first"
            )
        del self._categories[category_id]
        self.save()


def _empty_my_templates() -> TemplateCategory:
    return TemplateCategory(
        id=MY_TEMPLATES_ID,
        title=MY_TEMPLATES_TITLE,
        origin=TemplateOrigin.USER,
        description="Structures saved from the 2D editor.",
        entries=(),
    )


def _category_from_json(raw: object) -> TemplateCategory:
    if not isinstance(raw, dict):
        raise TemplateError("a category is not an object")
    origin = parse_origin(raw.get("origin"))
    if origin is TemplateOrigin.SHIPPED:
        raise TemplateError("a user library cannot contain a shipped category")
    category_id = raw.get("id")
    title = raw.get("title")
    if not isinstance(category_id, str) or not isinstance(title, str):
        raise TemplateError("a category needs an id and a title")
    entries_raw = raw.get("entries") or []
    if not isinstance(entries_raw, list):
        raise TemplateError(f"{category_id}: entries must be a list")
    entries = tuple(_entry_from_json(item, category_id) for item in entries_raw)
    description = raw.get("description") or ""
    if not isinstance(description, str):
        description = ""
    return TemplateCategory(
        id=category_id,
        title=title,
        origin=TemplateOrigin.USER,
        description=description,
        entries=entries,
    )


def _entry_from_json(raw: object, category_id: str) -> TemplateEntry:
    if not isinstance(raw, dict):
        raise TemplateError("a template is not an object")
    tags_raw = raw.get("tags") or []
    if not isinstance(tags_raw, list) or not all(isinstance(t, str) for t in tags_raw):
        raise TemplateError("tags must be a list of strings")
    provenance = raw.get("provenance")
    if provenance is not None and not isinstance(provenance, dict):
        raise TemplateError("provenance must be an object")
    kind = parse_kind(raw.get("kind"))
    if kind is not TemplateKind.COMPLETE_MOLECULE:
        raise TemplateError(f"{raw.get('id')}: only complete molecules can be stored")
    return TemplateEntry(
        id=str(raw.get("id") or ""),
        name=str(raw.get("name") or ""),
        category_id=category_id,
        smiles=raw.get("smiles") if isinstance(raw.get("smiles"), str) else None,
        molblock=raw.get("molblock") if isinstance(raw.get("molblock"), str) else None,
        description=raw.get("description") if isinstance(raw.get("description"), str) else "",
        tags=tuple(tags_raw),
        source=raw.get("source") if isinstance(raw.get("source"), str) else "",
        kind=kind,
        provenance={str(k): str(v) for k, v in provenance.items()} if provenance else None,
    )


def _category_to_json(category: TemplateCategory) -> dict:
    return {
        "id": category.id,
        "title": category.title,
        "origin": category.origin.value,
        "description": category.description,
        "entries": [_entry_to_json(entry) for entry in category.entries],
    }


def _entry_to_json(entry: TemplateEntry) -> dict:
    payload: dict = {
        "id": entry.id,
        "name": entry.name,
        "kind": entry.kind.value,
    }
    if entry.smiles:
        payload["smiles"] = entry.smiles
    if entry.molblock:
        payload["molblock"] = entry.molblock
    if entry.description:
        payload["description"] = entry.description
    if entry.tags:
        payload["tags"] = list(entry.tags)
    if entry.source:
        payload["source"] = entry.source
    if entry.provenance:
        payload["provenance"] = dict(entry.provenance)
    return payload
