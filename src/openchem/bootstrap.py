from __future__ import annotations

import dataclasses

from openchem.app.settings import Settings
from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
from openchem.chem.engine import ChemistryEngine
from openchem.chem.orca_engine import CALC_TYPE_LABELS, METHOD_BASIS_PRESETS
from openchem.chem.admet_providers import ADMET_PYTHON_SETTING
from openchem.chem.pka_providers import PKASOLVER_PYTHON_SETTING
from openchem.domain.calculator import (
    CalculatorDefinition,
    CalculatorParameter,
    RegistryExecution,
    ServiceExecution,
)
from openchem.events.base import EventBus
from openchem.services.calculator_registry import CalculatorRegistry
from openchem.services.alignment_service import AlignmentService
from openchem.services.batch_service import BatchService
from openchem.services.conformer_service import ConformerService
from openchem.services.container import ServiceContainer
from openchem.services.atom_fact_service import AtomFactService
from openchem.services.reaction_template_service import ReactionTemplateService
from openchem.services.structure_check_service import StructureCheckService
from openchem.services.descriptor_service import DescriptorService
from openchem.services.docking_service import DEFAULT_NUM_POSES, DockingService
from openchem.services.export_service import ExportService
from openchem.services.import_service import ImportService
from openchem.services.job_manager import JobManager
from openchem.services.measurement_service import MeasurementService
from openchem.services.project_service import ProjectService
from openchem.services.qm_surface_service import QmSurfaceService
from openchem.services.quantum_chemistry_service import QuantumChemistryService
from openchem.services.screening_service import ScreeningService
from openchem.services.table_export_service import TableExportService

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
    "delta_scf": (
        "Chemical hardness and softness from vertical ionization potential and "
        "electron affinity, computed as energy DIFFERENCES between the neutral, "
        "cation and anion rather than from orbital energies. Three single points in "
        "one job, all at the geometry as supplied -- optimize first if you need a "
        "relaxed geometry, since optimizing here would give adiabatic rather than "
        "vertical quantities. Slower than reading the frontier orbitals, and the "
        "one that reproduces the textbook hard/soft orderings."
    ),
    "led": (
        "Breaks a non-covalent interaction energy into electrostatics, exchange, "
        "dispersion, charge transfer and the cost of distorting each partner, via "
        "ORCA's Local Energy Decomposition on DLPNO-CCSD(T). Needs the two partners "
        "drawn as SEPARATE species -- they are the fragments. Runs the complex and "
        "both partners in one job, because the decomposition of a complex on its own "
        "is not a binding energy. Expensive and steeply so: measured 15 seconds for "
        "BH3-CO but 10 minutes and 1.9 GB of scratch disk for benzene-water, and it "
        "is not usable on anything drug-sized."
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


# Conceptual-DFT descriptors are produced by ANY ORCA job (see
# `OrcaQuantumEngineProvider._parse_conceptual_dft`), so this entry runs no
# new kind of calculation. It exists so the quantities Pearson's HSAB
# principle is stated in are findable from the Lewis section rather than
# only under quantum chemistry, and so the empirical Lewis site analysis
# gets an automatic pointer to its ab initio counterpart -- the same
# mechanism that points the SMARTS NMR estimate at a real ORCA run.
#
# There is deliberately no "this molecule is hard" verdict. HSAB is a
# COMPARATIVE principle: hard and soft are only meaningful between two
# species, and no cutoff on the Pearson scale separates them. Comparing a
# pair is what the Interactions work is for.
_EXTERNAL_CALCULATOR_DEFINITIONS.append(
    CalculatorDefinition(
        calculator_id="lewis_hsab",
        display_name="Hardness / Softness (HSAB)",
        category="lewis",
        description=(
            "Chemical hardness, softness, electronegativity, chemical potential and "
            "the electrophilicity index, from the frontier orbital energies of a "
            "quantum chemistry run. These are the quantities Pearson's hard/soft "
            "acid-base principle is stated in. "
            "Run any ORCA job from the Quantum Chemistry panel and they appear "
            "automatically -- no separate calculation. "
            "Koopmans values carry a caveat worth reading: measured against real "
            "B3LYP/def2-SVP runs they invert the hardness of ammonia and phosphine, "
            "which is one of the most-used hard/soft orderings there is."
        ),
        execution=ServiceExecution(
            service_name="quantum_chemistry_service", panel_name="Quantum Chemistry panel"
        ),
        prediction_basis="ab_initio",
        tags=["lewis", "hsab", "hardness", "softness", "electrophilicity"],
        parameters=[
            CalculatorParameter(
                name="method_basis",
                label="Method/basis",
                kind="choice",
                default=METHOD_BASIS_PRESETS[0],
                choices=METHOD_BASIS_PRESETS,
            )
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
#
# Three sidecars now, each with its own interpreter, so this is a mapping
# from calculator to the setting holding ITS interpreter rather than one
# branch per sidecar. The previous shape -- a frozenset per sidecar and an
# if-block per set -- would have needed a third copy of the same six lines
# to add ADMET.
_CALCULATOR_INTERPRETER_SETTING: dict[str, str] = {
    # pkasolver
    "pka": PKASOLVER_PYTHON_SETTING,
    "logd": PKASOLVER_PYTHON_SETTING,
    "pka_microspecies": PKASOLVER_PYTHON_SETTING,
    "isoelectric_point": PKASOLVER_PYTHON_SETTING,
    "logd_curve": PKASOLVER_PYTHON_SETTING,
    "cns_mpo": PKASOLVER_PYTHON_SETTING,
    "bbb_descriptors": PKASOLVER_PYTHON_SETTING,
    # ADMET-AI (hERG / CYP / Ames)
    "admet_ml": ADMET_PYTHON_SETTING,
}


def _bind_settings(definition: CalculatorDefinition, settings: Settings) -> CalculatorDefinition:
    setting_key = _CALCULATOR_INTERPRETER_SETTING.get(definition.calculator_id)
    if setting_key is None:
        return definition
    inner = definition.execution.compute

    # Read lazily, per call: reconfiguring the path in Tools > External
    # Tools then takes effect without restarting the application.
    def compute(mol, molecule_uuid, parameters, _inner=inner, _key=setting_key):
        return _inner(
            mol, molecule_uuid, parameters,
            interpreter_path=settings.get(_key, ""),
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
    # Named rather than constructed inline like its siblings, because
    # ScreeningService below drives THIS instance -- it queues ligands
    # through the same service the Docking panel uses, so a screen and a
    # one-off docking share one single-flight guard instead of racing.
    docking_service = DockingService(event_bus, settings, job_manager=job_manager)
    return ServiceContainer(
        event_bus=event_bus,
        chemistry_engine=engine,
        descriptor_service=DescriptorService(event_bus, engine, calculator_registry=calculator_registry),
        import_service=ImportService(engine),
        export_service=ExportService(engine),
        project_service=ProjectService(event_bus),
        conformer_service=ConformerService(event_bus, engine, job_manager=job_manager),
        alignment_service=AlignmentService(event_bus, engine, job_manager=job_manager),
        measurement_service=MeasurementService(engine),
        docking_service=docking_service,
        quantum_chemistry_service=QuantumChemistryService(event_bus, settings, job_manager=job_manager),
        # Shares Settings with QuantumChemistryService so `orca_plot` is
        # located beside the SAME configured `orca` executable -- a second
        # path setting is a second thing to fall out of step with the first.
        qm_surface_service=QmSurfaceService(event_bus, settings),
        job_manager=job_manager,
        calculator_registry=calculator_registry,
        # Shares the JobManager so a batch run is listed and cancellable in
        # the Jobs panel like every other long job, and shares the registry
        # so "what can be computed in batch" cannot drift from "what can be
        # computed at all".
        batch_service=BatchService(event_bus, engine, calculator_registry, job_manager=job_manager),
        table_export_service=TableExportService(),
        screening_service=ScreeningService(event_bus, docking_service, engine, job_manager=job_manager),
        # No JobManager: nine checkers over a drawing-sized molecule is
        # arithmetic over a few dozen atoms, and a thread would add a
        # second source of stale results to the one this service exists
        # to prevent. It subscribes to MoleculeChanged itself, so its
        # version counter is right from construction rather than from
        # whenever a panel first asks.
        structure_check_service=StructureCheckService(event_bus),
        # Empty until a plugin registers. Constructed here rather than
        # lazily so `PluginContext` always has something to hand a
        # registrar, exactly like every other provider service.
        atom_fact_service=AtomFactService(),
        reaction_template_service=ReactionTemplateService(),
    )
