"""What the assistant may know about the selected molecule during ONE turn, frozen when it began.

**A TURN IS ONE USER MESSAGE AND THE ASSISTANT'S REPLY, AND EVERYTHING IT READS IS A VALUE TAKEN WHEN
THE MESSAGE WAS SENT.** The reply streams for seconds, and in those seconds the person can select
another molecule, redraw this one, or have a calculation finish. If a tool re-read the live project
at the moment the model asked, the evidence behind one answer would change between its first
sentence and its last, and a question about aspirin could be answered with the numbers of whatever
was selected by then. So `begin_turn` (on the GUI thread, at Send) captures a `TurnContext`, tools
read only that, and the model is never given a way to name another molecule.

Results are frozen dataclasses, so holding references to the stored ones IS a value snapshot; no
copy is needed (`domain/scientific_result.py`).

**FRESHNESS AND OUTCOME ARE TWO AXES, AND THE DESIGN RECORD'S "FIVE STATES" ARE THEIR PRODUCT.**
A stored result is `CURRENT`, `HISTORICAL` or `UNVERIFIABLE` according to its input fingerprint, and
separately `COMPUTED`, `REFUSED` or `FAILED` according to what it says. A refusal that no longer
matches the structure is a historical refusal, and is not shown beside the current ones as if it
still applied. `NOT_RUN` is the absence of any record, reported per calculator and never invented as
a stale one.

* `CURRENT`: its fingerprint equals the snapshot's for that input, **and** it is the record the
  application itself would replay (`SessionResultStore.fresh_results`), so a legacy method version
  stored beside a current one is not offered as current.
* `HISTORICAL`: retained, computed on an earlier structure (or a superseded method version).
* `UNVERIFIABLE`: no fingerprint on the record, or none for this molecule's input in the snapshot.
  Never called fresh.

Pure: no Qt, no RDKit.
"""

from __future__ import annotations

import uuid as _uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from openchem.domain import result_status as rs
from openchem.domain.result_store import StoredResult


class Freshness(str, Enum):
    CURRENT = "current"
    HISTORICAL = "historical"
    UNVERIFIABLE = "unverifiable"


class Outcome(str, Enum):
    #: It computed something (which may be nothing: a result with no values is still a result).
    COMPUTED = "computed"
    #: The method declined: a limit, a missing input, a missing setup. Keeps its kind.
    REFUSED = "refused"
    #: It broke.
    FAILED = "failed"


@dataclass(frozen=True)
class ResultEntry:
    """One stored result, classified against the structure the turn began with."""

    stored: StoredResult
    freshness: Freshness
    #: `domain.result_status` value of the result itself.
    status: str
    outcome: Outcome
    #: Why it is not current, when it is not: an earlier structure, a superseded method.
    note: str = ""

    @property
    def result_id(self) -> str:
        return self.stored.identity.result_id

    @property
    def producer(self) -> str:
        return self.stored.identity.producer


def _outcome_of(status: str) -> Outcome:
    if status == rs.READY or status == rs.STALE:
        return Outcome.COMPUTED
    if status == rs.FAILED:
        return Outcome.FAILED
    return Outcome.REFUSED


_FRESHNESS_ORDER = {Freshness.CURRENT: 0, Freshness.HISTORICAL: 1, Freshness.UNVERIFIABLE: 2}


def classify_results(
    records: Iterable[StoredResult],
    fresh: Iterable[StoredResult],
    fingerprints: Mapping[str, str],
) -> tuple[ResultEntry, ...]:
    """Put every retained record in a freshness and an outcome. See the module docstring.

    `fresh` is what `SessionResultStore.fresh_results` returned for the same fingerprints: the
    records the application would replay. Identity comparison, because the store hands back its
    own objects.
    """
    fresh_ids = {id(stored) for stored in fresh}
    entries: list[ResultEntry] = []
    for stored in records:
        identity = stored.identity
        current_fingerprint = fingerprints.get(identity.calculation_input)
        note = ""
        if not identity.input_fingerprint or current_fingerprint is None:
            freshness = Freshness.UNVERIFIABLE
            note = (
                "the record carries no input fingerprint"
                if not identity.input_fingerprint
                else f"the molecule has no {identity.calculation_input} fingerprint to compare with"
            )
        elif identity.input_fingerprint != current_fingerprint:
            freshness = Freshness.HISTORICAL
            note = "computed on an earlier structure of this molecule"
        elif id(stored) in fresh_ids:
            freshness = Freshness.CURRENT
        else:
            freshness = Freshness.HISTORICAL
            note = "a method version the application has superseded for this result"
        status = rs.status_of(stored.result)
        entries.append(ResultEntry(stored=stored, freshness=freshness, status=status, outcome=_outcome_of(status), note=note))
    entries.sort(key=lambda e: (_FRESHNESS_ORDER[e.freshness], e.stored.identity.calculation_input, e.result_id))
    return tuple(entries)


