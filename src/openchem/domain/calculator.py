from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from openchem.domain.calculator_support import CalculatorSupport
from openchem.domain.common import ScientificResult

# Re-exported: every calculator module imports its refusal codes from here.
from openchem.domain.refusal_kinds import (  # noqa: F401
    ELEMENT_OUTSIDE_PARAMETER_SET,
    INPUT_REQUIRED,
    METAL_CONTAINING_UNSUPPORTED,
    MULTICOMPONENT_UNSUPPORTED,
    NO_ORGANIC_COMPONENT,
    SIDECAR_NOT_CONFIGURED,
    MissingInput,
    RefusalKind,
    refusal_kind_of,
)


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


#: Every kind a `CalculatorParameter` may declare, and the ONLY list of
#: them. `CalculatorSettingsDialog._build_widget` dispatches on it and the
#: dialog's coverage guard derives its expected set from it, so a seventh
#: kind cannot be added to the widget factory and quietly miss the guard.
#: Closed, and refused at REGISTRATION rather than at click: an unknown
#: kind otherwise reaches `_build_widget`, matches no branch, and produces
#: a settings dialog silently missing one of its controls.
#:
#: `"smiles"` is named after what the VALUE is rather than after the
#: widget. `"molecule_choice"` would lie -- the stored value is never a
#: molecule uuid, because a uuid makes a result unreplayable in another
#: project -- and naming it for the value is what lets the same kind serve
#: a free-text SMARTS field later.
PARAMETER_KINDS = frozenset({"float", "int", "choice", "bool", "text", "smiles"})


@dataclass(frozen=True, kw_only=True)
class CalculatorParameter:
    """One configurable input a calculator's settings dialog should show —
    the generic `CalculatorSettingsDialog` builds one Qt widget per
    parameter from `kind` (see `PARAMETER_KINDS`) rather than every
    calculator hand-building its own dialog.

    **`choices` IS THE STORED VALUE VOCABULARY; `choice_labels` IS WHAT
    THE USER READS.** That split is newer than most callers and the roles
    are easy to reverse, so it is stated here rather than left to be
    inferred:

        choices        stable codes, and what lands in
                       `CalculationRequest.parameters`
        choice_labels  the prose shown in the combo box, positionally
                       matched to `choices`
        absent labels  legacy behaviour -- the displayed text IS the
                       stored value, unchanged for every existing caller

    **THE REASON IT EXISTS IS THAT THE STORED VALUE IS PART OF A RESULT'S
    IDENTITY.** `CalculatorSettingsDialog.parameters()` read
    `QComboBox.currentText()`, and `batch_service` hashes what it gets into
    `parameters_key` -- so a `"choice"` parameter stored its ENGLISH LABEL
    in every retained result's key, and rewording a label silently orphaned
    every result computed under the old wording. Do not depend on UI text
    as a cache or provenance identifier again.
    """

    name: str  # key this value is stored under in CalculationRequest.parameters
    label: str  # shown next to the widget in the settings dialog
    kind: str  # one of PARAMETER_KINDS
    default: Any
    minimum: float | None = None
    maximum: float | None = None
    choices: list[str] | None = None
    #: Display text per entry of `choices`, positionally. None keeps the
    #: legacy behaviour where the choice IS its own label.
    choice_labels: list[str] | None = None
    #: The name of a `"bool"` parameter of the same calculator that must be
    #: True for this one to mean anything -- the pH under "pH-dependent".
    #: While it is False the dialog greys this control out AND the value is
    #: not dispatched (`active_parameters`), so an irrelevant setting can
    #: neither change the computation nor be recorded as part of it.
    enabled_by: str | None = None

    def __post_init__(self) -> None:
        # AT CONSTRUCTION, so a mismatch is a failing import rather than a
        # combo box that silently shows fewer entries than it stores --
        # the same fail-closed rule the `**OPNE**` marker parse follows.
        if self.kind not in PARAMETER_KINDS:
            raise ValueError(
                f"{self.name}: unknown parameter kind {self.kind!r}; "
                f"expected one of {sorted(PARAMETER_KINDS)}"
            )
        if self.choice_labels is None:
            return
        if self.choices is None:
            raise ValueError(f"{self.name}: choice_labels without choices")
        if len(self.choice_labels) != len(self.choices):
            raise ValueError(
                f"{self.name}: {len(self.choice_labels)} choice_labels for "
                f"{len(self.choices)} choices -- they are matched positionally"
            )


#: The kinds of structure a calculator can be asked about. A small,
#: closed vocabulary -- unlike `category` and `tags`, which are free
#: strings -- because a typo here would silently make a calculator apply
#: to nothing, and `test_every_calculator_declares_a_known_structure_kind`
#: turns that into a failure instead.
MOLECULE = "molecule"
CRYSTAL = "crystal"
MACROMOLECULE = "macromolecule"
STRUCTURE_KINDS = frozenset({MOLECULE, CRYSTAL, MACROMOLECULE})


