from __future__ import annotations

import dataclasses

from openchem.app.settings import Settings
from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
from openchem.chem.engine import ChemistryEngine
from openchem.chem.orca_engine import CALC_TYPE_LABELS, METHOD_BASIS_PRESETS
from openchem.chem.pka_providers import PKASOLVER_PYTHON_SETTING
from openchem.chem.stout_providers import STOUT_PYTHON_SETTING
from openchem.domain.calculator import (
    CalculatorDefinition,
    CalculatorParameter,
    RegistryExecution,
    ServiceExecution,
)
from openchem.events.base import EventBus
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.conformer_service import ConformerService
from openchem.services.container import ServiceContainer
from openchem.services.descriptor_service import DescriptorService
from openchem.services.docking_service import DEFAULT_NUM_POSES, DockingService
from openchem.services.export_service import ExportService
from openchem.services.import_service import ImportService
from openchem.services.job_manager import JobManager
from openchem.services.measurement_service import MeasurementService
from openchem.services.project_service import ProjectService
from openchem.services.quantum_chemistry_service import QuantumChemistryService

# Discovery-only registrations (Phase 21): Docking and QuantumChemistry run
# through their own services/panels, never through CalculatorRegistry.compute()
# (see ServiceExecution's docstring) -- registered here purely so
# "what can this app compute" is queryable in one place. Descriptions spell
# out what each needs/produces since there's no structured capability
# schema yet (see Phase 21 plan's "pushed back on" section).
_EXTERNAL_CALCULATOR_DEFINITIONS: list[CalculatorDefinition] = [
    CalculatorDefinition(
        calculator_id="docking.vina",
        display_name="Molecular Docking (Vina)",
        category="docking",
        description=(
            "Docking via AutoDock Vina. Needs a receptor macromolecule and a "
            "search box; run from the Docking panel. Produces ranked poses "
            "with binding scores and interaction analysis."
        ),
        execution=ServiceExecution(service_name="docking_service", panel_name="Docking panel"),
        parameters=[
            CalculatorParameter(
                name="num_poses", label="Number of poses", kind="int", default=DEFAULT_NUM_POSES, minimum=1
            )
        ],
    ),
]

_QM_CALC_TYPE_DESCRIPTIONS = {
    "sp": "Single-point energy via ORCA. Produces the SCF energy.",
    "opt": "Geometry optimization via ORCA. Produces an optimized geometry and energy.",
    "opt_freq": (
        "Geometry optimization + frequency analysis via ORCA. Produces an optimized "
        "geometry, energy, and thermochemistry (enthalpy, entropy, Gibbs free energy)."
    ),
    "nmr": (
        "NMR shielding prediction via ORCA. Produces per-atom isotropic shielding "
        "constants (raw, not yet referenced to a standard like TMS)."
    ),
    "nmr_coupling": (
        "NMR shielding + real ab initio spin-spin (J) coupling constants via ORCA. "
        "More expensive than plain NMR (couples every nucleus pair) -- produces per-atom "
        "shielding plus real Hz coupling values feeding the HSQC/HMBC/COSY correlation tables."
    ),
}

for _label, _calc_type in CALC_TYPE_LABELS.items():
    _EXTERNAL_CALCULATOR_DEFINITIONS.append(
        CalculatorDefinition(
            calculator_id=f"orca.{_calc_type}",
            display_name=_label,
            category="quantum_chemistry",
            description=(
                f"{_QM_CALC_TYPE_DESCRIPTIONS[_calc_type]} Needs an ORCA executable and a "
                "3D conformer; run from the Quantum Chemistry panel."
            ),
            execution=ServiceExecution(
                service_name="quantum_chemistry_service", panel_name="Quantum Chemistry panel"
            ),
            prediction_basis="ab_initio",
            parameters=[
                CalculatorParameter(name="charge", label="Charge", kind="int", default=0, minimum=-10, maximum=10),
                CalculatorParameter(
                    name="multiplicity", label="Multiplicity", kind="int", default=1, minimum=1, maximum=10
                ),
                CalculatorParameter(
                    name="method_basis",
                    label="Method/basis",
                    kind="choice",
                    default=METHOD_BASIS_PRESETS[0],
                    choices=METHOD_BASIS_PRESETS,
                ),
            ],
        )
    )


