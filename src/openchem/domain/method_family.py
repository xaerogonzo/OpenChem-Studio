"""The declared method-family axis on a calculator, if it has one.

Codes and labels come from that parameter's `choices` / `choice_labels`.
Nothing here lists Partial Charge (3D) methods by name.
"""

from __future__ import annotations

import uuid
from typing import Any

from openchem.domain.calculator import (
    CalculationRequest,
    CalculatorDefinition,
    CalculatorParameter,
    active_parameters,
)


def family_axis_of(definition: CalculatorDefinition) -> CalculatorParameter | None:
    """The one `family_axis` parameter, or None."""
    for parameter in definition.parameters:
        if parameter.family_axis:
            return parameter
    return None


def family_choice_labels(axis: CalculatorParameter) -> list[str]:
    """Display names in the declared choice order."""
    if axis.choice_labels:
        return list(axis.choice_labels)
    return list(axis.choices or ())


def family_shared_parameters(
    definition: CalculatorDefinition, values: dict[str, Any]
) -> dict[str, Any]:
    """Active dialog values with the family-axis key removed."""
    axis = family_axis_of(definition)
    shared = dict(values)
    if axis is not None:
        shared.pop(axis.name, None)
    return active_parameters(definition, shared)


def family_requests(
    definition: CalculatorDefinition,
    molecule_uuid: str,
    values: dict[str, Any],
) -> list[CalculationRequest]:
    """One request per family-axis code, sharing the rest of `values`."""
    axis = family_axis_of(definition)
    if axis is None or not axis.choices:
        raise ValueError(f"{definition.calculator_id} has no family axis")
    shared = family_shared_parameters(definition, values)
    requests: list[CalculationRequest] = []
    for code in axis.choices:
        parameters = dict(shared)
        parameters[axis.name] = code
        requests.append(
            CalculationRequest(
                calculator_id=definition.calculator_id,
                molecule_uuid=molecule_uuid,
                parameters=parameters,
                request_id=uuid.uuid4().hex,
            )
        )
    return requests