#: Which molecular representation a calculator should be handed. Closed,
#: for the same reason `STRUCTURE_KINDS` is: a typo would silently route a
#: calculator to the wrong structure and still look fine.
#:
#: **GEOMETRY AND HYDROGEN REPRESENTATION ARE ONE AXIS HERE AND THAT IS
#: DELIBERATE**, because a conformer molblock carries explicit hydrogens
#: -- ethylmorphine is 23 atoms as drawn and 46 as a conformer. Measured
#: over all 49 registered calculators, run once on the drawing and once on
#: a real conformer with timestamps normalised, plus a third run with the
#: hydrogens folded back to implicit to separate the two causes:
#:
#:     unchanged                            30
#:     changed ONLY by explicit hydrogens    8   <- the regression risk
#:     changed by the geometry              11   <- the point of the fix
#:
#: The eight are topological -- a Wiener index over 46 atoms is a
#: different number from one over 23, and neither is wrong for its input.
#: So "hand everyone the conformer" is unsafe and stripping the hydrogens
#: is too, since geometry, SASA and dipole need hydrogen positions.
DRAWING = "drawing"
GEOMETRY = "geometry"
CALCULATION_INPUTS = frozenset({DRAWING, GEOMETRY})

#: A conformer SET, in stored order -- what a Boltzmann-averaged ORCA run is
#: handed. Deliberately NOT in `CALCULATION_INPUTS`: a registry calculator
#: is handed one molecule, so no definition may declare this. It exists so a
#: result computed over several conformers can name exactly which several,
#: rather than borrowing the single canonical conformer's identity as a
#: stand-in for all of them.
ENSEMBLE = "ensemble"


class ComponentSelection(str, Enum):
    """WHICH components of a drawing a calculator is handed.

    Round 5's multicomponent sweep (tests/fixtures/multicomponent_matrix_s1.json)
    found the question had never been asked: every calculator got the whole
    drawing, so metformin pamoate "failed Lipinski" on its C23 counter-ion and
    sodium acetate had a logP of -4.24 against acetic acid's 0.09. It is a
    different axis from `calculation_input` (drawing vs conformer), which is
    why it is its own field rather than a third member there.
    """

    #: The drawing as given: what the substance IS (formula, mass, name) or
    #: a description of the given structure or geometry.
    WHOLE_STRUCTURE = "whole_structure"
    #: The drawing as given, by a method that is atom- or component-local, so
    #: each component is answered on its own (perception, per-atom values).
    EACH_COMPONENT = "each_component"
    #: The ChEMBL parent compound (Bento et al. 2020): listed salts and
    #: solvents removed, the rest neutralised, identical components merged,
    #: and applied only when there is more than one component -- the paper
    #: applies GetParent "to just those compounds" that are multicomponent or
    #: isotopic. ChEMBL computes every calculated property on it but the full
    #: weight and formula (ChEMBL 37 schema documentation, COMPOUND_PROPERTIES,
    #: [source:chembl_schema]).
    CHEMBL_PARENT = "chembl_parent"
    #: More than one component is refused: the method is stated for a pure
    #: single substance and a salt is a different substance.
    REFUSE_MULTICOMPONENT = "refuse_multicomponent"


class Aggregation(str, Enum):
    """HOW the answer relates to the components it was computed over."""

    SCALAR = "scalar"
    PER_ATOM = "per_atom"
    #: A set of structures, facts or points (isomers, a report, a curve).
    COLLECTION = "collection"


class MethodDomain(str, Enum):
    """WHAT inputs the published method is defined for.

    Declared, and enforced by the framework only where it can be decided
    from the structure alone (`ORGANIC`); a `METHOD_SPECIFIC` calculator
    refuses what its own source excludes, with its own code.
    """

    ANY_STRUCTURE = "any_structure"
    ORGANIC = "organic"
    METHOD_SPECIFIC = "method_specific"


@dataclass(frozen=True)
class CalculatorScope:
    """Which components, how aggregated, and over what domain. Every
    registered calculator declares one; `tests/test_multicomponent_scope.py`
    refuses a definition without. An explicit `WHOLE_STRUCTURE` is a real
    declaration, not a missing one."""

    selection: ComponentSelection
    aggregation: Aggregation
    domain: MethodDomain = MethodDomain.ANY_STRUCTURE
    #: Why this scope, in a sentence -- and, for `REFUSE_MULTICOMPONENT`, the
    #: explanation the refusal shows.
    note: str = ""


