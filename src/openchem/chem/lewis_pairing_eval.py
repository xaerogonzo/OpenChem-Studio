"""Evaluate the Lewis pairing over stored quantum-chemistry runs (`docs/RECIPES_DESIGN.md` sections 4 and 8, Stage A).

Pure given what it is handed (`PairMember`: the drawing, and what the host knows about the molecule's runs). It
starts no job and reads no project. For anything missing it returns the gap, as a sentence, on the run it returns;
the preview of the work that would fill it is the host's, and nothing here runs ORCA.

**THE RUN IT RETURNS IS HONEST ABOUT WHAT IT IS.** Each of the four jobs the plan would run is `COMPLETED` when
a stored run supplied its numbers and `BLOCKED` (with the gap) when none did; the evaluating step is `COMPLETED`
when the report was built and `REFUSED` when the structures cannot form an adduct at all. The status is decided by
`recipe_run.classify` and nowhere else, so a pairing with a missing hardness is `PARTIAL`, never `COMPLETED`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Any

from openchem.chem.lewis_adduct import lewis_report
from openchem.domain.common import CacheState, Provenance
from openchem.domain.lewis import ROLE_ACID, ROLE_AUTO, ROLE_BASE, PairEvidence
from openchem.domain.lewis_binder import MoleculeFacts, bind_molecule
from openchem.domain.lewis_pairing import (
    DSCF_FIRST,
    DSCF_SECOND,
    PAIR,
    RECIPE_ID,
    SP_FIRST,
    SP_SECOND,
    VERSION,
)
from openchem.domain.quantum_methods import METHOD_BASIS_PRESETS, SOLVENTS
from openchem.domain.recipe_run import (
    BindingRecord,
    BindingState,
    RecipeRun,
    SlotInput,
    StepRecord,
    StepState,
    classify,
    new_run_id,
)
from openchem.domain.refusal_kinds import RefusalKind

#: The name the result is filed under. Not `lewis_adduct`: that is the registered calculator's id, and a pairing
#: built from stored runs is a different answer that must not be mistaken for it in Results.
RESULT_NAME = "Lewis pairing (stored quantum-chemistry runs)"

#: The roles the recipe's `role` parameter accepts: the calculator's own codes.
_ROLES = (ROLE_AUTO, ROLE_ACID, ROLE_BASE)


@dataclass(frozen=True)
class PairMember:
    """One molecule of the pair: its drawing, and what the host knows about it."""

    facts: MoleculeFacts
    #: The drawing as an RDKit molecule, which the structural analysis and the role resolution read.
    mol: Any
    #: `chem.recipe_host.constitution_key` of the drawing now, or None if it could not be computed.
    constitution_key: str | None


def _slot_input(slot: str, member: PairMember) -> SlotInput:
    return SlotInput(
        slot=slot,
        molecule_uuid=member.facts.molecule_uuid,
        constitution_key=member.constitution_key or "",
        drawing_fingerprint=member.facts.fingerprints.get("drawing", ""),
    )


def _service_step(step_id: str, slot: str, kinds: tuple[str, ...], by_target: dict[str, BindingRecord]) -> StepRecord:
    """A job of the plan, satisfied by a stored run or blocked with the reason."""
    records = [by_target[f"{slot}_{kind}"] for kind in kinds]
    if all(r.state is BindingState.BOUND for r in records):
        runs = sorted({r.evidence.run_id for r in records})
        return StepRecord(step_id, StepState.COMPLETED, f"from stored run {', '.join(runs)}")
    gaps = [r.reason for r in records if r.state is not BindingState.BOUND]
    return StepRecord(step_id, StepState.BLOCKED, " ".join(dict.fromkeys(gaps)))


def evaluate_lewis_pairing(
    first: PairMember,
    second: PairMember,
    *,
    method_basis: str,
    solvent: str = "",
    role: str = ROLE_AUTO,
) -> RecipeRun:
    """The pairing of `first` and `second` at one level of theory, from their stored runs.

    `role` is the role of `first`, in the calculator's own codes. Which molecule is the acid is decided by the
    structures (`resolve_roles`), never by the order they are given in: the same two molecules in either slot give
    the same lines.

    A parameter that is not one of the recipe's choices is a programming error in the caller, not a chemistry
    outcome, and raises `ValueError`; the UI offers only the choices and the assistant's tool validates first.
    """
    if method_basis not in METHOD_BASIS_PRESETS:
        raise ValueError(f"method_basis {method_basis!r} is not one of the presets: {', '.join(METHOD_BASIS_PRESETS)}")
    if solvent not in SOLVENTS:
        raise ValueError(f"solvent {solvent!r} is not one of: {', '.join(repr(s) for s in SOLVENTS)}")
    if role not in _ROLES:
        raise ValueError(f"role {role!r} is not one of: {', '.join(_ROLES)}")

    first_evidence, first_records = bind_molecule("first", first.facts, method_basis=method_basis, solvent=solvent)
    second_evidence, second_records = bind_molecule("second", second.facts, method_basis=method_basis, solvent=solvent)
    bindings = first_records + second_records
    by_target = {r.target: r for r in bindings}

    run_id = new_run_id()
    report = lewis_report(
        first.mol,
        first.facts.molecule_uuid,
        second.mol,
        role,
        evidence=PairEvidence(first_evidence, second_evidence),
    )
    refused = report.cache_state is CacheState.FAILED
    # Evaluated, and no line came of it: no tabulated enthalpy for the pair and no evidence for either orbital line.
    # That is a gap list, not an answer, so it is shown as one rather than as a report of three "not available".
    nothing = (not refused) and report.provenance is not None and report.provenance.parameters.get("lines_available") == 0

    steps = (
        _service_step(SP_FIRST, "first", ("homo", "lumo"), by_target),
        _service_step(DSCF_FIRST, "first", ("hardness",), by_target),
        _service_step(SP_SECOND, "second", ("homo", "lumo"), by_target),
        _service_step(DSCF_SECOND, "second", ("hardness",), by_target),
        _pair_step(report, refused, nothing),
    )

    result = None if refused or nothing else _as_pairing(report, run_id, method_basis, solvent)
    return RecipeRun(
        run_id=run_id,
        recipe_id=RECIPE_ID,
        recipe_version=VERSION,
        status=classify(steps, bindings),
        inputs=(_slot_input("first", first), _slot_input("second", second)),
        parameters=(("method_basis", method_basis), ("solvent", solvent), ("role", role)),
        steps=steps,
        bindings=bindings,
        result=result,
        created_at=time.time(),
    )


def _pair_step(report: Any, refused: bool, nothing: bool) -> StepRecord:
    if refused:
        # A structural limit: nothing in the acid can accept, or nothing in the base can donate. The calculator
        # already says which, and in words.
        return StepRecord(PAIR, StepState.REFUSED, report.error or "", RefusalKind.LIMIT.value)
    if nothing:
        return StepRecord(
            PAIR,
            StepState.BLOCKED,
            "No line of evidence could be evaluated: the pair has no tabulated enthalpy, and the stored runs do not "
            "supply the orbital energies or the hardnesses a line needs. The gaps above say what to run.",
        )
    return StepRecord(PAIR, StepState.COMPLETED)


def _as_pairing(report: Any, run_id: str, method_basis: str, solvent: str) -> Any:
    """The calculator's report, filed as this recipe's answer and stamped with where it came from."""
    inherited = dict(report.provenance.parameters) if report.provenance is not None else {}
    # `ReportResult.matched` omits a fact's label when it IS the report's name (that is how an unlabelled line, such
    # as the role sentence, reads as a plain line). Renaming the report without renaming those facts would print
    # "Lewis Adduct: Role: ..." on every one of them.
    facts = tuple(replace(f, label=RESULT_NAME) if f.label == report.name else f for f in report.facts)
    return replace(
        report,
        report_id=RECIPE_ID,
        name=RESULT_NAME,
        facts=facts,
        provenance=Provenance(
            created_by="core",
            method=f"recipe:{RECIPE_ID}:{VERSION}",
            parameters={**inherited, "recipe_run_id": run_id, "method_basis": method_basis, "solvent": solvent},
        ),
    )
