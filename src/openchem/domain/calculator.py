from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from openchem.domain.common import ScientificResult


@dataclass(frozen=True, kw_only=True)
class RegistryExecution:
    """This calculator runs synchronously through
    `CalculatorRegistry.compute()` / `DescriptorService.run_calculator()` --
    `PropertyPanel` offers an "Open [Calculator]..." row for it. A
    `RegistryExecution` cannot be constructed without a real callable, so
    there is no "sometimes runnable" state to special-case elsewhere.

    First callable argument is an `rdkit.Chem.Mol` at runtime -- typed as
    `Any` here, not `Chem.Mol`, since `domain/` stays free of RDKit/Qt
    imports (same layering rule every other module in this package
    follows).
    """

    compute: Callable[[Any, str, dict[str, Any]], ScientificResult]


@dataclass(frozen=True, kw_only=True)
class ServiceExecution:
    """This calculator is owned and run by its own service/panel, not
    through `CalculatorRegistry.compute()` -- registered for discovery
    only. Real invocation happens through `service_name`'s own request
    method, driven from `panel_name`.
    """

    service_name: str
    panel_name: str


CalculatorExecution = RegistryExecution | ServiceExecution


@dataclass(frozen=True, kw_only=True)
class CalculatorParameter:
    """One configurable input a calculator's settings dialog should show —
    the generic `CalculatorSettingsDialog` builds one Qt widget per
    parameter from `kind` (`"float"`/`"int"`/`"choice"`/`"bool"`) rather
    than every calculator hand-building its own dialog.
    """

    name: str  # key this value is stored under in CalculationRequest.parameters
    label: str  # shown next to the widget in the settings dialog
    kind: str  # "float" | "int" | "choice" | "bool"
    default: Any
    minimum: float | None = None
    maximum: float | None = None
    choices: list[str] | None = None


@dataclass(frozen=True, kw_only=True)
class CalculatorDefinition:
    """Metadata for one registered calculator (`CalculatorRegistry`) —
    `category` is a plain string, not an enum, so a new category needs no
    code change, just a new registration.
    """

    calculator_id: str
    display_name: str
    category: str
    description: str
    execution: CalculatorExecution
    parameters: list[CalculatorParameter] = field(default_factory=list)
    # "empirical" | "ab_initio" | None (Phase 22) -- lets a UI badge how
    # trustworthy a result is, same honesty spirit as the hERG risk-factor
    # checklist's "not a prediction" label. Populated only where it's
    # actually known; left unset rather than guessed for calculators
    # outside whatever phase introduced this field.
    prediction_basis: str | None = None


@dataclass(frozen=True, kw_only=True)
class CalculationRequest:
    """A request to run one registered calculator against one molecule —
    the generic shape `DescriptorService.request_calculation` takes,
    replacing a one-off method per calculator kind."""

    calculator_id: str
    molecule_uuid: str
    parameters: dict[str, Any] = field(default_factory=dict)
