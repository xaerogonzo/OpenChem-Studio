from __future__ import annotations

from pathlib import Path

import pytest

from openchem.chem.engine import ChemistryEngine
from openchem.domain.molecule import MoleculeModel
from openchem.services.export_service import ExportService
from openchem.services.import_service import ImportService, UnsupportedFormatError


def test_export_then_import_mol_roundtrip(tmp_path: Path):
    engine = ChemistryEngine()
    export_service = ExportService(engine)
    import_service = ImportService(engine)

    model = MoleculeModel(display_name="Ethanol")
    engine.set_structure_from_smiles(model, "CCO")

    path = tmp_path / "ethanol.mol"
    export_service.export_file(model, path)
    imported = import_service.import_file(path)

    assert len(imported) == 1
    assert imported[0].canonical_smiles == model.canonical_smiles
    assert imported[0].inchikey == model.inchikey


def test_export_then_import_smiles_roundtrip(tmp_path: Path):
    engine = ChemistryEngine()
    export_service = ExportService(engine)
    import_service = ImportService(engine)

    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "c1ccccc1")

    path = tmp_path / "benzene.smi"
    export_service.export_file(model, path)
    imported = import_service.import_file(path)

    assert len(imported) == 1
    assert imported[0].canonical_smiles == "c1ccccc1"


def test_export_then_import_sdf_roundtrip(tmp_path: Path):
    engine = ChemistryEngine()
    export_service = ExportService(engine)
    import_service = ImportService(engine)

    model = MoleculeModel()
    engine.set_structure_from_smiles(model, "CC(=O)O")

    path = tmp_path / "acetic_acid.sdf"
    export_service.export_file(model, path)
    imported = import_service.import_file(path)

    assert len(imported) == 1
    assert imported[0].canonical_smiles == model.canonical_smiles


def test_unsupported_format_raises(tmp_path: Path):
    engine = ChemistryEngine()
    import_service = ImportService(engine)

    path = tmp_path / "unknown.xyz123"
    path.write_text("nonsense")

    with pytest.raises(UnsupportedFormatError):
        import_service.import_file(path)
