from __future__ import annotations

import logging
from pathlib import Path

from openchem.chem.engine import ChemistryEngine
from openchem.chem.io_backends import (
    OPENBABEL_FALLBACK_FORMATS,
    RDKIT_IMPORT_FORMATS,
    Importer,
    OpenBabelImporter,
    RDKitImporter,
)
from openchem.domain.molecule import MoleculeModel
from openchem.services.progress import ProgressHandle

logger = logging.getLogger("openchem.import")


class UnsupportedFormatError(ValueError):
    pass


class ImportService:
    """File -> MoleculeModel(s).

    Routes RDKit-first, falling back to Open Babel only for formats RDKit
    doesn't cover well (see `openchem.chem.io_backends`). UI code should call
    this instead of touching `chem.io_backends` directly.
    """

    def __init__(self, engine: ChemistryEngine) -> None:
        self._rdkit_importer: Importer = RDKitImporter(engine)
        self._openbabel_importer: Importer = OpenBabelImporter(engine)

    def import_file(self, path: Path, progress: ProgressHandle | None = None) -> list[MoleculeModel]:
        progress = progress or ProgressHandle()
        fmt = path.suffix.lstrip(".").lower()
        progress.report(0.0, f"Importing {path.name}")
        if fmt in RDKIT_IMPORT_FORMATS:
            models = self._rdkit_importer.import_file(path)
        elif fmt in OPENBABEL_FALLBACK_FORMATS:
            models = self._openbabel_importer.import_file(path)
        else:
            raise UnsupportedFormatError(f"No importer registered for .{fmt}")
        progress.report(1.0, "Done")
        logger.info("Imported %d molecule(s) from %s", len(models), path)
        return models