class CalculationRefusal(Exception):
    """A calculator declining a structure, with a stable code.

    Raised rather than returned so that every route into a calculator --
    Properties, Batch, the 3D overlay -- gets the same refusal from the same
    place; `DescriptorService` turns it into a FAILED result carrying the
    code, both sentences and its KIND (`domain.refusal_kinds`).

    **THE KIND IS RESOLVED, NEVER DEFAULTED TO "LIMIT".** In order: the kind
    the producer declared, then the kind `REFUSAL_KINDS` gives the code, then
    the legacy `inapplicable` flag if one was passed explicitly (True is a
    limit). A refusal with none of the three has NO kind, which is a fault:
    `CalculationRefusal("SOME_NEW_CODE", ...)` used to be silently a permanent
    limit because `inapplicable` defaulted to True, so a code nobody had
    classified read as "the method does not apply" and nobody looked at it.

    `inapplicable` stays, derived (`kind is LIMIT`), because every consumer of
    a refusal already reads it and NEEDS_INPUT / NEEDS_SETUP are, by
    definition, not limits of the method.
    """

    def __init__(
        self,
        code: str,
        summary: str,
        detail: str,
        *,
        inapplicable: bool | None = None,
        kind: RefusalKind | None = None,
        missing_inputs: tuple[MissingInput, ...] = (),
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.summary = summary
        self.detail = detail
        resolved = kind if kind is not None else refusal_kind_of(code)
        if resolved is None and inapplicable:
            resolved = RefusalKind.LIMIT
        self.kind = resolved
        self.inapplicable = resolved is RefusalKind.LIMIT
        self.missing_inputs = tuple(missing_inputs)


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
    #: Which molecular representation this calculator is handed.
    #:
    #: **The default is today's behaviour**, for the same reason
    #: `applies_to` defaults to molecule-only: a calculator registered
    #: without a thought keeps getting the drawn structure, and asking
    #: for real 3D coordinates is an opt-in somebody had to mean. That
    #: matters more than usual here, because the alternative is not
    #: "slightly worse input" -- eight registered calculators return a
    #: DIFFERENT NUMBER when handed a conformer, purely because it
    #: carries explicit hydrogens. See `CALCULATION_INPUTS`.
    #:
    #: `GEOMETRY` means "prefer real 3D coordinates when they exist", and
    #: deliberately does NOT mean "refuse without them". The refusal
    #: already exists where it belongs, inside the calculators that need
    #: it -- `geometry_analysis._require_conformer` and
    #: `descriptor_providers._compute_shape_descriptors` both check
    #: `Is3D()` and say what the user should do about it. Duplicating
    #: that into the routing policy would give two places to drift apart.
    #:
    #: Two members and no speculative third: a representation with the
    #: original graph semantics AND coordinates is what the eight
    #: topological calculators would need if they ever wanted geometry,
    #: and nothing asks for it today. The vocabulary is extensible; it is
    #: not extended in advance.
    calculation_input: str = DRAWING
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
    #: Which components, how aggregated, over what domain. `None` is not a
    #: scope: the guard fails on it (see `CalculatorScope`).
    scope: CalculatorScope | None = None
    #: Declared stage and default visibility, with the reason
    #: (`domain.calculator_support`). `None` is "nobody decided" and reads as
    #: STABLE and shown, so a plugin's calculator or a test double behaves as it
    #: always did; a guard fails a BUILT-IN calculator that is neither classified
    #: nor named in `LEGACY_UNCLASSIFIED`.
    support: CalculatorSupport | None = None

    def __post_init__(self) -> None:
        # At construction, so a dangling or circular dependency is a failing
        # import rather than a control that is greyed out forever.
        by_name = {p.name: p for p in self.parameters}
        for parameter in self.parameters:
            seen = {parameter.name}
            controller_name = parameter.enabled_by
            while controller_name is not None:
                controller = by_name.get(controller_name)
                if controller is None:
                    raise ValueError(f"{self.calculator_id}.{parameter.name}: enabled_by names no parameter {controller_name!r}")
                if controller.kind != "bool":
                    raise ValueError(f"{self.calculator_id}.{parameter.name}: enabled_by {controller_name!r} is not a bool")
                if controller_name in seen:
                    raise ValueError(f"{self.calculator_id}.{parameter.name}: enabled_by forms a cycle through {controller_name!r}")
                seen.add(controller_name)
                controller_name = controller.enabled_by


def active_parameters(definition: CalculatorDefinition, values: dict[str, Any] | None) -> dict[str, Any]:
    """`values` without every declared parameter whose controller is off.

    A controller's value is read from `values`, or its default when absent,
    and must itself be active. Keys no parameter declares pass through
    untouched: callers may hand a calculator internal settings.
    """
    values = dict(values or {})
    by_name = {p.name: p for p in definition.parameters}

    def active(name: str) -> bool:
        controller_name = by_name[name].enabled_by
        if controller_name is None:
            return True
        return active(controller_name) and bool(values.get(controller_name, by_name[controller_name].default))

    return {key: value for key, value in values.items() if key not in by_name or active(key)}


@dataclass(frozen=True, kw_only=True)
class CalculationRequest:
    """A request to run one registered calculator against one molecule —
    the generic shape `DescriptorService.request_calculation` takes,
    replacing a one-off method per calculator kind."""

    calculator_id: str
    molecule_uuid: str
    parameters: dict[str, Any] = field(default_factory=dict)
