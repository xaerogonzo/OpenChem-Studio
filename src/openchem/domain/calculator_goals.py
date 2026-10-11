"""What to run for a goal: the curated sets behind "Run recommended" and the wizard.

**A GOAL IS A QUESTION, NOT A CATEGORY.** "Where is the charge, and how polar is it?"
is answered by calculators from three categories; a person asking it does not know,
or want to know, which sections they live in. Each goal here is named for the question
and holds the calculators that answer it, in two roles:

* `recommended` -- what "Run recommended" runs: a short set that answers the question
  without needing a decision from the person;
* `optional` -- offered in the wizard's customise page, ticked off, because it answers
  a narrower or costlier version of the question.

**THE LISTS ARE EDITORIAL AND SAY SO.** Which five of a dozen charge-related
calculators to run is a judgement, so every entry carries the one-line reason it is
there, shown beside it in the wizard. Nothing here is a validated protocol, and the
wizard says that too.

**A GOAL'S ID IS A TASK GROUP'S ID**, so the launcher's group heading and the goal that
runs its recommended set are the same thing under one name (`TASK_GROUPS`).

Pure: no Qt, no registry. `validate_goals` takes the one lookup it needs and returns
every way the table has drifted from what is registered, so a retired id, a renamed
parameter or a calculator that now needs input is a failing test rather than a
recommendation that silently runs nothing.
"""

from __future__ import annotations

import uuid as _uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from openchem.domain.calculator import GEOMETRY, CalculatorDefinition, RegistryExecution
from openchem.domain.calculator_support import is_offered_by_default
from openchem.domain.calculator_taxonomy import FALLBACK_TASK_GROUP, TASK_GROUPS

#: Run by "Run recommended", ticked by default in the wizard.
RECOMMENDED = "recommended"

#: Offered in the wizard's customise page, unticked.
OPTIONAL = "optional"

#: The closed set of roles. A typo would silently drop an entry from both lists.
ROLES = frozenset({RECOMMENDED, OPTIONAL})

#: A run covers the molecule selected when it starts.
SCOPE_THIS = "this"

#: A run covers every molecule in the project.
SCOPE_ALL = "all"

#: A run covers molecules the person chose, which a `GoalRun` carries by id.
SCOPE_CHOSEN = "chosen"

#: The closed set of scopes. The same three words Properties' "Run on" uses.
SCOPES = frozenset({SCOPE_THIS, SCOPE_ALL, SCOPE_CHOSEN})


@dataclass(frozen=True)
class Recommendation:
    """One calculator in a goal, with why it is there."""

    calculator_id: str
    role: str
    #: One line: what this adds to answering the goal. Shown beside the entry.
    reason: str
    #: Settings that differ from the calculator's registered defaults, by parameter
    #: name. Empty almost everywhere: a recommendation that needs non-default
    #: settings to make sense is a sign the default is wrong, not a reason to
    #: override it here.
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))


@dataclass(frozen=True)
class Goal:
    """A question a person brings, and the calculators that answer it."""

    goal_id: str
    #: The question, in the person's words.
    question: str
    entries: tuple[Recommendation, ...]

    @property
    def label(self) -> str:
        return TASK_GROUPS[self.goal_id]

    def recommended(self) -> tuple[Recommendation, ...]:
        return tuple(e for e in self.entries if e.role == RECOMMENDED)

    def optional(self) -> tuple[Recommendation, ...]:
        return tuple(e for e in self.entries if e.role == OPTIONAL)

    def recommended_ids(self) -> tuple[str, ...]:
        return tuple(e.calculator_id for e in self.recommended())

    def entry(self, calculator_id: str) -> Recommendation | None:
        return next((e for e in self.entries if e.calculator_id == calculator_id), None)


def _r(calculator_id: str, reason: str, **parameters: Any) -> Recommendation:
    return Recommendation(calculator_id, RECOMMENDED, reason, parameters)


def _o(calculator_id: str, reason: str, **parameters: Any) -> Recommendation:
    return Recommendation(calculator_id, OPTIONAL, reason, parameters)


