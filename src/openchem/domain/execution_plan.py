"""What a run will do, decided once, before anything starts.

**THERE WERE TWO INTERPRETATIONS OF "RUN THESE CALCULATORS".** Properties ran
the ticked ones on one molecule and skipped, by name, any that needed an input
it could not default; the batch panel ran every id it was handed on every
molecule and let a calculator that needed input fail into a cell. Neither was
wrong, but a third consumer (a wizard, a "run recommended" button) would have
had to choose between them, and the cost estimate -- molecules times ticks --
counted work neither route would do.

An `ExecutionPlan` is that decision as a value: which molecules, which
calculators survive, which were left out and why, what parameters each will
run with, and how many jobs that is. Both routes read it; the single-molecule
route simply has a plan with one molecule. It is immutable, so a run is what
it was when it was submitted: a selection that changes while the run is in
flight affects the NEXT plan, never this one.

It is pure. Nothing here imports Qt or touches a registry: the caller passes
the one lookup it needs (`definition_of`), which is how this stays testable
without a window.

What it deliberately does NOT do: generate prerequisites (a conformer), probe
a structure for applicability (`CalculatorDefinition.preflight` needs a mol),
or choose parameter values for the person. A calculator that needs a
conformer still refuses on its own, with its own reason, in its own cell.
"""

from __future__ import annotations

import uuid as _uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from openchem.domain.calculator import CalculatorDefinition, RegistryExecution

#: Why a calculator is not in a plan. Closed strings, so a caller (and a test)
#: can tell "retired" from "runs from its own panel" without parsing prose.
UNKNOWN = "unknown"
#: The calculator runs from its own panel (docking, quantum chemistry).
SERVICE_ONLY = "service_only"
#: A required parameter with nothing chosen: no usable default exists.
NEEDS_INPUT = "needs_input"
#: The molecule has no drawn structure yet; it keeps a failed row.
NO_STRUCTURE = "no_structure"


@dataclass(frozen=True)
class ExcludedJob:
    """One calculator (or one molecule) left out of a plan, and why."""

    kind: str
    reason: str
    calculator_id: str = ""
    display_name: str = ""
    molecule_uuid: str = ""


