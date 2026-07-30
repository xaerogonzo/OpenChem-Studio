from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QThreadPool

from openchem.chem.engine import ChemistryEngine
from openchem.domain.common import CacheState
from openchem.domain.molecule import MoleculeModel
from openchem.events.base import EventBus
from openchem.events.events import ConformerJobStateChanged
from openchem.plugins.interfaces import ConformerProvider, DescriptorProvider, Exporter, Importer
from openchem.services.conformer_service import ConformerService
from openchem.services.descriptor_service import DescriptorService
from openchem.services.export_service import ExportService, UnsupportedFormatError as ExportUnsupportedFormatError
from openchem.services.import_service import ImportService, UnsupportedFormatError as ImportUnsupportedFormatError


class _FakeDescriptorProvider(DescriptorProvider):
    provider_id = "fake"

    def descriptor_ids(self) -> list[str]:
        return ["fake.x"]

    def compute(self, mol, molecule_uuid):
        return []


def test_descriptor_service_register_unregister():
    service = DescriptorService(EventBus(), ChemistryEngine())
    before = len(service._providers)

    provider = _FakeDescriptorProvider()
    service.register_provider(provider)
    assert len(service._providers) == before + 1

    service.unregister_provider("fake")
    assert len(service._providers) == before


class _FakeConformerProvider(ConformerProvider):
    provider_id = "fakeconf"

    def generate_conformers(self, mol, num_conformers, optimize, on_progress=None):
        return []


def _drain(qapp, iterations: int = 30) -> None:
    QThreadPool.globalInstance().waitForDone(5000)
    for _ in range(iterations):
        qapp.processEvents()


def test_conformer_service_register_unregister_and_provider_id_selection(qapp):
    engine = ChemistryEngine()
    bus = EventBus()
    service = ConformerService(bus, engine)
    service.register_provider(_FakeConformerProvider())
    assert "fakeconf" in service._providers

    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CCO")

    states: list[CacheState] = []
    bus.subscribe(ConformerJobStateChanged, lambda e: states.append(e.state))
    service.request_conformers(model, 1, False, provider_id="fakeconf")
    _drain(qapp)

    assert CacheState.COMPLETED in states

    service.unregister_provider("fakeconf")
    assert "fakeconf" not in service._providers


def test_conformer_service_unknown_provider_id_fails(qapp):
    engine = ChemistryEngine()
    bus = EventBus()
    service = ConformerService(bus, engine)
    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CCO")

    states: list[CacheState] = []
    bus.subscribe(ConformerJobStateChanged, lambda e: states.append(e.state))
    service.request_conformers(model, 1, False, provider_id="doesnotexist")
    _drain(qapp, iterations=5)

    assert states == [CacheState.FAILED]


class _FakeImporter(Importer):
    def supported_formats(self) -> set[str]:
        return {"fakefmt"}

    def import_file(self, path: Path):
        return [MoleculeModel(display_name="fake")]


def test_import_service_register_unregister(tmp_path: Path):
    service = ImportService(ChemistryEngine())
    importer = _FakeImporter()
    service.register_importer(importer)

    path = tmp_path / "test.fakefmt"
    path.write_text("data")
    models = service.import_file(path)
    assert models[0].display_name == "fake"

    service.unregister_importer(importer)
    with pytest.raises(ImportUnsupportedFormatError):
        service.import_file(path)


class _FakeExporter(Exporter):
    def supported_formats(self) -> set[str]:
        return {"fakefmt"}

    def export_file(self, model, path: Path, fmt: str) -> None:
        path.write_text("exported")


def test_export_service_register_unregister(tmp_path: Path):
    service = ExportService(ChemistryEngine())
    exporter = _FakeExporter()
    service.register_exporter(exporter)

    model = MoleculeModel()
    path = tmp_path / "test.fakefmt"
    service.export_file(model, path)
    assert path.read_text() == "exported"

    service.unregister_exporter(exporter)
    with pytest.raises(ExportUnsupportedFormatError):
        service.export_file(model, path)
