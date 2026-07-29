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

    def export_file(
        self, model: MoleculeModel, path: Path, progress: ProgressHandle | None = None
    ) -> None:
        progress = progress or ProgressHandle()
        fmt = path.suffix.lstrip(".").lower()
        progress.report(0.0, f"Exporting {path.name}")
        if fmt in RDKIT_EXPORT_FORMATS:
            self._rdkit_exporter.export_file(model, path, fmt)
        elif fmt in OPENBABEL_FALLBACK_FORMATS:
            self._openbabel_exporter.export_file(model, path, fmt)
        else:
            raise UnsupportedFormatError(f"No exporter registered for .{fmt}")
        progress.report(1.0, "Done")
        logger.info("Exported molecule %s to %s", model.uuid, path)
