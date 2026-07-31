from __future__ import annotations

from dataclasses import dataclass

from openchem.chem.engine import ChemistryEngine
from openchem.events.base import EventBus
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.alignment_service import AlignmentService
from openchem.services.conformer_service import ConformerService
from openchem.services.descriptor_service import DescriptorService
from openchem.services.docking_service import DockingService
from openchem.services.export_service import ExportService
from openchem.services.import_service import ImportService
from openchem.services.job_manager import JobManager
from openchem.services.measurement_service import MeasurementService
from openchem.services.project_service import ProjectService
from openchem.services.quantum_chemistry_service import QuantumChemistryService


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
    alignment_service: AlignmentService
    measurement_service: MeasurementService
    docking_service: DockingService
    quantum_chemistry_service: QuantumChemistryService
    job_manager: JobManager
    calculator_registry: CalculatorRegistry
