from __future__ import annotations

from dataclasses import dataclass

from openchem.chem.engine import ChemistryEngine
from openchem.events.base import EventBus
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.spatial_overlay_service import SpatialOverlayService
from openchem.services.alignment_service import AlignmentService
from openchem.services.batch_service import BatchService
from openchem.services.conformer_service import ConformerService
from openchem.services.descriptor_service import DescriptorService
from openchem.services.docking_service import DockingService
from openchem.services.export_service import ExportService
from openchem.services.import_service import ImportService
from openchem.services.job_manager import JobManager
from openchem.services.measurement_service import MeasurementService
from openchem.services.project_service import ProjectService
from openchem.services.qm_surface_service import QmSurfaceService
from openchem.services.quantum_chemistry_service import QuantumChemistryService
from openchem.services.screening_service import ScreeningService
from openchem.services.atom_fact_service import AtomFactService
from openchem.services.reaction_template_service import ReactionTemplateService
from openchem.services.structure_check_service import StructureCheckService
from openchem.services.table_export_service import TableExportService


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
    qm_surface_service: QmSurfaceService
    job_manager: JobManager
    calculator_registry: CalculatorRegistry
    batch_service: BatchService
    table_export_service: TableExportService
    screening_service: ScreeningService
    structure_check_service: StructureCheckService
    atom_fact_service: AtomFactService
    reaction_template_service: ReactionTemplateService
    #: Recomputes shape-valued results for the conformer a viewer is
    #: showing. Defaulted and LAST, because a dataclass cannot take a
    #: defaulted field before required ones -- and defaulted so a
    #: container built without it (every existing test) still works.
    spatial_overlay_service: SpatialOverlayService | None = None
