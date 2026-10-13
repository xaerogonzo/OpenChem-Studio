"""From a molecule's stored quantum-chemistry runs to the evidence the Lewis lines take, or to a gap that says why.

The binder half of `docs/RECIPES_DESIGN.md` sections 3 to 5. Pure: it is handed what the host knows about the
molecule (`MoleculeFacts`: its fingerprints today, whether each run's input is still this molecule) and returns
`MoleculeEvidence` with one `BindingRecord` per number. It does no chemistry and reads no project.

**EVERY OUTCOME IS A STATE WITH A SENTENCE, AND THE SENTENCES DIFFER ON PURPOSE.** "X has no delta-SCF run",
"X has delta-SCF runs only at another method", "X's run failed", "two earlier geometries are waiting to be chosen
between" and "the structure was edited since that run" are five next steps, and a binder that said "not
available" for all of them would send a person to run something they had run. A present-but-wrong record is never
reported as an absent one.

**ONLY A CURRENT RUN IS USED.** A run is current when its input is this molecule (constitution, charge, isotopes
and any stereochemistry the drawing specifies) AND its fingerprint is the one a run would be given today for the
same input kind. A run of the same molecule at an earlier geometry is historical: never used by default, because a
number from a geometry the molecule no longer has is not the molecule's number. It can be CHOSEN, by run id, and
the choice is recorded. Several current runs are repeats of one job: the newest is used, the others are named, and
the largest spread among their values is written down as a number, so a surprising one is visible without a
threshold having been invented.

**THE METHOD, BASIS AND SOLVENT ARE ARGUMENTS, NOT FOUND.** The binder never looks for the method that happens to
have evidence. A molecule with runs only at another level is reported as such, and the sentence names the levels
it does have.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from openchem.domain.lewis import (
    EVIDENCE_CALC_TYPES,
    EVIDENCE_DESCRIPTORS,
    EVIDENCE_UNIT,
    EvidenceValue,
    MoleculeEvidence,
)
from openchem.domain.lewis_pairing import PAIR
from openchem.domain.quantum_chemistry_run import QuantumChemistryRun, RunStatus
from openchem.domain.recipe_run import BindingRecord, BindingState, Evidence

#: Display names for the two calculation types the evidence is read from.
_CALC_LABELS = {"sp": "single-point", "delta_scf": "delta-SCF"}
#: What each number is called in a sentence.
_ITEM_NAMES = {"homo": "HOMO energy", "lumo": "LUMO energy", "hardness": "delta-SCF hardness"}

#: The run states whose numbers exist.
_FINISHED = frozenset({RunStatus.COMPLETED, RunStatus.COMPLETED_WITH_WARNINGS})


@dataclass(frozen=True)
class MoleculeFacts:
    """What the host knows about one molecule and its runs. The binder trusts it and checks none of it."""

    molecule_uuid: str
    #: Display name, for sentences.
    label: str
    #: All runs of this molecule, any calculation type, any status.
    runs: tuple[QuantumChemistryRun, ...]
    #: The fingerprint a run would be given TODAY, by input kind (`DRAWING`, `GEOMETRY`). A kind the host could not
    #: work out is absent, and a run of that kind is then unverifiable rather than current.
    fingerprints: Mapping[str, str]
    #: run id -> whether that run's input is this molecule. True, False, or None when the host could not tell.
    describes: Mapping[str, bool | None]
    #: The drawing's net formal charge. A run at another charge is a different species, not this molecule's number.
    #: None means the host could not say, and the check is then skipped.
    formal_charge: int | None = None
    #: calculation type -> run id the person CHOSE, for the case where several are candidates.
    picks: Mapping[str, str] = field(default_factory=dict)


def where(method_basis: str, solvent: str) -> str:
    """How a level of theory is named in a sentence."""
    return f"{method_basis} in {solvent}" if solvent else f"{method_basis} (gas phase)"


def _when(run: QuantumChemistryRun) -> float:
    return run.completed_at if run.completed_at is not None else run.started_at


def _newest_first(runs: Sequence[QuantumChemistryRun]) -> list[QuantumChemistryRun]:
    return sorted(runs, key=_when, reverse=True)


def _ids(runs: Sequence[QuantumChemistryRun]) -> str:
    return ", ".join(r.run_id for r in runs)


def _value_of(run: QuantumChemistryRun, descriptor_id: str) -> tuple[float | None, str]:
    """The number `descriptor_id` has in `run`, or None and why not."""
    for descriptor in run.results.get("descriptors") or []:
        if getattr(descriptor, "descriptor_id", None) != descriptor_id:
            continue
        value = getattr(descriptor, "value", None)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return None, f"{descriptor_id} is {value!r}, not a number"
        if getattr(descriptor, "units", "") != EVIDENCE_UNIT:
            return None, f"{descriptor_id} is in {getattr(descriptor, 'units', '')!r}, not {EVIDENCE_UNIT}"
        return float(value), ""
    return None, f"the run has no {descriptor_id}"


def bind_molecule(
    slot: str, facts: MoleculeFacts, *, method_basis: str, solvent: str = ""
) -> tuple[MoleculeEvidence, tuple[BindingRecord, ...]]:
    """The evidence for one molecule at one level of theory, and a record of how each number was found.

    `slot` is "first" or "second"; the records are for the evaluating step's inputs `<slot>_homo`, `<slot>_lumo` and
    `<slot>_hardness`, in that order.
    """
    items: dict[str, EvidenceValue] = {}
    records: list[BindingRecord] = []
    for kind in ("homo", "lumo", "hardness"):
        value, record = _bind_item(slot, kind, facts, method_basis, solvent)
        items[kind] = value
        records.append(record)
    return MoleculeEvidence(facts.label, items["homo"], items["lumo"], items["hardness"]), tuple(records)


def _bind_item(
    slot: str, kind: str, facts: MoleculeFacts, method_basis: str, solvent: str
) -> tuple[EvidenceValue, BindingRecord]:
    calc = EVIDENCE_CALC_TYPES[kind]
    descriptor_id = EVIDENCE_DESCRIPTORS[kind]
    label = _CALC_LABELS[calc]
    who = facts.label or slot
    target = f"{slot}_{kind}"
    level = where(method_basis, solvent)

    def gap(state: BindingState, reason: str, candidates: Sequence[str] = ()) -> tuple[EvidenceValue, BindingRecord]:
        return (
            EvidenceValue(state=state, reason=reason),
            BindingRecord(PAIR, target, state, reason, None, tuple(candidates)),
        )

    of_type = [r for r in facts.runs if r.calc_type == calc]
    if not of_type:
        return gap(
            BindingState.MISSING,
            f"{who} has no {label} run. Run one in the Quantum Chemistry panel at {level}.",
        )

    here = [r for r in of_type if r.method_basis == method_basis and r.solvent == solvent]
    if not here:
        elsewhere = sorted({where(r.method_basis, r.solvent) for r in of_type})
        return gap(
            BindingState.INCOMPATIBLE,
            f"{who} has {label} runs only at {', '.join(elsewhere)}, not at {level}. Numbers from different levels "
            "of theory are different scales, so none was used. Run one at "
            f"{level}, or choose that level.",
        )

    finished = [r for r in here if r.status in _FINISHED]
    if not finished:
        failed = _newest_first([r for r in here if r.status is RunStatus.FAILED])
        if failed:
            why = failed[0].warnings[0] if failed[0].warnings else "no reason was recorded"
            return gap(
                BindingState.FAILED,
                f"{who}'s {label} run {_ids(failed)} at {level} failed: {why}.",
                [r.run_id for r in failed],
            )
        return gap(BindingState.MISSING, f"The only {label} run of {who} at {level} was cancelled. Run it again.")

    if facts.formal_charge is not None:
        right_charge = [r for r in finished if r.charge == facts.formal_charge]
        if not right_charge:
            charges = sorted({r.charge for r in finished})
            return gap(
                BindingState.INCOMPATIBLE,
                f"{who} has a formal charge of {facts.formal_charge:+d}, but its {label} run(s) at {level} were run at "
                f"charge {', '.join(f'{c:+d}' for c in charges)}. That is a different species, so none was used.",
                [r.run_id for r in finished],
            )
        finished = right_charge

    carrying: list[tuple[QuantumChemistryRun, float]] = []
    reasons: list[str] = []
    for run in finished:
        value, why = _value_of(run, descriptor_id)
        if value is None:
            reasons.append(f"run {run.run_id}: {why}")
        else:
            carrying.append((run, value))
    if not carrying:
        return gap(
            BindingState.FAILED,
            f"{who}'s {label} run(s) at {level} finished but give no usable {_ITEM_NAMES[kind]} "
            f"({'; '.join(reasons)}).",
            [r.run_id for r in finished],
        )

    values = {r.run_id: v for r, v in carrying}
    runs = [r for r, _ in carrying]
    current, historical, unverifiable, stale = [], [], [], []
    for run in runs:
        describes = facts.describes.get(run.run_id)
        if (
            describes is None
            or not run.input_fingerprint
            or not run.input_molblock
            or run.calculation_input not in facts.fingerprints
        ):
            unverifiable.append(run)
        elif describes is False:
            stale.append(run)
        elif facts.fingerprints.get(run.calculation_input) == run.input_fingerprint:
            current.append(run)
        else:
            historical.append(run)

    note = ""
    others: list[QuantumChemistryRun] = []
    pick = facts.picks.get(calc)
    if pick:
        chosen = next((r for r in runs if r.run_id == pick), None)
        if chosen is None:
            return gap(
                BindingState.MISSING,
                f"The {label} run chosen for {who} ({pick}) is not a finished {label} run of this molecule at {level}.",
            )
        if chosen in stale:
            return gap(
                BindingState.STALE,
                f"The {label} run chosen for {who} ({pick}) was of a different structure; the molecule was edited since.",
                [pick],
            )
        if chosen in unverifiable:
            return gap(
                BindingState.UNVERIFIABLE,
                f"The {label} run chosen for {who} ({pick}) kept no input to compare, so it cannot be shown to describe this molecule.",
                [pick],
            )
        note = "Chosen by run id" + ("; at an earlier geometry than a run would use now." if chosen in historical else ".")
    elif current:
        multiplicities = sorted({r.multiplicity for r in current})
        if len(multiplicities) > 1:
            return gap(
                BindingState.AMBIGUOUS,
                f"{who} has current {label} runs at multiplicities {', '.join(map(str, multiplicities))}. Choose one "
                f"by run id ({_ids(_newest_first(current))}).",
                [r.run_id for r in _newest_first(current)],
            )
        ordered = _newest_first(current)
        chosen, others = ordered[0], ordered[1:]
        if others:
            spread = max(values[r.run_id] for r in ordered) - min(values[r.run_id] for r in ordered)
            note = (
                f"Newest of {len(ordered)} repeats of this job; the others ({_ids(others)}) were not used. "
                f"Their values differ by up to {spread:.4f} {EVIDENCE_UNIT}."
            )
    elif historical:
        ordered = _newest_first(historical)
        return gap(
            BindingState.AMBIGUOUS,
            f"{who}'s {label} run(s) at {level} ({_ids(ordered)}) were made at an earlier geometry than a run would "
            "use now, so none is used by default. Choose one by run id, or run it again.",
            [r.run_id for r in ordered],
        )
    elif unverifiable:
        return gap(
            BindingState.UNVERIFIABLE,
            f"{who}'s {label} run(s) {_ids(unverifiable)} kept no input to compare, so they cannot be shown to "
            "describe this molecule and none is used.",
            [r.run_id for r in unverifiable],
        )
    else:
        return gap(
            BindingState.STALE,
            f"{who}'s {label} run(s) {_ids(stale)} were of a different structure; the molecule was edited since. "
            "Run it again.",
            [r.run_id for r in stale],
        )

    value = values[chosen.run_id]
    evidence = Evidence(
        molecule_uuid=facts.molecule_uuid,
        run_id=chosen.run_id,
        descriptor_id=descriptor_id,
        value=value,
        unit=EVIDENCE_UNIT,
        calc_type=chosen.calc_type,
        method_basis=chosen.method_basis,
        charge=chosen.charge,
        multiplicity=chosen.multiplicity,
        input_fingerprint=chosen.input_fingerprint,
        solvent=chosen.solvent,
    )
    return (
        EvidenceValue(value, BindingState.BOUND, evidence=evidence),
        BindingRecord(PAIR, target, BindingState.BOUND, note, evidence, tuple(r.run_id for r in others)),
    )