#: Every goal, in the order the wizard lists them (the launcher's group order).
GOALS: tuple[Goal, ...] = (
    Goal(
        "identity",
        "What is this compound, and what is it called?",
        (
            _r("elemental_analysis", "Formula, average and exact mass, composition."),
            _r("substance_analysis", "Whether it is a salt, a molecule, a complex or a mixture."),
            _r("iupac_name", "Its systematic name, withheld when it cannot be checked."),
            _r("functional_groups", "The functional groups it carries."),
            _o("mass_spectrum", "The isotope envelope of a chosen ion."),
            _o("locants", "The IUPAC numbering drawn onto the structure."),
        ),
    ),
    Goal(
        "charge",
        "Where is the charge, and how polar is it?",
        (
            _r("gasteiger_charge_at_ph", "Partial charge on every atom, at a chosen pH."),
            _r("isoelectric_point", "The pH at which it carries no net charge."),
            _r("geometry_partial_charge", "Partial charges on the 3D structure."),
            _r("dipole_moment", "How polar the 3D structure is, as a vector."),
            _r("polarizability", "How easily its electrons are displaced."),
            _o("oxidation_states", "Formal oxidation state of each atom."),
            _o("atomic_polarizability", "Polarizability atom by atom."),
            _o("orbital_electronegativity", "Electronegativity of each atom's orbitals."),
            _o("lewis_sites", "Which atoms can give or accept an electron pair."),
            _o("huckel_analysis", "Huckel pi-orbital energies, for a conjugated system."),
            _o("huckel_pi_density", "Pi-electron density per atom (Huckel)."),
        ),
    ),
    Goal(
        "solubility",
        "How does it behave in water: ionisation, lipophilicity, solubility?",
        (
            _r("pka", "Where each ionisable group gains or loses a proton."),
            _r("major_microspecies", "The form that dominates at a chosen pH."),
            _r("logd", "Lipophilicity at a chosen pH."),
            _r("crippen_logp_contrib", "LogP, atom by atom."),
            _r("solubility", "A bounded estimate of aqueous solubility."),
            _o("pka_microspecies", "The full distribution of forms against pH."),
            _o("hansen_solubility", "Hansen parameters, for choosing a solvent."),
        ),
    ),
    Goal(
        "shape",
        "What shape and surface does it have?",
        (
            _r("geometry_analysis", "Bond lengths, angles and torsions of the 3D structure."),
            _r("polar_surface_area", "Polar surface area from the 2D structure."),
            _r("surface_analysis", "Molecular surface area of the 3D structure."),
            _r("steric_analysis", "How much room it takes up, in the 3D structure."),
            _o("atom_sasa", "Accessible surface area, atom by atom."),
            _o("griffin_hlb", "Hydrophilic-lipophilic balance (Griffin)."),
        ),
    ),
    Goal(
        "topology",
        "How is it connected, and what stereochemistry does it have?",
        (
            _r("topology_analysis", "Graph indices of the molecule."),
            _r("ring_systems", "Its rings and fused ring systems."),
            _r("stereocenters", "Which centres are stereogenic."),
            _r("hbond_vs_ph", "Hydrogen-bond donors and acceptors across pH."),
            _o("stereo_descriptors", "R/S and E/Z labels."),
            _o("bird_aromaticity", "Aromaticity from bond-length uniformity (Bird), 3D."),
            _o("homa_aromaticity", "Aromaticity from bond-length deviation (HOMA), 3D."),
            _o("topology_distance_degree", "Distance degree of each atom."),
            _o("topology_eccentricity", "Eccentricity of each atom."),
        ),
    ),
    Goal(
        "druglike",
        "Is it drug-like, and what would worry a reviewer?",
        (
            _r("admet_ml", "ADMET predictions: hERG, CYP, Ames, absorption."),
            _r("cns_mpo", "CNS multi-parameter optimisation score."),
            _r("bbb_descriptors", "Descriptors behind blood-brain-barrier scores."),
            _r("regulatory_screen", "A screen against regulatory lists."),
        ),
    ),
    Goal(
        "structures",
        "What other structures does this one stand for?",
        (
            _r("tautomers", "Its tautomers."),
            _r("stereoisomers", "Its stereoisomers."),
            _r("resonance_forms", "Its resonance forms."),
            _o("structural_frameworks", "Its scaffold and framework."),
        ),
    ),
    Goal(
        "spectra",
        "What spectra and energetics can be read off the structure?",
        (
            _r("nmr_database", "NMR shifts looked up from experimental data."),
            _o("oxygen_balance", "Oxygen balance, for energetic materials."),
        ),
    ),
)


