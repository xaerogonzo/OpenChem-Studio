from __future__ import annotations

import logging
from pathlib import Path

from openchem.chem.engine import ChemistryEngine
from openchem.chem.io_backends import (
    OPENBABEL_FALLBACK_FORMATS,
    RDKIT_EXPORT_FORMATS,
    Exporter,
    OpenBabelExporter,
    RDKitExporter,
)
from openchem.domain.molecule import MoleculeModel
from openchem.services.progress import ProgressHandle

logger = logging.getLogger("openchem.export")


class UnsupportedFormatError(ValueError):
    pass


class ExportService:
    """MoleculeModel -> file, RDKit-first with Open Babel fallback (mirrors ImportService)."""

    def __init__(self, engine: ChemistryEngine) -> None:
        self._rdkit_exporter: Exporter = RDKitExporter(engine)
        self._openbabel_exporter: Exporter = OpenBabelExporter(engine)
        self._extra_exporters: list[Exporter] = []

    def register_exporter(self, exporter: Exporter) -> None:
        """Register a plugin-supplied exporter, checked before the built-in
        RDKit/Open Babel backends for any format it claims."""
        self._extra_exporters.append(exporter)

    def unregister_exporter(self, exporter: Exporter) -> None:
        if exporter in self._extra_exporters:
            self._extra_exporters.remove(exporter)

    def export_file(
        self, model: MoleculeModel, path: Path, progress: ProgressHandle | None = None
    ) -> None:
        progress = progress or ProgressHandle()
        fmt = path.suffix.lstrip(".").lower()
        progress.report(0.0, f"Exporting {path.name}")
        for exporter in self._extra_exporters:
            if fmt in exporter.supported_formats():
                exporter.export_file(model, path, fmt)
                break
        else:
            if fmt in RDKIT_EXPORT_FORMATS:
                self._rdkit_exporter.export_file(model, path, fmt)
            elif fmt in OPENBABEL_FALLBACK_FORMATS:
                self._openbabel_exporter.export_file(model, path, fmt)
            else:
                raise UnsupportedFormatError(f"No exporter registered for .{fmt}")
        progress.report(1.0, "Done")
        logger.info("Exported molecule %s to %s", model.uuid, path)
