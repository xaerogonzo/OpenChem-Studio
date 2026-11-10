"""User template library: isolated data root, atomic writes, import refusals."""

from __future__ import annotations

from pathlib import Path

import pytest

from openchem.chem.engine import ChemistryEngine
from openchem.chem.structure_templates import import_mol_file, molblock_for
from openchem.domain.structure_template import (
    MY_TEMPLATES_ID,
    TemplateCategory,
    TemplateEntry,
    TemplateError,
    TemplateOrigin,
)
from openchem.domain.structure_template_store import StructureTemplateStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCHEM_DATA_ROOT", str(tmp_path))
    return StructureTemplateStore(tmp_path)


def test_a_missing_library_starts_with_empty_my_templates(store, tmp_path):
    assert [c.id for c in store.categories()] == [MY_TEMPLATES_ID]
    assert store.entries() == ()
    assert not (tmp_path / "structure_templates" / "library.json").exists()


def test_adding_the_current_drawing_round_trips(store):
    engine = ChemistryEngine()
    molblock = molblock_for(
        TemplateEntry(id="t", name="t", category_id=MY_TEMPLATES_ID, smiles="c1ccccc1"),
        engine,
    )
    store.add_entry(
        TemplateEntry(
            id="user:my_templates:benzene",
            name="Benzene sketch",
            category_id=MY_TEMPLATES_ID,
            molblock=molblock,
        )
    )
    again = StructureTemplateStore(store._root)
    [entry] = again.entries()
    assert entry.name == "Benzene sketch"
    assert entry.molblock
    assert "c1ccccc1" in engine.molblock_to_smiles(entry.molblock) or engine.molblock_to_smiles(
        entry.molblock
    ).lower().startswith("c1")


def test_duplicate_ids_are_refused(store):
    entry = TemplateEntry(
        id="user:my_templates:one",
        name="One",
        category_id=MY_TEMPLATES_ID,
        smiles="C",
    )
    store.add_entry(entry)
    with pytest.raises(TemplateError, match="duplicate"):
        store.add_entry(entry)


def test_a_populated_category_cannot_be_removed(store):
    category = TemplateCategory(
        id="user:extra",
        title="Extra",
        origin=TemplateOrigin.USER,
        entries=(
            TemplateEntry(id="user:extra:a", name="A", category_id="user:extra", smiles="C"),
        ),
    )
    store.add_category(category)
    with pytest.raises(TemplateError, match="still has templates"):
        store.remove_category("user:extra")
    store.remove_entry("user:extra", "user:extra:a")
    store.remove_category("user:extra")
    assert store.category("user:extra") is None


def test_my_templates_cannot_be_removed(store):
    with pytest.raises(TemplateError, match="My Templates"):
        store.remove_category(MY_TEMPLATES_ID)


def test_corrupt_json_is_a_named_refusal(tmp_path):
    path = tmp_path / "structure_templates" / "library.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(TemplateError, match="could not be read"):
        StructureTemplateStore(tmp_path)


def test_user_json_cannot_claim_to_be_shipped(tmp_path):
    path = tmp_path / "structure_templates" / "library.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"version": 1, "categories": [{"id": "rings", "title": "Rings", "origin": "shipped", "entries": []}]}',
        encoding="utf-8",
    )
    with pytest.raises(TemplateError, match="shipped"):
        StructureTemplateStore(tmp_path)


def test_importing_an_sdf_keeps_good_records_and_names_the_rest(tmp_path):
    from rdkit import Chem

    sdf = tmp_path / "pair.sdf"
    engine = ChemistryEngine()
    mol = engine.mol_from_smiles("CCO")
    mol.SetProp("_Name", "ethanol")
    dummy = engine.mol_from_smiles("*C")
    dummy.SetProp("_Name", "wildcard")
    writer = Chem.SDWriter(str(sdf))
    writer.write(mol)
    writer.write(dummy)
    writer.close()
    added, skipped = import_mol_file(sdf, "user:extra", engine)
    assert len(added) == 1
    assert added[0].name == "ethanol"
    assert skipped
    reason = skipped[0][1].casefold()
    assert "dummy" in reason or "wildcard" in reason


def test_tests_never_touch_the_real_data_root(store, tmp_path, monkeypatch):
    from openchem.paths import DATA_ROOT_ENV_VAR, data_root

    assert data_root() == tmp_path
    monkeypatch.delenv(DATA_ROOT_ENV_VAR, raising=False)
    # After deleting the env, this process would see the developer root.
    # The store fixture already wrote only under tmp_path.
    assert store.path.is_relative_to(tmp_path)