# Calculators whose compute function needs the configured pkasolver
# interpreter. `CalculatorRegistry.compute` deliberately passes only
# (mol, molecule_uuid, parameters) -- a calculator has no business reaching
# into app Settings itself, and `chem/` must not import `app/`. So the
# composition root, which already owns Settings, binds the path in at
# registration time. Read lazily per call (not captured once) so
# reconfiguring the path in Tools > External Tools takes effect without a
# restart.
# Calculators that need the out-of-process pkasolver interpreter. They
# take an extra `interpreter_path` argument, injected here by the
# composition root -- `chem/` must not import `app/`, and
# `CalculatorRegistry.compute` deliberately passes only
# (mol, molecule_uuid, parameters).
_SETTINGS_BOUND_CALCULATORS = frozenset(
    {
        "pka",
        "logd",
        "pka_microspecies",
        "isoelectric_point",
        "logd_curve",
        "cns_mpo",
        "bbb_descriptors",
    }
)
# `iupac_name` needs a DIFFERENT interpreter (STOUT, not pkasolver), so it
# gets its own binding rather than being folded into the set above.
_STOUT_BOUND_CALCULATORS = frozenset({"iupac_name"})


def _bind_settings(definition: CalculatorDefinition, settings: Settings) -> CalculatorDefinition:
    if definition.calculator_id in _STOUT_BOUND_CALCULATORS:
        stout_inner = definition.execution.compute

        def compute_with_stout(mol, molecule_uuid, parameters, _inner=stout_inner):
            return _inner(
                mol, molecule_uuid, parameters,
                interpreter_path=settings.get(STOUT_PYTHON_SETTING, ""),
            )

        return dataclasses.replace(
            definition, execution=RegistryExecution(compute=compute_with_stout)
        )
    if definition.calculator_id not in _SETTINGS_BOUND_CALCULATORS:
        return definition
    inner = definition.execution.compute

    def compute(mol, molecule_uuid, parameters, _inner=inner):
        return _inner(
            mol, molecule_uuid, parameters,
            interpreter_path=settings.get(PKASOLVER_PYTHON_SETTING, ""),
        )

    return dataclasses.replace(definition, execution=RegistryExecution(compute=compute))


def build_service_container() -> ServiceContainer:
    """Composition root: wires concrete services into a ServiceContainer.

    This is the only place that constructs services directly. Everything
    else (MainWindow, panels, commands) receives them via the container —
    constructor injection, never a global singleton.
    """
    event_bus = EventBus()
    engine = ChemistryEngine()
    # DockingService (for docking/vina_executable_path) and
    # QuantumChemistryService (for orca/executable_path) both need Settings
    # -- constructed here rather than threading a Settings parameter
    # through this function's signature (every existing caller, including
    # many tests, calls build_service_container() with no arguments).
    # Settings is a lightweight wrapper over the same global QSettings
    # store regardless of how many Python instances wrap it, so this is
    # safe: main.py's own separately-constructed Settings(services.event_bus)
    # reads/writes the identical underlying store.
    settings = Settings(event_bus)
    # One JobManager shared by every service that guards against duplicate
    # concurrent submissions for the same key (see JobManager's docstring)
    # -- DescriptorService deliberately doesn't get one; a re-edit should
    # supersede an in-flight descriptor recompute, not be dropped by it.
    job_manager = JobManager()
    # Phase 18: registers the built-in per-atom calculators (Charge, LogP,
    # Molar Refractivity, pKa) against CalculatorRegistry -- the single
    # place PropertyPanel/DescriptorService look up "what calculators
    # exist," rather than each new one needing a PropertyPanel code change.
    # Phase 21: also registers Docking/QuantumChemistry as discovery-only
    # (ServiceExecution) entries -- see _EXTERNAL_CALCULATOR_DEFINITIONS.
    calculator_registry = CalculatorRegistry()
    for definition in CALCULATOR_DEFINITIONS:
        calculator_registry.register(_bind_settings(definition, settings))
    for definition in _EXTERNAL_CALCULATOR_DEFINITIONS:
        calculator_registry.register(definition)
    return ServiceContainer(
        event_bus=event_bus,
        chemistry_engine=engine,
        descriptor_service=DescriptorService(event_bus, engine, calculator_registry=calculator_registry),
        import_service=ImportService(engine),
        export_service=ExportService(engine),
        project_service=ProjectService(event_bus),
        conformer_service=ConformerService(event_bus, engine, job_manager=job_manager),
        measurement_service=MeasurementService(engine),
        docking_service=DockingService(event_bus, settings, job_manager=job_manager),
        quantum_chemistry_service=QuantumChemistryService(event_bus, settings, job_manager=job_manager),
        job_manager=job_manager,
        calculator_registry=calculator_registry,
    )