@dataclass(frozen=True)
class TurnContext:
    """The selected molecule and everything stored about it, as it was when the turn began."""

    turn_id: str
    project_uuid: str
    molecule_uuid: str
    display_name: str
    canonical_smiles: str
    #: Heavy atoms of the drawing: the size an execution decision is made against.
    heavy_atoms: int
    #: False for a molecule nothing has been drawn for yet.
    has_structure: bool
    conformer_count: int
    #: The molecule's CURRENT fingerprint for each calculation input at the moment of capture.
    fingerprints: Mapping[str, str]
    entries: tuple[ResultEntry, ...] = ()

    def entries_for(self, key: str) -> tuple[ResultEntry, ...]:
        """Records made by calculator `key`, or carrying result id `key` (the always-on set)."""
        return tuple(e for e in self.entries if e.producer == key or e.result_id == key)


def build_turn_context(
    *,
    project_uuid: str,
    molecule_uuid: str,
    display_name: str,
    canonical_smiles: str,
    heavy_atoms: int,
    has_structure: bool,
    conformer_count: int,
    fingerprints: Mapping[str, str],
    records: Iterable[StoredResult],
    fresh: Iterable[StoredResult],
) -> TurnContext:
    frozen = dict(fingerprints)
    return TurnContext(
        turn_id=_uuid.uuid4().hex,
        project_uuid=project_uuid,
        molecule_uuid=molecule_uuid,
        display_name=display_name,
        canonical_smiles=canonical_smiles,
        heavy_atoms=heavy_atoms,
        has_structure=has_structure,
        conformer_count=conformer_count,
        fingerprints=MappingProxyType(frozen),
        entries=classify_results(records, fresh, frozen),
    )


#: The most entries one read returns; a molecule with the whole always-on set stored has a few dozen.
DEFAULT_READ_LIMIT = 40


@dataclass(frozen=True)
class ResultsView:
    """What `read_results` hands back: the entries asked for, and what is missing or not current."""

    turn_id: str
    molecule_uuid: str
    entries: tuple[ResultEntry, ...]
    #: Requested calculators with no stored record of any kind.
    not_run: tuple[str, ...] = ()
    #: Requested calculators that have records, none of them current.
    only_not_current: tuple[str, ...] = ()
    #: How many matching entries were left out to respect the limit.
    truncated: int = 0


def read_results(
    turn: TurnContext,
    calculator_ids: Iterable[str] | None = None,
    *,
    include_not_current: bool = False,
    limit: int = DEFAULT_READ_LIMIT,
) -> ResultsView:
    """The turn's results, optionally for named calculators.

    By default only `CURRENT` entries are returned: a historical or unverifiable one is read only
    when asked for, and then carries its freshness so it cannot be taken for current. A requested
    calculator with nothing stored is `not_run`; one with only not-current records is reported as
    such, and neither is turned into a value.
    """
    wanted = list(dict.fromkeys(calculator_ids)) if calculator_ids is not None else None
    pool = turn.entries if wanted is None else tuple(e for key in wanted for e in turn.entries_for(key))
    # A result matched by both its producer and its id appears once. By identity, because an entry
    # holds a mutable `StoredResult` and is not hashable.
    seen: set[int] = set()
    pool = tuple(e for e in pool if not (id(e) in seen or seen.add(id(e))))
    shown = tuple(e for e in pool if include_not_current or e.freshness is Freshness.CURRENT)
    not_run: list[str] = []
    only_not_current: list[str] = []
    for key in wanted or ():
        matched = turn.entries_for(key)
        if not matched:
            not_run.append(key)
        elif not any(e.freshness is Freshness.CURRENT for e in matched):
            only_not_current.append(key)
    limit = max(0, limit)
    return ResultsView(
        turn_id=turn.turn_id,
        molecule_uuid=turn.molecule_uuid,
        entries=shown[:limit],
        not_run=tuple(not_run),
        only_not_current=tuple(only_not_current),
        truncated=max(0, len(shown) - limit),
    )
