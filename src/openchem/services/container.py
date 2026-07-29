from __future__ import annotations

from dataclasses import dataclass

from openchem.chem.engine import ChemistryEngine
from openchem.events.base import EventBus
from openchem.services.conformer_service import ConformerService
from openchem.services.descriptor_service import DescriptorService
from openchem.services.docking_service import DockingService
from openchem.services.export_service import ExportService
from openchem.services.import_service import ImportService
from openchem.services.measurement_service import MeasurementService
from openchem.services.project_service import ProjectService


@dataclass
class ServiceContainer:
    """Explicit dependency-injection container.

    Built once in `openchem.bootstrap` and passed down to whatever needs it
    (MainWindow, panels, commands). Nothing in the app reaches for a global
    singleton instead.
    """

    event_bus: EventBus
    chemistry_engine: ChemistryEngine
    descriptor_service: DescriptorService
    import_service: ImportService
    export_service: ExportService
    project_service: ProjectService
    conformer_service: ConformerService
    measurement_service: MeasurementService
    docking_service: DockingService