@dataclass(frozen=True)
class GoalRun:
    """One run of a goal, fixed at the moment it was asked for.

    **IMMUTABLE ON PURPOSE.** The wizard builds this when Run is pressed and hands it on;
    from then on nothing the person does in the wizard (another goal, another tick, another
    scope) can reach it, and a second press makes a second one with its own `run_id`. The
    ids and settings are tuples and read-only mappings for the same reason.

    `scope_uuids` is carried only for `SCOPE_CHOSEN`. "This molecule" and "all molecules"
    are resolved by whoever runs it, at that moment, because the selection and the project
    are theirs to read -- a wizard that resolved them early would run on the molecule that
    WAS selected when it opened.
    """

    goal_id: str
    calculator_ids: tuple[str, ...]
    #: Settings that differ from the defaults, by calculator id. Absent means defaults.
    parameters: Mapping[str, Mapping[str, Any]]
    scope_mode: str
    scope_uuids: tuple[str, ...] = ()
    run_id: str = field(default_factory=lambda: _uuid.uuid4().hex)

    def __post_init__(self) -> None:
        if self.scope_mode not in SCOPES:
            raise ValueError(f"unknown scope {self.scope_mode!r}; expected one of {sorted(SCOPES)}")
        object.__setattr__(self, "calculator_ids", tuple(self.calculator_ids))
        object.__setattr__(self, "scope_uuids", tuple(self.scope_uuids))
        object.__setattr__(
            self,
            "parameters",
            MappingProxyType({cid: MappingProxyType(dict(p)) for cid, p in dict(self.parameters).items()}),
        )

    def chosen_parameters(self) -> dict[str, dict[str, Any]]:
        """A plain copy for `build_execution_plan`, which takes ordinary mappings."""
        return {cid: dict(p) for cid, p in self.parameters.items()}


def goal_of(goal_id: str) -> Goal | None:
    return next((g for g in GOALS if g.goal_id == goal_id), None)


def goal_ids() -> tuple[str, ...]:
    return tuple(g.goal_id for g in GOALS)


def needs_conformer(definition: CalculatorDefinition) -> bool:
    """Whether a calculator is run on a 3D structure rather than the drawing."""
    return getattr(definition, "calculation_input", None) == GEOMETRY


def validate_goals(
    definition_of: Callable[[str], CalculatorDefinition | None],
    goals: tuple[Goal, ...] = GOALS,
) -> list[str]:
    """Every way `goals` has drifted from what is registered. Empty means sound.

    A recommendation must name a calculator that exists, runs in the launcher (not from
    a panel of its own), is offered by default, and needs no input only the person can
    give; every setting it overrides must exist and be allowed. Anything else is a
    recommendation that would run nothing, or something the person cannot see.
    """
    problems: list[str] = []
    seen_goals: set[str] = set()
    for goal in goals:
        if goal.goal_id in seen_goals:
            problems.append(f"goal {goal.goal_id!r} is listed twice")
        seen_goals.add(goal.goal_id)
        if goal.goal_id not in TASK_GROUPS or goal.goal_id == FALLBACK_TASK_GROUP:
            problems.append(f"goal {goal.goal_id!r} is not a task group with a heading")
        if not goal.recommended():
            problems.append(f"goal {goal.goal_id!r} recommends nothing")
        seen: set[str] = set()
        for entry in goal.entries:
            where = f"{goal.goal_id}/{entry.calculator_id}"
            if entry.calculator_id in seen:
                problems.append(f"{where}: listed twice")
            seen.add(entry.calculator_id)
            if entry.role not in ROLES:
                problems.append(f"{where}: unknown role {entry.role!r}")
            if not entry.reason.strip():
                problems.append(f"{where}: no reason given")
            definition = definition_of(entry.calculator_id)
            if definition is None:
                problems.append(f"{where}: no such calculator")
                continue
            if not isinstance(definition.execution, RegistryExecution):
                problems.append(f"{where}: runs from its own panel, so it cannot be recommended here")
                continue
            if not is_offered_by_default(definition):
                problems.append(f"{where}: hidden by default, so the person cannot see what is being run")
            by_name = {p.name: p for p in definition.parameters}
            for parameter in definition.parameters:
                if parameter.required and parameter.name not in entry.parameters:
                    problems.append(f"{where}: needs {parameter.name!r}, which only the person can give")
            for name, value in entry.parameters.items():
                parameter = by_name.get(name)
                if parameter is None:
                    problems.append(f"{where}: overrides unknown setting {name!r}")
                    continue
                if parameter.choices is not None and value not in parameter.choices:
                    problems.append(f"{where}: {name}={value!r} is not one of {parameter.choices}")
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    if parameter.minimum is not None and value < parameter.minimum:
                        problems.append(f"{where}: {name}={value!r} is below {parameter.minimum}")
                    if parameter.maximum is not None and value > parameter.maximum:
                        problems.append(f"{where}: {name}={value!r} is above {parameter.maximum}")
    return problems
