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