@dataclass(frozen=True)
class ExecutionPlan:
    """An immutable description of one run. See the module docstring."""

    run_id: str
    #: EVERY molecule the scope named, in the order given -- including the ones
    #: that cannot run. This is what the service is handed, so each still gets a
    #: row.
    scope_uuids: tuple[str, ...]
    #: Molecules that will be computed, in the order given, with their labels.
    molecule_uuids: tuple[str, ...]
    molecule_labels: Mapping[str, str]
    #: Molecules named in the request that cannot run (no structure yet). They
    #: still get a row -- failed, with the reason -- so the table is never
    #: silently shorter than the scope.
    unrunnable_molecules: tuple[ExcludedJob, ...]
    #: The structure version of EACH molecule when the run was submitted. The
    #: checker's counter is per molecule, so one number for a whole run cannot
    #: say whether any one of them has moved since.
    structure_versions: Mapping[str, int]
    calculator_ids: tuple[str, ...]
    descriptor_ids: tuple[str, ...]
    #: Parameters for each RUNNABLE calculator, normalised: what the person
    #: chose, else the registered defaults. A calculator absent from the
    #: overrides runs on its defaults, exactly as `batch_service` builds them.
    parameters: Mapping[str, Mapping[str, Any]]
    excluded: tuple[ExcludedJob, ...] = field(default_factory=tuple)

    @property
    def molecule_count(self) -> int:
        return len(self.molecule_uuids)

    @property
    def job_count(self) -> int:
        """Calculations that will actually be started.

        Molecules times what survived -- not molecules times what was ticked.
        A molecule with no structure contributes none; a calculator that was
        excluded contributes none.
        """
        return self.molecule_count * (len(self.calculator_ids) + len(self.descriptor_ids))

    @property
    def is_empty(self) -> bool:
        return not self.calculator_ids and not self.descriptor_ids

    def parameters_for(self, calculator_id: str) -> dict[str, Any]:
        return dict(self.parameters.get(calculator_id, {}))

    def overrides(self, chosen: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
        """Only the settings somebody actually chose, for the service.

        `BatchRequest.parameters` documents that an absent calculator runs on
        its registered defaults; sending the normalised dict instead would
        make this module a second implementation of "what are the defaults".
        """
        return {cid: dict(chosen[cid]) for cid in self.calculator_ids if cid in chosen}

    def describe_exclusions(self) -> str:
        """One sentence naming what was left out, for a status line."""
        parts = [f"{job.display_name or job.calculator_id} ({job.reason})" for job in self.excluded]
        parts += [f"{job.display_name} ({job.reason})" for job in self.unrunnable_molecules]
        return "Left out: " + "; ".join(parts) + "." if parts else ""


def build_execution_plan(
    *,
    molecules: Iterable[Any],
    calculator_ids: Iterable[str],
    descriptor_ids: Iterable[str] = (),
    chosen_parameters: Mapping[str, Mapping[str, Any]] | None = None,
    definition_of: Callable[[str], CalculatorDefinition | None],
    structure_version_of: Callable[[str], int] = lambda _uuid: 0,
    run_id: str | None = None,
    plain_label: Callable[[str], str] = lambda text: text,
) -> ExecutionPlan:
    """Decide a run.

    `molecules` are objects with `uuid`, `display_name` and `molblock` (a
    `MoleculeModel`). `chosen_parameters` is what settings dialogs produced;
    anything absent runs on the registered defaults.
    """
    chosen = chosen_parameters or {}
    runnable: list[str] = []
    excluded: list[ExcludedJob] = []
    parameters: dict[str, Mapping[str, Any]] = {}
    seen: set[str] = set()
    for calculator_id in calculator_ids:
        if calculator_id in seen:
            continue
        seen.add(calculator_id)
        definition = definition_of(calculator_id)
        if definition is None:
            excluded.append(
                ExcludedJob(UNKNOWN, "not offered any more", calculator_id=calculator_id)
            )
            continue
        if not isinstance(definition.execution, RegistryExecution):
            excluded.append(
                ExcludedJob(
                    SERVICE_ONLY,
                    "runs from its own panel",
                    calculator_id=calculator_id,
                    display_name=definition.display_name,
                )
            )
            continue
        # A REQUIRED parameter with nothing chosen has no usable default, so
        # running it could only produce a refusal the person did not earn by
        # asking. It is left out and named, with what it wants.
        wanted = [
            plain_label(p.label)
            for p in definition.parameters
            if p.required and calculator_id not in chosen
        ]
        if wanted:
            excluded.append(
                ExcludedJob(
                    NEEDS_INPUT,
                    f"needs {', '.join(wanted)}",
                    calculator_id=calculator_id,
                    display_name=definition.display_name,
                )
            )
            continue
        runnable.append(calculator_id)
        parameters[calculator_id] = MappingProxyType(
            dict(chosen[calculator_id])
            if calculator_id in chosen
            else {p.name: p.default for p in definition.parameters}
        )

    runnable_molecules: list[str] = []
    scope: list[str] = []
    labels: dict[str, str] = {}
    unrunnable: list[ExcludedJob] = []
    for molecule in molecules:
        labels[molecule.uuid] = molecule.display_name
        scope.append(molecule.uuid)
        if not getattr(molecule, "molblock", ""):
            unrunnable.append(
                ExcludedJob(
                    NO_STRUCTURE,
                    "no structure yet",
                    display_name=molecule.display_name,
                    molecule_uuid=molecule.uuid,
                )
            )
            continue
        runnable_molecules.append(molecule.uuid)

    return ExecutionPlan(
        run_id=run_id or _uuid.uuid4().hex,
        scope_uuids=tuple(scope),
        molecule_uuids=tuple(runnable_molecules),
        molecule_labels=MappingProxyType(labels),
        unrunnable_molecules=tuple(unrunnable),
        structure_versions=MappingProxyType({u: structure_version_of(u) for u in scope}),
        calculator_ids=tuple(runnable),
        descriptor_ids=tuple(dict.fromkeys(descriptor_ids)),
        parameters=MappingProxyType(parameters),
        excluded=tuple(excluded),
    )
