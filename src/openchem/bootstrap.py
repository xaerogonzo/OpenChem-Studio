from __future__ import annotations

import dataclasses
import functools

from openchem.app.settings import Settings
from openchem.chem.admet_providers import ADMET_PYTHON_SETTING
from openchem.chem.bond_dissociation import METHOD_LABEL as BOND_DISSOCIATION_METHOD
from openchem.chem.descriptor_providers import CALCULATOR_DEFINITIONS
from openchem.chem.engine import ChemistryEngine
from openchem.chem.orca_engine import CALC_TYPE_LABELS, METHOD_BASIS_PRESETS
from openchem.chem.pka_providers import PKASOLVER_PYTHON_SETTING
from openchem.chem.proton_affinity import METHOD_LABEL as PROTON_AFFINITY_METHOD
from openchem.domain.calculator import (
    CalculatorDefinition,
    CalculatorParameter,
    RegistryExecution,
    ServiceExecution,
)
from openchem.domain.builtin_execution_policies import BUILTIN_POLICIES
from openchem.domain.calculator_support import (
    CalculatorSupport,
    SupportStage,
    Visibility,
)
from openchem.events.base import EventBus
from openchem.services.alignment_service import AlignmentService
from openchem.services.synthesis_planner_setup import SetupProvider
from openchem.services.synthesis_planning_service import SynthesisPlanningService
from openchem.services.atom_fact_service import AtomFactService
from openchem.services.batch_service import BatchService
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
from openchem.services.qm_surface_service import QmSurfaceService
from openchem.services.quantum_chemistry_service import QuantumChemistryService
from openchem.services.reaction_template_service import ReactionTemplateService
from openchem.services.recalc_scheduler import RecalcScheduler
from openchem.services.recipe_service import RecipeService
from openchem.services.result_store_service import ResultStoreService
from openchem.services.score_service import ScoreService
from openchem.services.screening_service import ScreeningService
from openchem.services.spatial_overlay_service import SpatialOverlayService
from openchem.services.structure_check_service import StructureCheckService
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
        execution=ServiceExecution(
            service_name="docking_service", panel_name="Docking panel", panel_id="Docking"
        ),
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
    "fukui": (
        "Where an added or removed electron goes, atom by atom: the condensed Fukui functions f+ (attack "
        "by a nucleophile), f- (attack by an electrophile), f0 (attack by a radical) and the dual "
        "descriptor f+ - f-, from the Hirshfeld charges of the neutral, the cation and the anion. Three "
        "single points in one job, all at the geometry as supplied (vertical): optimize first if the "
        "drawn geometry is not good enough. Closed-shell species only. A species that is itself an anion "
        "gets its f+ from a dianion, which no basis set binds in the gas phase, so for an anion f+ is the "
        "least trustworthy number; the dianion is run last, and if it gives nothing usable the result is "
        "f- alone and says why (Settings > Quantum chemistry can leave it out). Hirshfeld is the one charge "
        "scheme offered because, of the five ORCA prints, it was the only one whose values stayed within "
        "0.023 of themselves when diffuse functions were added and never went negative, on "
        "formaldehyde, propene and pyridine. The anion of a neutral molecule is usually unbound at an "
        "ordinary basis set, which makes f+ the less trustworthy half; the result says so. At a basis set "
        "with diffuse functions an anionic state is also started from two more initial guesses and the "
        "lowest solution is read, because there it can have more than one. The cation can have several "
        "states a few tenths of an eV apart, and one cation job reaches whichever ORCA's SCF falls into "
        "(for benzaldehyde, not a function of the structure), so three more cation jobs start from the "
        "neutral's orbitals with the electron taken from the HOMO-1, HOMO-2 and HOMO-3, f- is read from "
        "the lowest state found, and the result says when another lies within 0.5 eV and how far its f- is "
        "(about 2.5 times the time of a run without it; Settings > Quantum chemistry can switch it off)."
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

# The calc types that declare a stage of their own. The rest predate the declaration and are `LEGACY_UNCLASSIFIED`, a closing
# migration, so a calc type added today earns an honest stage here instead of joining that list.
_QM_CALC_TYPE_SUPPORT = {
    # EXPERIMENTAL, as the tautomer distribution below is: implemented, run through the application on real ORCA and measured
    # against published values, and not validated for default use because it did not pass its own preregistered gate
    # (benchmarks/fukui_gate/PREREGISTRATION.md section 11). A stage describes THIS implementation, never the published method.
    "fukui": CalculatorSupport(
        stage=SupportStage.EXPERIMENTAL,
        default_visibility=Visibility.HIDDEN,
        support_reason=(
            "Not validated: it failed two preregistered checks against published Hirshfeld condensed Fukui values. "
            "The first (an earlier version) missed by 0.0014 on the f- of carbon monoxide at HF/6-31G**, whose cation "
            "is heavily spin-contaminated. The second, of the current version, reproduced 33 of 47 numbers to within "
            "0.02 (23 of them to 0.002); the other 14 belong to hydrogen cyanide, thiocyanate, benzaldehyde, "
            "anilinium, pyrrole, furan and thiophene, and for benzaldehyde, anilinium and thiophene the published "
            "values match a cation state 0.09 to 0.45 eV above the lowest one. Offered in the Quantum Chemistry "
            "panel, and every result says so."
        ),
        scope_note=(
            "Closed-shell species, Hirshfeld charges only, ions at the neutral geometry (vertical); "
            "needs a configured ORCA executable"
        ),
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
                service_name="quantum_chemistry_service",
                panel_name="Quantum Chemistry panel",
                panel_id="Quantum_Chemistry",
            ),
            prediction_basis="ab_initio",
            support=_QM_CALC_TYPE_SUPPORT.get(_calc_type),
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


# NOT in CALC_TYPE_LABELS, deliberately: "tautomer_distribution" is not a
# real ORCA calc_type (it dispatches N real "opt" jobs internally, one per
# candidate, via QuantumChemistryService.request_tautomer_distribution) --
# looping it through the CALC_TYPE_LABELS block above would wrongly imply
# it is a single ORCA job like the others. A standalone entry instead.
_EXTERNAL_CALCULATOR_DEFINITIONS.append(
    CalculatorDefinition(
        calculator_id="orca.tautomer_distribution",
        display_name="Tautomer Distribution",
        category="quantum_chemistry",
        description=(
            "Gas-phase electronic-energy Boltzmann population ESTIMATE over every "
            "tautomer RDKit can enumerate, each optimized by its own real ORCA geometry "
            "optimization -- not a full equilibrium probability model: no vibrational, "
            "thermal, entropic, or solvent correction, and a SAMPLED conformer search per "
            "tautomer (not exhaustive: the lowest calculated conformer represents it). "
            "A population percentage is "
            "shown only once validated against reference data (see docs/USER_GUIDE.md's "
            "'Tautomer distribution' topic); otherwise each candidate's real relative "
            "energy is still shown, just not a population built from it. If any "
            "candidate fails to converge, no percentages are shown for any of them. "
            "Needs an ORCA executable; run from the Quantum Chemistry panel's "
            "'Tautomers...' button -- no pre-existing 3D conformer required, since each "
            "candidate is embedded fresh from the 2D structure."
        ),
        execution=ServiceExecution(
            service_name="quantum_chemistry_service",
            panel_name="Quantum Chemistry panel",
            panel_id="Quantum_Chemistry",
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
        # EXPERIMENTAL, honestly: this implementation is not yet validated
        # for default use (see chem/tautomer_distribution.py -- the real,
        # two-gate validation study against published reference data has
        # not been run; every result ships under VALIDATION_UNVALIDATED
        # today). Not a guess "it feels experimental" -- the scope's own
        # seven ORCA siblings all predate this declaration and are still
        # LEGACY_UNCLASSIFIED, but that list is a closing migration, never
        # an open bucket a NEW calculator can be added to
        # (test_the_legacy_list_only_shrinks) -- a calculator written today
        # earns its own honest stage instead.
        support=CalculatorSupport(
            stage=SupportStage.EXPERIMENTAL,
            default_visibility=Visibility.HIDDEN,
            support_reason=(
                "Not yet validated: computed populations have not been checked against "
                "published reference data at a literature-comparable level of theory. "
                "Every result currently ships labeled 'unvalidated' -- real relative "
                "energies are shown, but no population percentage is."
            ),
            scope_note="Gas-phase electronic-energy Boltzmann estimate; needs a configured ORCA executable",
        ),
    )
)

# Like the tautomer distribution, NOT in CALC_TYPE_LABELS: proton affinity is not one ORCA calc type, it dispatches an `Opt Freq` per structure
# of the base and of every conjugate acid (QuantumChemistryService.request_proton_affinity), so it is a standalone entry. It has no method or
# free method or charge parameters on purpose: the protocol is exactly the one that was benchmarked, and a different functional or basis is a different
# protocol that needs its own benchmark (benchmarks/proton_affinity/PREREGISTRATION.md). Its one parameter shows the fixed protocol.
_EXTERNAL_CALCULATOR_DEFINITIONS.append(
    CalculatorDefinition(
        calculator_id="orca.proton_affinity",
        display_name="Proton Affinity and Gas Basicity",
        category="quantum_chemistry",
        description=(
            "The gas-phase proton affinity (an enthalpy) and gas-phase basicity (a Gibbs energy) of a neutral base at 298.15 K and 1 atm, "
            "from ORCA M062X/def2-TZVPD optimizations and frequencies of the base and of its conjugate acid at every protonation site "
            "(every N, O, S or P lone pair and every pi-system carbon), the lowest structure of each, with ORCA's symmetry number "
            "replaced by the true one. Reports kJ/mol, the site that won and every site's own value. Benchmarked on 28 bases against the NIST "
            "evaluation of Hunter and Lias: on the 21 above propene's proton affinity the mean absolute error is 1.55 kcal/mol (PA) and 1.53 (GB), "
            "with the proton bound about 1.2 kcal/mol too weakly; measured for neutral bases of at most ten heavy atoms of H, C, N, O, P and S; "
            "a larger base or other elements are computed after a warning, the result labelled an estimate. A structure that keeps an imaginary vibration after one re-run is dropped, so a base can have no value "
            "(the benchmark lost water this way). Many ORCA jobs (minutes to hours): needs an ORCA executable; run from the Quantum Chemistry "
            "panel's 'Proton affinity...' button -- no 3D conformer needed, each structure is embedded fresh from the 2D structure."
        ),
        execution=ServiceExecution(
            service_name="quantum_chemistry_service",
            panel_name="Quantum Chemistry panel",
            panel_id="Quantum_Chemistry",
        ),
        prediction_basis="ab_initio",
        # One option, a fixed choice, so the dialog says WHICH protocol this is rather than offering the free method box the other ORCA entries have;
        # a calculator with no option at all is refused by tests/test_calculator_options.py.
        parameters=[
            CalculatorParameter(
                name="method_basis",
                label="Method/basis (fixed: the benchmarked protocol)",
                kind="choice",
                default=PROTON_AFFINITY_METHOD,
                choices=[PROTON_AFFINITY_METHOD],
            ),
        ],
        # LIMITED, and shown: the benchmark PASSED, and this implementation has now been driven through the application on real ORCA, reproducing the
        # benchmark's own numbers from the STORED result (benchmarks/visual/proton_affinity_run.json, recorded in docs/PROTON_AFFINITY_DESIGN.md), which is
        # what EXPERIMENTAL waited for. LIMITED and not STABLE because the scope is narrow (neutral bases of at most ten heavy atoms of six elements) and one
        # benchmark is not the held-out, stratified result STABLE asks for (docs/CALCULATOR_MATURITY.md). It was hidden only for want of the driven run;
        # to hide it again, set default_visibility back to HIDDEN.
        support=CalculatorSupport(
            stage=SupportStage.LIMITED,
            default_visibility=Visibility.SHOWN,
            support_reason=(
                "Limited: the measured error holds for neutral closed-shell bases of at most ten heavy atoms of H, C, N, O, P and S (outside that it still computes, after a warning, as an estimate). The protocol passed its preregistered benchmark (28 bases against NIST, mean absolute error "
                "1.55 kcal/mol for proton affinity and 1.53 for gas basicity, the proton bound about 1.2 kcal/mol too weakly) and this implementation reproduces the benchmark's numbers when driven "
                "through the application on real ORCA. It needs many ORCA jobs. Every result states the measured error and its limits."
            ),
            scope_note=(
                "Measured for neutral closed-shell bases of at most ten heavy atoms of H, C, N, O, P and S (larger or other elements: computed after a warning, an estimate); "
                "charged, radical and multi-component structures are refused; the lowest structure only; needs a configured ORCA executable"
            ),
        ),
    )
)


# Standalone like the proton affinity, for the same reason: bond dissociation is not one ORCA calc type, it dispatches the hydrogen atom, an `Opt Freq` of the parent's conformers and one
# of a doublet radical per chosen bond and conformer (QuantumChemistryService.request_bond_dissociation). No method or charge parameters on purpose: the protocol is exactly the one that was
# benchmarked (benchmarks/bde/PREREGISTRATION.md, then the held-out arm of benchmarks/restart_v2/), and its one parameter shows it.
_EXTERNAL_CALCULATOR_DEFINITIONS.append(
    CalculatorDefinition(
        calculator_id="orca.bond_dissociation_enthalpy",
        display_name="X-H Bond Dissociation Enthalpy",
        category="quantum_chemistry",
        description=(
            "The homolytic bond dissociation enthalpy at 298.15 K of the C-H, N-H, O-H or S-H bonds you choose in a neutral closed-shell molecule, "
            "DH298 = H(radical) + H(H atom) - H(molecule), from ORCA M062X/def2-TZVPD optimizations and frequencies of the molecule, of the doublet radical "
            "each bond leaves and a single point of the hydrogen atom, the lowest structure of each. Reports kJ/mol: the weakest bond computed in the headline and every bond's own value "
            "or the reason it has none. Benchmarked on 49 bonds (22 against experiment, 27 held out against the Active Thermochemical Tables): mean absolute error 1.48 kcal/mol, "
            "and the calculation runs LOW by 1.38 kcal/mol on average, in every class (an O-H next to another oxygen or a nitrogen: 3.3, up to 4.6). Measured for molecules of at most "
            "nine heavy atoms of H, C, N, O and S; outside that it computes after a warning, the result labelled an estimate. A radical that keeps an imaginary vibration after one re-run gives that bond no value (thiyl radicals do). "
            "Many ORCA jobs (minutes to hours): needs an ORCA executable; run from the Quantum Chemistry panel's 'Bond dissociation...' button -- no 3D conformer needed."
        ),
        execution=ServiceExecution(
            service_name="quantum_chemistry_service",
            panel_name="Quantum Chemistry panel",
            panel_id="Quantum_Chemistry",
        ),
        prediction_basis="ab_initio",
        parameters=[
            CalculatorParameter(
                name="method_basis",
                label="Method/basis (fixed: the benchmarked protocol)",
                kind="choice",
                default=BOND_DISSOCIATION_METHOD,
                choices=[BOND_DISSOCIATION_METHOD],
            ),
        ],
        # EXPERIMENTAL like the proton affinity, for the same reason: the stage describes THIS implementation, and until it has been driven through the application on real ORCA
        # (its recorded run is the change that promotes it, docs/CALCULATOR_MATURITY.md) the benchmarks' verdicts are about the benchmarks' own runner.
        support=CalculatorSupport(
            stage=SupportStage.EXPERIMENTAL,
            default_visibility=Visibility.HIDDEN,
            support_reason=(
                "The protocol was measured on 49 bonds (22 against experiment, PARTIAL by 0.03 kcal/mol on the bias; 27 held out against the Active Thermochemical Tables, PASS): mean absolute error 1.48 kcal/mol, "
                "values run about 1.4 kcal/mol low, and an O-H next to O or N runs 3.3 low. This implementation has not yet been driven through the application on real ORCA, and it needs many ORCA jobs. "
                "Every result states the measured error and its limits."
            ),
            scope_note=(
                "Measured for neutral closed-shell molecules of at most nine heavy atoms of H, C, N, O and S and their C-H, N-H, O-H, S-H and Si-H bonds (outside that: computed after a warning, an estimate); "
                "charged, radical and multi-component structures are refused; the lowest structure only; needs a configured ORCA executable"
            ),
        ),
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
            service_name="quantum_chemistry_service",
            panel_name="Quantum Chemistry panel",
            panel_id="Quantum_Chemistry",
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
# A dict VALUE names one keyword argument each, for the calculators that
# need more than one sidecar. Solubility is the case that forced it: its
# pKa comes from pkasolver while its optional AqSolDB baseline comes from
# the ADMET environment, and either can be configured without the other.
# A plain string keeps meaning exactly what it did -- bind
# `interpreter_path` -- so no existing entry changed.
_CALCULATOR_INTERPRETER_SETTING: dict[str, str | dict[str, str]] = {
    # pkasolver
    "pka": PKASOLVER_PYTHON_SETTING,
    "ionisable_sites": PKASOLVER_PYTHON_SETTING,
    "logd": PKASOLVER_PYTHON_SETTING,
    "pka_microspecies": PKASOLVER_PYTHON_SETTING,
    "isoelectric_point": PKASOLVER_PYTHON_SETTING,
    "cns_mpo": PKASOLVER_PYTHON_SETTING,
    "bbb_descriptors": PKASOLVER_PYTHON_SETTING,
    # For its ionization-model cross-check only: the charges are computed on
    # Dimorphite-DL's species with or without it.
    "gasteiger_charge_at_ph": PKASOLVER_PYTHON_SETTING,
    # ADMET-AI (hERG / CYP / Ames)
    "admet_ml": ADMET_PYTHON_SETTING,
    # Both, independently.
    "solubility": {
        "interpreter_path": PKASOLVER_PYTHON_SETTING,
        "admet_interpreter_path": ADMET_PYTHON_SETTING,
    },
}


def _bind_settings(definition: CalculatorDefinition, settings: Settings) -> CalculatorDefinition:
    setting_key = _CALCULATOR_INTERPRETER_SETTING.get(definition.calculator_id)
    if setting_key is None:
        return definition
    keys = {"interpreter_path": setting_key} if isinstance(setting_key, str) else dict(setting_key)
    inner = definition.execution.compute

    # Read lazily, per call: reconfiguring the path in Tools > External
    # Tools then takes effect without restarting the application.
    #
    # **`functools.wraps` IS LOAD-BEARING, NOT TIDINESS.** A bare closure
    # keeps none of the wrapped function's metadata, so every
    # sidecar-backed calculator presented itself as a nameless `compute`
    # with no docstring and, the part that bit, NO RETURN ANNOTATION.
    # Measured when the calculator reference was generated: 12 of 59
    # calculators could not say what they produce, and 9 of those 12 had an
    # annotation all along -- this wrapper was eating it.
    @functools.wraps(inner)
    def compute(mol, molecule_uuid, parameters, _inner=inner, _keys=keys):
        paths = {name: settings.get(key, "") for name, key in _keys.items()}
        return _inner(mol, molecule_uuid, parameters, **paths)

    return dataclasses.replace(definition, execution=RegistryExecution(compute=compute))


def _with_policy(definition: CalculatorDefinition) -> CalculatorDefinition:
    """A built-in's execution policy, put on its definition here and nowhere later.

    Attached by the composition root rather than looked up by id when a decision is made, so a
    plugin that registers a calculator under a built-in's id does not inherit that calculator's
    permission to run unattended. A built-in with no entry keeps `None` and is treated as needing
    approval; `tests/test_execution_policy.py` fails for one, so that never ships.
    """
    policy = BUILTIN_POLICIES.get(definition.calculator_id)
    if policy is None or definition.execution_policy is not None:
        return definition
    return dataclasses.replace(definition, execution_policy=policy)


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
        calculator_registry.register(_with_policy(_bind_settings(definition, settings)))
    for definition in _EXTERNAL_CALCULATOR_DEFINITIONS:
        calculator_registry.register(_with_policy(definition))
    # Named rather than constructed inline like its siblings, because
    # ScreeningService below drives THIS instance -- it queues ligands
    # through the same service the Docking panel uses, so a screen and a
    # one-off docking share one single-flight guard instead of racing.
    docking_service = DockingService(event_bus, settings, job_manager=job_manager)
    # Named for the same reason `docking_service` is: DescriptorService
    # below needs THIS instance's version counter, so that every calculator
    # result records which revision of the structure it describes. A second
    # checker would count a different molecule's edits.
    structure_check_service = StructureCheckService(event_bus)
    # Named because the synthesis panel asks THIS instance what the planner's configuration offers; the planning service reads the same one.
    synthesis_setup = SetupProvider(settings)
    # Named because the recipe service below reads THIS instance's project and stored runs.
    result_store_service = ResultStoreService(event_bus, engine, settings)
    # Named because the store asks THIS instance, as a project is opened, which of the results a
    # file brings back no build records any more (an earlier build re-ran the whole always-on
    # set on a conformer and saved it under the GEOMETRY identity).
    descriptor_service = DescriptorService(
        event_bus,
        engine,
        calculator_registry=calculator_registry,
        structure_version_of=structure_check_service.current_version,
    )
    result_store_service.set_obsolete_check(descriptor_service.is_obsolete_result)
    return ServiceContainer(
        event_bus=event_bus,
        chemistry_engine=engine,
        descriptor_service=descriptor_service,
        import_service=ImportService(engine),
        export_service=ExportService(engine),
        project_service=ProjectService(event_bus),
        conformer_service=ConformerService(event_bus, engine, job_manager=job_manager),
        alignment_service=AlignmentService(event_bus, engine, job_manager=job_manager),
        # The planner's Python and configuration come from the External Tools tab's settings: until both are set and the environment answers,
        # the provider returns None and every request is `unavailable`, after the regulatory gate has had its say.
        synthesis_planning_service=SynthesisPlanningService(
            event_bus,
            setup_provider=synthesis_setup,
            job_manager=job_manager,
            structure_version_of=structure_check_service.current_version,
        ),
        synthesis_setup=synthesis_setup,
        measurement_service=MeasurementService(engine),
        docking_service=docking_service,
        quantum_chemistry_service=QuantumChemistryService(event_bus, settings, job_manager=job_manager),
        # Shares Settings with QuantumChemistryService so `orca_plot` is
        # located beside the SAME configured `orca` executable -- a second
        # path setting is a second thing to fall out of step with the first.
        qm_surface_service=QmSurfaceService(event_bus, settings),
        job_manager=job_manager,
        calculator_registry=calculator_registry,
        spatial_overlay_service=SpatialOverlayService(event_bus, calculator_registry),
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
        structure_check_service=structure_check_service,
        # Empty until a plugin registers. Constructed here rather than
        # lazily so `PluginContext` always has something to hand a
        # registrar, exactly like every other provider service.
        atom_fact_service=AtomFactService(),
        reaction_template_service=ReactionTemplateService(),
        # Subscribes to the result envelopes at construction, so nothing a
        # calculator records can arrive before there is a store to take it.
        result_store_service=result_store_service,
        recipe_service=RecipeService(result_store_service, engine),
        score_service=ScoreService(event_bus, result_store_service, calculator_registry),
        # The policy is read from Settings at every edit, never captured, so changing it
        # in the Settings window applies to the next edit.
        recalc_scheduler=RecalcScheduler(event_bus, settings.recalc_policy),
    )
