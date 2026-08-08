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
    parameter from `kind` (`"float"`/`"int"`/`"choice"`/`"bool"`/`"text"`) rather
    than every calculator hand-building its own dialog.
    """

    name: str  # key this value is stored under in CalculationRequest.parameters
    label: str  # shown next to the widget in the settings dialog
    kind: str  # "float" | "int" | "choice" | "bool" | "text"
    default: Any
    minimum: float | None = None
    maximum: float | None = None
    choices: list[str] | None = None


#: The kinds of structure a calculator can be asked about. A small,
#: closed vocabulary -- unlike `category` and `tags`, which are free
#: strings -- because a typo here would silently make a calculator apply
#: to nothing, and `test_every_calculator_declares_a_known_structure_kind`
#: turns that into a failure instead.
MOLECULE = "molecule"
CRYSTAL = "crystal"
MACROMOLECULE = "macromolecule"
STRUCTURE_KINDS = frozenset({MOLECULE, CRYSTAL, MACROMOLECULE})


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
    #: Which structure kinds this calculator can honestly be run on.
    #:
    #: **The default is the restrictive one, and that is the whole
    #: point.** This replaced a hand-maintained blocklist of category
    #: names in `chem/crystal_report.py`, which had rotted in both
    #: directions -- measured before the change: 49 registered
    #: calculators, 22 correctly listed as inapplicable to a crystal, 27
    #: silently treated as applicable (IUPAC Name, Tautomers, Molecular
    #: Dynamics, NMR Shifts among them), and 3 of the 13 blocked category
    #: names matching no live category at all.
    #:
    #: It rotted because `category` is deliberately a free string, so
    #: adding one "needs no code change" -- and therefore nothing ever
    #: forced anyone back to the blocklist. Declaring capability here
    #: inverts that: a calculator registered without a thought is
    #: molecule-only, which is the answer that cannot be wrong about a
    #: periodic solid. Applying to a crystal is an opt-in somebody had to
    #: mean.
    applies_to: frozenset[str] = frozenset({MOLECULE})
    # "empirical" | "ab_initio" | None (Phase 22) -- lets a UI badge how
    # trustworthy a result is, same honesty spirit as the hERG risk-factor
    # checklist's "not a prediction" label. Populated only where it's
    # actually known; left unset rather than guessed for calculators
    # outside whatever phase introduced this field.
    prediction_basis: str | None = None
    # Free-form labels for search and filtering (Phase 26). Additive,
    # default empty -- a calculator without tags is still fully usable.
    # Earned its place at ~15 registered calculators; at 4 it would have
    # been ceremony. Plain strings for the same reason `category` is:
    # a new tag needs no code change.
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class CalculationRequest:
    """A request to run one registered calculator against one molecule —
    the generic shape `DescriptorService.request_calculation` takes,
    replacing a one-off method per calculator kind."""

    calculator_id: str
    molecule_uuid: str
    parameters: dict[str, Any] = field(default_factory=dict)
