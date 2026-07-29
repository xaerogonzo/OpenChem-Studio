from __future__ import annotations

from openchem.chem.engine import ChemistryEngine
from openchem.events.base import EventBus
from openchem.services.conformer_service import ConformerService
from openchem.services.container import ServiceContainer
from openchem.services.descriptor_service import DescriptorService
from openchem.services.docking_service import DockingService
from openchem.services.export_service import ExportService
from openchem.services.import_service import ImportService
from openchem.services.measurement_service import MeasurementService
from openchem.services.project_service import ProjectService


def build_service_container() -> ServiceContainer:
    """Composition root: wires concrete services into a ServiceContainer.

    This is the only place that constructs services directly. Everything
    else (MainWindow, panels, commands) receives them via the container —
    constructor injection, never a global singleton.
    """
    event_bus = EventBus()
    engine = ChemistryEngine()
    return ServiceContainer(
        event_bus=event_bus,
        chemistry_engine=engine,
        descriptor_service=DescriptorService(event_bus, engine),
        import_service=ImportService(engine),
        export_service=ExportService(engine),
        project_service=ProjectService(event_bus),
        conformer_service=ConformerService(event_bus, engine),
        measurement_service=MeasurementService(engine),
        docking_service=DockingService(event_bus),
    )
