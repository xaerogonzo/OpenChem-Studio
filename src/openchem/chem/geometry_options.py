"""The options of the Geometry calculator, declared once and read once.

They are modelled on ChemAxon's Geometrical Descriptors plugin because those are the controls
people expect (energy unit, optimise before the energy, optimise before the projection, which
conformer to use, how tightly to optimise). **They are OpenChem's own implementations of those
controls, not ChemAxon's**: ChemAxon publishes no defaults and no algorithms for any of them,
so the defaults here are chosen for what leaves existing results unchanged, and every value is
recorded in the result's provenance.

**THE STORED VALUE OF A CHOICE IS A CODE, NEVER ITS LABEL.** A result's identity includes the
parameters it was computed with, so a label that is reworded must not orphan every stored
result; the labels are `CalculatorParameter.choice_labels`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openchem.chem.geometry_preparation import DEFAULT_LIMIT, LIMIT_LEVELS
from openchem.domain.calculator import CalculatorParameter

#: kcal/mol to kJ/mol: the thermochemical calorie, exactly.
KJ_PER_KCAL = 4.184

#: Energy unit codes and what is shown. The energy is always COMPUTED in kcal/mol and converted
#: for display, so switching the unit converts the same stored number rather than computing again.
UNIT_KCAL = "kcal_per_mol"
UNIT_KJ = "kj_per_mol"
UNIT_LABELS = {UNIT_KCAL: "kcal/mol", UNIT_KJ: "kJ/mol"}

#: Which conformer the numbers are measured on.
#:
#: `never` -- the geometry as it is (the behaviour before the option existed; a 2D structure is
#: refused, as it always was). `if_2d` -- the geometry as it is when it is 3D, a generated lowest-
#: energy one when it is not. `always` -- the lowest-energy of the generated candidates and the
#: geometry supplied.
POLICY_NEVER = "never"
POLICY_IF_2D = "if_2d"
POLICY_ALWAYS = "always"
POLICY_LABELS = {
    POLICY_NEVER: "Never: use the conformer as it is",
    POLICY_IF_2D: "Only if the structure is 2D",
    POLICY_ALWAYS: "Always: the lowest of several",
}

DEFAULT_CONFORMER_COUNT = 20
DEFAULT_RADIUS_SCALE = 1.0


@dataclass(frozen=True)
class GeometryOptions:
    """The Geometry calculator's options, validated."""

    energy_unit: str = UNIT_KCAL
    conformer_policy: str = POLICY_NEVER
    conformer_count: int = DEFAULT_CONFORMER_COUNT
    optimise_mmff: bool = False
    optimise_projection: bool = False
    optimisation_limit: str = DEFAULT_LIMIT
    radius_scale: float = DEFAULT_RADIUS_SCALE

    @property
    def unit_label(self) -> str:
        return UNIT_LABELS[self.energy_unit]

    def convert(self, kcal_per_mol: float) -> float:
        """An energy computed in kcal/mol, in the unit asked for."""
        return kcal_per_mol * KJ_PER_KCAL if self.energy_unit == UNIT_KJ else kcal_per_mol


def geometry_parameters() -> list[CalculatorParameter]:
    """The options, in the order the settings dialog shows them (after Decimal places)."""
    return [
        CalculatorParameter(
            name="energy_unit", label="Energy unit", kind="choice", default=UNIT_KCAL,
            choices=[UNIT_KCAL, UNIT_KJ], choice_labels=[UNIT_LABELS[UNIT_KCAL], UNIT_LABELS[UNIT_KJ]],
        ),
        CalculatorParameter(
            name="conformer_policy", label="Use the lowest-energy conformer", kind="choice",
            default=POLICY_NEVER,
            choices=[POLICY_NEVER, POLICY_IF_2D, POLICY_ALWAYS],
            choice_labels=[POLICY_LABELS[p] for p in (POLICY_NEVER, POLICY_IF_2D, POLICY_ALWAYS)],
        ),
        CalculatorParameter(
            name="conformer_count", label="Conformers to try", kind="int",
            default=DEFAULT_CONFORMER_COUNT, minimum=1, maximum=200,
        ),
        CalculatorParameter(
            name="optimise_mmff", label="Optimise before the MMFF94 energy", kind="bool", default=False,
        ),
        CalculatorParameter(
            name="optimise_projection", label="Optimise before the projections", kind="bool", default=False,
        ),
        CalculatorParameter(
            name="optimisation_limit", label="Optimisation limit", kind="choice", default=DEFAULT_LIMIT,
            choices=list(LIMIT_LEVELS), choice_labels=list(LIMIT_LEVELS.values()),
        ),
        CalculatorParameter(
            name="radius_scale", label="Projection radii (x van der Waals)", kind="float",
            default=DEFAULT_RADIUS_SCALE, minimum=0.5, maximum=3.0,
        ),
    ]


def geometry_options(parameters: dict[str, Any] | None) -> GeometryOptions:
    """The options from a parameter dict, with anything missing or unrecognised at its default.

    Lenient on purpose, like `decimals`: a stored project carrying a value this build no longer
    offers should open showing the plain answer, not fail to open.
    """
    values = parameters or {}

    def choice(name: str, allowed, default):
        value = values.get(name, default)
        return value if value in allowed else default

    try:
        count = max(1, min(200, int(values.get("conformer_count", DEFAULT_CONFORMER_COUNT))))
    except (TypeError, ValueError):
        count = DEFAULT_CONFORMER_COUNT
    try:
        scale = float(values.get("radius_scale", DEFAULT_RADIUS_SCALE))
    except (TypeError, ValueError):
        scale = DEFAULT_RADIUS_SCALE
    if not 0.5 <= scale <= 3.0:
        scale = DEFAULT_RADIUS_SCALE
    return GeometryOptions(
        energy_unit=choice("energy_unit", UNIT_LABELS, UNIT_KCAL),
        conformer_policy=choice("conformer_policy", POLICY_LABELS, POLICY_NEVER),
        conformer_count=count,
        optimise_mmff=bool(values.get("optimise_mmff", False)),
        optimise_projection=bool(values.get("optimise_projection", False)),
        optimisation_limit=choice("optimisation_limit", LIMIT_LEVELS, DEFAULT_LIMIT),
        radius_scale=scale,
    )
