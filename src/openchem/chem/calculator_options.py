"""Options shared across calculators.

ChemAxon exposes the same handful of controls on nearly every plugin --
decimal places, and "take major microspecies at pH". Defining them once
here rather than re-declaring them in 34 registrations keeps their labels,
defaults and behaviour identical everywhere, which is the whole point of a
shared option: a user who learns it on one calculator has learned it on
all of them.
"""

from __future__ import annotations

from typing import Any

from rdkit import Chem

from openchem.domain.calculator import CalculatorParameter

DEFAULT_DECIMAL_PLACES = 2
DEFAULT_PH = 7.4


def decimal_places_parameter(default: int = DEFAULT_DECIMAL_PLACES) -> CalculatorParameter:
    return CalculatorParameter(
        name="decimal_places",
        label="Decimal places",
        kind="int",
        default=default,
        minimum=0,
        maximum=8,
    )


def microspecies_parameters() -> list[CalculatorParameter]:
    """The pair that always travel together -- a pH with nothing to apply
    it to is meaningless, so neither is offered alone."""
    return [
        CalculatorParameter(
            name="major_microspecies",
            label="Take major microspecies",
            kind="bool",
            default=False,
        ),
        CalculatorParameter(
            name="pH", label="at pH", kind="float", default=DEFAULT_PH, minimum=0.0, maximum=14.0
        ),
    ]


def decimals(parameters: dict[str, Any] | None) -> int:
    """Clamped, because a negative or absurd width would break formatting
    rather than merely look odd."""
    value = (parameters or {}).get("decimal_places", DEFAULT_DECIMAL_PLACES)
    try:
        return max(0, min(8, int(value)))
    except (TypeError, ValueError):
        return DEFAULT_DECIMAL_PLACES


def fmt(value: float, parameters: dict[str, Any] | None) -> str:
    """Format one number at the caller's requested precision."""
    return f"{value:.{decimals(parameters)}f}"


def apply_microspecies(mol: Chem.Mol, parameters: dict[str, Any] | None) -> Chem.Mol:
    """The dominant protonation form at the requested pH, when asked for.

    Falls back to the drawn structure if Dimorphite-DL cannot build one --
    an unavailable microspecies should not fail a calculation that is
    perfectly well defined on the structure as drawn.
    """
    parameters = parameters or {}
    if not parameters.get("major_microspecies"):
        return mol
    try:
        from openchem.chem.pka_providers import protonate_at_ph

        return protonate_at_ph(mol, float(parameters.get("pH", DEFAULT_PH)))
    except Exception:  # noqa: BLE001 - the drawn form remains a valid answer
        return mol


def microspecies_note(parameters: dict[str, Any] | None) -> list[str]:
    """A line stating the structure was changed, or nothing. Silently
    computing on a different structure than the one on screen is the kind
    of thing that costs someone an afternoon."""
    parameters = parameters or {}
    if not parameters.get("major_microspecies"):
        return []
    return [f"Computed on the major microspecies at pH {float(parameters.get('pH', DEFAULT_PH)):g}."]


#: The pH curves sampled 0-14 at a fixed step until these existed. The
#: default still does, so nothing changes for a user who never opens the
#: dialog -- but someone studying the physiological window can ask for
#: 6-8 at 0.05 and get 40 points across it instead of 8.
DEFAULT_PH_MIN = 0.0
DEFAULT_PH_MAX = 14.0
DEFAULT_PH_STEP = 0.25


def ph_range_parameters(step: float = DEFAULT_PH_STEP) -> list[CalculatorParameter]:
    """Range and resolution for a property-versus-pH curve.

    Three parameters rather than one, because a range with no step is
    unusable at a narrow width -- 6-8 sampled every 0.25 is nine points,
    which draws as a polygon rather than a curve.

    `step` is a parameter of THIS function because the curves do not agree
    on a sensible default: the H-bond count only changes when a group
    flips protonation, so it samples coarsely, while logD is smooth and
    benefits from a finer grid.
    """
    return [
        CalculatorParameter(
            name="ph_min", label="pH from", kind="float",
            default=DEFAULT_PH_MIN, minimum=-2.0, maximum=16.0,
        ),
        CalculatorParameter(
            name="ph_max", label="pH to", kind="float",
            default=DEFAULT_PH_MAX, minimum=-2.0, maximum=16.0,
        ),
        CalculatorParameter(
            name="ph_step", label="Step", kind="float",
            default=step, minimum=0.01, maximum=2.0,
        ),
    ]


def ph_grid_from(parameters: dict[str, Any] | None, step: float = DEFAULT_PH_STEP) -> list[float]:
    """The pH values to sample, from the caller's parameters.

    Defensive about its own inputs because these arrive from a dialog: a
    reversed range is swapped rather than returning nothing, a zero or
    negative step falls back to the default rather than looping forever,
    and the point count is capped so that asking for 0-14 at 0.01 cannot
    hand a widget 1,400 points to draw.
    """
    parameters = parameters or {}

    def number(name: str, fallback: float) -> float:
        try:
            return float(parameters.get(name, fallback))
        except (TypeError, ValueError):
            return fallback

    low = number("ph_min", DEFAULT_PH_MIN)
    high = number("ph_max", DEFAULT_PH_MAX)
    if low > high:
        low, high = high, low
    if low == high:  # a single-point "curve" is not one
        high = low + DEFAULT_PH_STEP
    size = number("ph_step", step)
    if size <= 0:
        size = step
    count = int(round((high - low) / size)) + 1
    if count > 1001:
        size = (high - low) / 1000
        count = 1001
    return [low + index * size for index in range(count)]
