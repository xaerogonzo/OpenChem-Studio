"""Settings for a goal run, kept apart from a calculator's registered defaults.

A direct run from Properties still uses the registered default. A goal run
resolves three layers, and only the goal run sees the result:

1. A choice this person saved for goal runs, when it still matches the
   calculator as it is registered now.
2. The recommendation's own parameters (Spectra asks for 1H; the NMR
   calculator's default stays 13C).
3. The registered default.

The saved layer is keyed by calculator id and parameter name and holds the
machine value, never the label. An unknown name or a value the calculator no
longer allows is dropped and logged, and the next layer is used.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from openchem.domain.calculator import CalculatorDefinition, CalculatorParameter
from openchem.domain.calculator_goals import GOALS, Goal

logger = logging.getLogger(__name__)

#: Where the saved choices live. Not a `Preference`: those are a bool or an int,
#: and this is a map of calculator settings.
GOAL_PARAMETER_KEY = "goals/parameter_overrides"

#: Shown in Settings, not on the customise row. A display knob, not the chemistry.
_DISPLAY_PARAMETERS = frozenset({"decimal_places"})


def resolve_parameters(
    definition: CalculatorDefinition,
    recommendation: Mapping[str, Any],
    saved: Mapping[str, Any],
) -> dict[str, Any]:
    """Every parameter of `definition`, after the three layers.

    Saved values are checked first so a bad stored value cannot hide a valid
    recommendation. Dropped values are logged and the layer below is kept.
    """
    values = {parameter.name: parameter.default for parameter in definition.parameters}
    values.update(_kept(definition, recommendation, source="recommendation"))
    values.update(_kept(definition, saved, source="saved goal choice"))
    return values


def parameters_for_run(
    definition: CalculatorDefinition,
    recommendation: Mapping[str, Any],
    saved: Mapping[str, Any],
) -> dict[str, Any]:
    """The settings a goal run should carry: only what differs from the registered default.

    An absent key already means "the registered default" everywhere a run is
    built. Sending the whole resolved map would make this a second copy of
    those defaults. A saved choice that matches the default is omitted, so it
    does not become a second default for a direct Properties run -- this
    function is only called while building a goal run.
    """
    resolved = resolve_parameters(definition, recommendation, saved)
    return {
        parameter.name: resolved[parameter.name]
        for parameter in definition.parameters
        if parameter.name in resolved and resolved[parameter.name] != parameter.default
    }


def chemistry_summary(definition: CalculatorDefinition, resolved: Mapping[str, Any]) -> str:
    """One line of the choices that change the chemistry, from the parameter definitions.

    Decimal places and the same kind of display knob stay in Settings. A
    parameter whose controller is off (a pH while pH-dependent is unticked)
    is left out, because it will not be used.
    """
    by_name = {parameter.name: parameter for parameter in definition.parameters}
    parts: list[str] = []
    for parameter in definition.parameters:
        if parameter.name in _DISPLAY_PARAMETERS:
            continue
        if parameter.kind not in {"choice", "bool", "float"}:
            continue
        if not _controller_on(parameter, resolved, by_name):
            continue
        value = resolved.get(parameter.name, parameter.default)
        if parameter.kind == "bool":
            if value:
                parts.append(parameter.label)
            continue
        parts.append(f"{parameter.label}: {_choice_label(parameter, value)}")
    return "; ".join(parts)


@dataclass(frozen=True)
class RecommendedCalculators:
    """The recommended calculators of every goal, in goal order, each id once."""

    calculator_ids: tuple[str, ...]
    #: The recommendation's own parameters, by calculator id. Empty means none.
    recommendation_parameters: Mapping[str, Mapping[str, Any]]
    #: Set when one calculator is recommended twice with different parameters.
    conflict_id: str = ""


def recommended_calculators(goals: Iterable[Goal] = GOALS) -> RecommendedCalculators:
    """Walk goals in order, then each goal's recommended entries.

    The same id with the same parameters is kept once. The same id with
    different parameters is a conflict: nothing is returned to run, and
    `conflict_id` names the calculator.
    """
    order: list[str] = []
    parameters: dict[str, dict[str, Any]] = {}
    for goal in goals:
        for entry in goal.recommended():
            raw = dict(entry.parameters)
            previous = parameters.get(entry.calculator_id)
            if previous is None:
                parameters[entry.calculator_id] = raw
                order.append(entry.calculator_id)
                continue
            if previous != raw:
                return RecommendedCalculators((), {}, entry.calculator_id)
    return RecommendedCalculators(tuple(order), parameters)


@dataclass(frozen=True)
class RecommendedBatch:
    """A run of every recommended calculator. It is not a goal, so it has no goal id."""

    calculator_ids: tuple[str, ...]
    parameters: Mapping[str, Mapping[str, Any]]
    scope_mode: str
    scope_uuids: tuple[str, ...] = ()


def confirmation_text(
    *,
    calculator_count: int,
    job_count: int,
    molecule_count: int,
    conformer_names: Iterable[str],
    lacking_conformers: int,
    exclusions: str,
) -> str:
    """What the person is asked before every recommended calculator starts."""
    lines = [
        f"This will run {calculator_count} recommended calculators "
        f"({job_count} calculations on {molecule_count} molecule(s))."
    ]
    names = list(conformer_names)
    if names:
        shown = ", ".join(names[:6]) + ("..." if len(names) > 6 else "")
        lines.append(f"These need a 3D structure: {shown}.")
        if lacking_conformers:
            lines.append(
                f"{lacking_conformers} of {molecule_count} molecule(s) have none yet. "
                "Those calculations will say so."
            )
    if exclusions:
        lines.append(exclusions)
    lines.append("Nothing starts until you continue.")
    return "\n\n".join(lines)


class GoalParameterStore:
    """The saved goal-run choices. Writing happens when Settings is accepted."""

    def __init__(self, overrides: Mapping[str, Mapping[str, Any]] | None = None) -> None:
        self._overrides: dict[str, dict[str, Any]] = {}
        for calculator_id, parameters in (overrides or {}).items():
            if isinstance(parameters, Mapping):
                self._overrides[str(calculator_id)] = dict(parameters)

    @classmethod
    def from_settings(cls, settings: Any) -> GoalParameterStore:
        if settings is None:
            return cls()
        return cls(_decode(settings.get(GOAL_PARAMETER_KEY, "")))

    def save(self, settings: Any) -> None:
        if settings is None:
            return
        settings.set(GOAL_PARAMETER_KEY, json.dumps(self._overrides, sort_keys=True))

    def get(self, calculator_id: str) -> dict[str, Any]:
        return dict(self._overrides.get(calculator_id, {}))

    def remember(self, calculator_id: str, parameters: Mapping[str, Any]) -> None:
        self._overrides[calculator_id] = dict(parameters)

    def as_dict(self) -> dict[str, dict[str, Any]]:
        return {calculator_id: dict(parameters) for calculator_id, parameters in self._overrides.items()}


def _kept(
    definition: CalculatorDefinition,
    raw: Mapping[str, Any],
    *,
    source: str,
) -> dict[str, Any]:
    by_name = {parameter.name: parameter for parameter in definition.parameters}
    kept: dict[str, Any] = {}
    for name, value in raw.items():
        parameter = by_name.get(name)
        if parameter is None:
            logger.info(
                "%s: %s dropped unknown setting %s",
                definition.calculator_id,
                source,
                name,
            )
            continue
        if not _allowed(parameter, value):
            logger.info(
                "%s: %s dropped %s=%r; it is not allowed",
                definition.calculator_id,
                source,
                name,
                value,
            )
            continue
        kept[name] = value
    return kept


def _allowed(parameter: CalculatorParameter, value: Any) -> bool:
    if parameter.kind == "bool":
        return isinstance(value, bool)
    if parameter.kind == "choice":
        return value in (parameter.choices or [])
    if parameter.kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            return False
        return _in_range(parameter, value)
    if parameter.kind == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        return _in_range(parameter, float(value))
    if parameter.kind in {"text", "smiles"}:
        return isinstance(value, str)
    return False


def _in_range(parameter: CalculatorParameter, value: float) -> bool:
    if parameter.minimum is not None and value < parameter.minimum:
        return False
    if parameter.maximum is not None and value > parameter.maximum:
        return False
    return True


def _controller_on(
    parameter: CalculatorParameter,
    resolved: Mapping[str, Any],
    by_name: Mapping[str, CalculatorParameter],
) -> bool:
    controller_name = parameter.enabled_by
    seen: set[str] = set()
    while controller_name is not None:
        if controller_name in seen or controller_name not in by_name:
            return False
        seen.add(controller_name)
        controller = by_name[controller_name]
        if not resolved.get(controller_name, controller.default):
            return False
        controller_name = controller.enabled_by
    return True


def _choice_label(parameter: CalculatorParameter, value: Any) -> str:
    if parameter.choices and parameter.choice_labels:
        try:
            return parameter.choice_labels[list(parameter.choices).index(value)]
        except ValueError:
            pass
    return str(value)


def _decode(raw: Any) -> dict[str, dict[str, Any]]:
    if isinstance(raw, str):
        if not raw.strip():
            return {}
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            logger.info("saved goal choices could not be read and were ignored")
            return {}
    if not isinstance(raw, dict):
        return {}
    decoded: dict[str, dict[str, Any]] = {}
    for calculator_id, parameters in raw.items():
        if isinstance(parameters, dict):
            decoded[str(calculator_id)] = dict(parameters)
    return decoded
