from __future__ import annotations

import ai_assistant.context_builder as context_builder_mod

from openchem.domain.common import CacheState
from openchem.domain.descriptor import DescriptorValue
from openchem.events.events import DescriptorComputed, MoleculeSelected, MoleculeSnapshotUpdated


def _snapshot(**overrides):
    defaults = dict(
        molecule_uuid="mol-1",
        display_name="A",
        canonical_smiles=None,
        inchi=None,
        inchikey=None,
        conformer_count=0,
        lowest_conformer_energy=None,
    )
    defaults.update(overrides)
    return MoleculeSnapshotUpdated(**defaults)


def test_context_text_before_any_molecule():
    cache = context_builder_mod.MoleculeContextCache()
    assert not cache.has_molecule()
    assert "No molecule" in cache.build_context_text()


def test_context_text_includes_snapshot_and_descriptors():
    cache = context_builder_mod.MoleculeContextCache()
    cache.on_snapshot_updated(
        _snapshot(
            display_name="Aspirin",
            canonical_smiles="CC(=O)Oc1ccccc1C(=O)O",
            inchikey="BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
            conformer_count=2,
            lowest_conformer_energy=5.5,
        )
    )
    cache.on_descriptor_computed(
        DescriptorComputed(
            descriptor=DescriptorValue(
                descriptor_id="mol_wt",
                name="Molecular Weight",
                units="g/mol",
                category="physicochemical",
                provider="rdkit",
                molecule_uuid="mol-1",
                value=180.16,
                cache_state=CacheState.COMPLETED,
            )
        )
    )

    text = cache.build_context_text()
    assert "Aspirin" in text
    assert "CC(=O)Oc1ccccc1C(=O)O" in text
    assert "Molecular Weight: 180.16 g/mol" in text
    assert "Conformers: 2 generated, lowest energy 5.50 kcal/mol" in text


def test_descriptor_for_different_molecule_is_ignored():
    cache = context_builder_mod.MoleculeContextCache()
    cache.on_snapshot_updated(_snapshot())
    cache.on_descriptor_computed(
        DescriptorComputed(
            descriptor=DescriptorValue(
                descriptor_id="x",
                name="X",
                units="",
                category="",
                provider="p",
                molecule_uuid="mol-OTHER",
                value=1,
                cache_state=CacheState.COMPLETED,
            )
        )
    )
    assert "Computed descriptors" not in cache.build_context_text()


def test_incomplete_descriptor_is_ignored():
    cache = context_builder_mod.MoleculeContextCache()
    cache.on_snapshot_updated(_snapshot())
    cache.on_descriptor_computed(
        DescriptorComputed(
            descriptor=DescriptorValue(
                descriptor_id="x",
                name="X",
                units="",
                category="",
                provider="rdkit",
                molecule_uuid="mol-1",
                value=None,
                cache_state=CacheState.RUNNING,
            )
        )
    )
    assert "Computed descriptors" not in cache.build_context_text()


def test_explicit_deselection_clears_cache():
    cache = context_builder_mod.MoleculeContextCache()
    cache.on_snapshot_updated(_snapshot())
    assert cache.has_molecule()

    cache.on_molecule_selected(MoleculeSelected(molecule_uuid=None))
    assert not cache.has_molecule()


def test_selecting_another_molecule_does_not_clear_by_itself():
    """MainWindow always follows a non-None MoleculeSelected with a
    MoleculeSnapshotUpdated from inside the same handler; the cache must
    not race that by also clearing on MoleculeSelected itself."""
    cache = context_builder_mod.MoleculeContextCache()
    cache.on_snapshot_updated(_snapshot())

    cache.on_molecule_selected(MoleculeSelected(molecule_uuid="mol-2"))
    assert cache.has_molecule()
