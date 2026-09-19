"""Every result computed in a session, keyed by the input it describes.

**THE RULE THIS FILE EXISTS TO ENFORCE:** a stored result set may degrade
gracefully, but a replay must never mistake a partial or unsupported set for
a complete one. That is why "is the automatic set here?" is answered by a
MANIFEST (`BundlePart`) and not by "are there results for this molecule?".
If one of ten saved results cannot be decoded after an update, the store
holds nine, the manifest says ten were produced, the state is PARTIAL, and
the calculators run again. Without the manifest the nine would look like a
cache hit and the tenth would silently never come back.

**WHY NOT `BatchResultStore`.** Its key includes `structure_version`, the
structure checker's in-process counter, which restarts every session and so
cannot identify anything in a saved file. The key here is the input
FINGERPRINT (`chem.calculation_input.resolve_calculation_input`), which
names the exact structure a result was computed on and means the same thing
tomorrow.

**ONE PROJECT PER STORE.** Molecule uuids persist across saves, so a store
that outlived a project change could hand one project's results to another
that happened to carry the same uuid (a copy, an import). The store is built
FOR a project and refuses anything addressed to another.

Pure data: no Qt, no services, no RDKit. Identities are built in the service
layer (`services/result_identity.py`) and handed in.
"""

from __future__ import annotations

import enum
import logging
from collections import Counter
from dataclasses import dataclass, field, replace
from typing import Any

from openchem.domain.calculator import DRAWING, GEOMETRY
from openchem.domain.common import CacheState
from openchem.domain.descriptor import DescriptorValue
from openchem.domain import result_codec
from openchem.domain.report import ReportResult
from openchem.domain.scientific_result import (
    AlertResult,
    PerAtomDataset,
    PhCurveResult,
    SpectrumResult,
    StructureSetResult,
    TrajectoryResult,
)

logger = logging.getLogger("openchem.result_store")

#: Which always-on set a manifest describes. Bumped when what "the automatic
#: set" CONTAINS changes, so an old manifest cannot vouch for a new set.
#: v2 (2026-09-18): Fragment Counts changed method (vocabulary v2), so a
#: saved set's counts no longer describe what the set now computes.
AUTOMATIC_BUNDLE_ID = "automatic/v2"

#: The method Fragment Counts is computed by today. **Immutable once
#: persisted**: a change of meaning is a NEW string, never a repointed one,
#: because a saved result carries this and is interpreted by it.
FRAGMENT_COUNTS_METHOD = "structural-features-v2"

#: Result ids whose METHOD is part of their stored identity, and the method
#: a result computed today is by. Only these carry a `method_version`, so no
#: other result's identity (or saved project) changes.
CURRENT_METHOD_VERSIONS: dict[str, str] = {
    "fragment_counts": FRAGMENT_COUNTS_METHOD,
}

#: What a saved entry WITHOUT a `method_version` was computed by -- the rule
#: for recognising a result from before methods were recorded, and the label
#: it is shown under. A legacy result is kept, never silently replaced: it
#: occupies its own slot beside the current method's.
LEGACY_METHOD_VERSIONS: dict[str, tuple[str, str]] = {
    "fragment_counts": ("legacy-rdkit-fr-v1", "Fragment Counts (legacy: RDKit fr_* counters)"),
}

#: The persisted block's own layout version.
ENVELOPE_VERSION = 1

#: Revisions retained per molecule in a session, counted separately for each
#: calculation input (`SessionResultStore._touch`). Enough to undo back
#: through a handful of edits without recomputing; not a history. The
#: default of the "Revisions kept" setting, which can change it.
MAX_REVISIONS = 8

#: Result ids no current producer makes, each with why, dropped on load and
#: counted as `load_problems["retired"]`. A NAMED list, not "any producer the
#: registry does not know": an unknown id may be a plugin that is not loaded
#: today, and those are still restored.
RETIRED_RESULT_IDS: dict[str, str] = {
    # Not migrated onto the merged id: these results carry no computed
    # structure, and drawing them on the stored conformer puts every value
    # after a removed proton on the next atom (measured on OC(=O)C).
    "geometry_partial_charge_at_ph": (
        "merged into geometry_partial_charge (pH-dependent option) on 2026-09-17; "
        "rerun it, which takes under a second"
    ),
}

#: Saved result ids that MOVED, as (old id, payload type) -> new id, with the
#: payload's own id field rewritten to match.
#:
#: Keyed by the PAYLOAD TYPE, not the id alone, because the collision this
#: exists for is two producers sharing one id: `functional_groups` was both
#: the RDKit fragment counter's `AlertResult` and the naming-engine
#: annotation's `PerAtomDataset`. Only the alert moved.
#:
#: **A SAVED PROJECT CAN ONLY EVER HOLD ONE OF THE TWO.** The store keys a
#: result by (result id, calculation input, fingerprint), so for one molecule
#: and one drawing they were the same slot and whichever ran last replaced the
#: other. So this migration re-files one entry; it does not, and could not,
#: recover a second one that was never stored.
MIGRATED_RESULT_IDS: dict[tuple[str, str], str] = {
    ("functional_groups", "AlertResult"): "fragment_counts",
}

#: Replay order. Drawing results first, geometry on top: the geometry
#: descriptor run publishes the SAME descriptor ids as the drawing run, and
#: the panel keeps the latest, which must be the one a conformer produced.
_INPUT_ORDER = {DRAWING: 0, GEOMETRY: 1}


class BundleState(str, enum.Enum):
    NONE = "none"          # nothing was ever recorded for this molecule
    PARTIAL = "partial"    # recorded for this input, but something is missing
    COMPLETE = "complete"  # every expected part, every result it produced
    STALE = "stale"        # recorded, but for a different input


def _renamed_result(result: object, new_id: str) -> object:
    """A copy of `result` carrying `new_id` in its OWN id field.

    The field differs per result type, and `result_id_of` is the one place
    that knows which -- so this mirrors it rather than guessing. A type
    without a known id field is returned unchanged, which then fails the
    id check below and is dropped as unaddressable rather than stored under
    a name it does not agree with.
    """
    for field_name in ("alert_id", "report_id", "property_id", "spectrum_type"):
        if hasattr(result, field_name):
            return replace(result, **{field_name: new_id})  # type: ignore[type-var]
    return result


def result_id_of(result: object) -> str:
    """The id a result is filed under -- the same id the panel files it under.

    **Taken from the result's own field, per type**, because that is what
    `PropertyPanel` keys `_reports` and `_retained_results` on. Inventing a
    different id here would make "stored" and "shown" two vocabularies.
    A descriptor is namespaced by provider for the reason the panel keys
    `_descriptor_values` on the pair: two providers may share a short name.
    """
    if isinstance(result, DescriptorValue):
        return f"descriptor:{result.provider}:{result.descriptor_id}"
    if isinstance(result, ReportResult):
        return result.report_id
    if isinstance(result, AlertResult):
        return result.alert_id
    if isinstance(result, PerAtomDataset):
        return result.property_id
    if isinstance(result, SpectrumResult):
        return result.spectrum_type
    if isinstance(result, StructureSetResult):
        return result.set_id
    if isinstance(result, PhCurveResult):
        return result.curve_id
    if isinstance(result, TrajectoryResult):
        return result.trajectory_id
    raise TypeError(f"No result id for {type(result).__name__}")


def is_failure(result: object) -> bool:
    return getattr(result, "cache_state", None) is CacheState.FAILED


@dataclass(frozen=True)
class ResultIdentity:
    """Everything that decides whether a stored result answers a question.

    `producer` is the calculator id for a dispatched calculation, or the
    provider id for the always-on batch -- no result carries either itself.
    """

    molecule_uuid: str
    result_id: str
    calculation_input: str
    input_fingerprint: str
    producer: str
    parameters_key: str = ""
    #: The method, for result ids listed in `CURRENT_METHOD_VERSIONS`; "" for
    #: every other result. Part of the slot key, so two methods never share
    #: one. NOT the parameters key: a method is what the numbers MEAN.
    method_version: str = ""


@dataclass
class StoredResult:
    identity: ResultIdentity
    result: object
    #: The build that computed it. **NOT a calculator version -- no such
    #: thing exists in this application** (`CalculatorDefinition` and
    #: `Provenance` carry none). Recorded so a reader can see a result
    #: predates an update; it is not used to invalidate anything.
    application_version: str = ""
    #: True when this came out of a saved file rather than this session.
    restored: bool = False


@dataclass(frozen=True)
class BundlePart:
    """One producer's contribution to the automatic set, and what it made.

    `result_ids` is the part's own record of its output, which is what lets
    a lost result be noticed rather than silently absent.
    """

    part_id: str
    input_fingerprint: str
    result_ids: tuple[str, ...]
    failed: bool = False


@dataclass
class _MoleculeRecord:
    #: (result id, calculation input, input fingerprint, method version) -> result
    results: dict[tuple[str, str, str, str], StoredResult] = field(default_factory=dict)
    #: (part id, input fingerprint) -> part
    parts: dict[tuple[str, str], BundlePart] = field(default_factory=dict)
    #: calculation input -> fingerprints seen for it, oldest first. See
    #: `SessionResultStore._touch`.
    revisions: dict[str, list[str]] = field(default_factory=dict)


class ForeignProjectError(ValueError):
    pass


class SessionResultStore:
    def __init__(self, project_uuid: str) -> None:
        self.project_uuid = project_uuid
        self._molecules: dict[str, _MoleculeRecord] = {}
        #: Why entries did not come back from a saved file, by problem --
        #: `result_codec.PROBLEMS` plus `unaddressable`. Kept so a PARTIAL
        #: state can be explained rather than merely observed.
        self.load_problems: Counter[str] = Counter()
        #: Revisions kept per molecule, per calculation input -- `MAX_REVISIONS`
        #: unless the "Revisions kept" setting says otherwise. See `_touch`.
        self.max_revisions = MAX_REVISIONS

    # --- writing ----------------------------------------------------------

    def put(self, stored: StoredResult) -> None:
        identity = stored.identity
        record = self._molecules.setdefault(identity.molecule_uuid, _MoleculeRecord())
        record.results[(identity.result_id, identity.calculation_input, identity.input_fingerprint,
                        identity.method_version)] = stored
        self._touch(record, identity.calculation_input, identity.input_fingerprint)

    def record_part(self, molecule_uuid: str, part: BundlePart) -> None:
        # A part is always a DRAWING run's: `bundle_state` looks parts up by
        # the drawing fingerprint, and both dispatchers finish a part only
        # for DRAWING (`descriptor_service._finish_part`).
        record = self._molecules.setdefault(molecule_uuid, _MoleculeRecord())
        record.parts[(part.part_id, part.input_fingerprint)] = part
        self._touch(record, DRAWING, part.input_fingerprint)

    def _touch(self, record: _MoleculeRecord, calculation_input: str, fingerprint: str) -> None:
        """Keep the most recent `max_revisions` fingerprints OF EACH INPUT.

        **KEYED BY FINGERPRINT, SO AN EDIT DOES NOT OVERWRITE.** The first
        version keyed on the result id alone, so drawing a change replaced
        the previous structure's results -- and undoing back to it, which is
        the commonest edit there is, recomputed everything. Measured by
        `test_an_edit_recomputes_and_an_undo_back_does_not`.

        Bounded because every edit is a new fingerprint: a result set is
        tens of KiB, and a long drawing session is hundreds of edits.

        **COUNTED PER INPUT, BECAUSE ONE LIST LET A CONFORMER SEARCH EVICT THE
        CURRENT DRAWING.** Every conformer change reruns the descriptors on
        GEOMETRY (`MainWindow._on_conformers_changed`), so each search is a
        new geometry fingerprint while the drawing's stays put. With one list
        shared by both, measured 2026-09-14: the results of a drawing that
        was still current -- hand-run ones included, which nothing reruns --
        were gone after 8 searches at the default, and after ONE at a limit
        of 1, which the Settings window would have offered.
        """
        revisions = record.revisions.setdefault(calculation_input, [])
        if fingerprint in revisions:
            revisions.remove(fingerprint)
        revisions.append(fingerprint)
        self._trim(record)

    def _trim(self, record: _MoleculeRecord) -> None:
        for calculation_input, revisions in record.revisions.items():
            while len(revisions) > self.max_revisions:
                oldest = revisions.pop(0)
                record.results = {
                    k: v for k, v in record.results.items() if (k[1], k[2]) != (calculation_input, oldest)
                }
                if calculation_input == DRAWING:
                    record.parts = {k: v for k, v in record.parts.items() if k[1] != oldest}

    def revisions_beyond(self, limit: int) -> tuple[int, int]:
        """(result sets, molecules) that a limit of `limit` would evict now.

        A result set is one input's results for one fingerprint -- what a
        single revision holds. Counted BEFORE anything is dropped, for the
        Settings window's confirmation: lowering the limit trims at once, so
        the number has to be shown while it can still be declined.
        """
        result_sets = molecules = 0
        for record in self._molecules.values():
            over = sum(max(0, len(revisions) - limit) for revisions in record.revisions.values())
            result_sets += over
            molecules += bool(over)
        return result_sets, molecules

    def set_max_revisions(self, limit: int) -> None:
        """Change the limit and apply it to every molecule AT ONCE.

        Only cached results are dropped: the structures themselves live in
        the project and the undo stack, so undoing back to an evicted one
        recomputes rather than failing. And no saved file ever carried them:
        every save passes the current fingerprints, so `to_dict` writes only
        each molecule's current revision of each input, which any limit of
        at least 1 keeps.
        """
        if limit < 1:
            raise ValueError(f"at least one revision must be kept, not {limit}")
        self.max_revisions = limit
        for record in self._molecules.values():
            self._trim(record)

    def forget_molecule(self, molecule_uuid: str) -> None:
        self._molecules.pop(molecule_uuid, None)

    def clear(self) -> None:
        self._molecules.clear()
        self.load_problems.clear()

    # --- reading ----------------------------------------------------------

    def fresh_results(self, molecule_uuid: str, fingerprints: dict[str, str]) -> list[StoredResult]:
        """Results whose input is still the input, in replay order.

        `fingerprints` maps each calculation input to the molecule's CURRENT
        fingerprint for it. An input with no entry is not replayed: the
        caller could not say what it is now, so nothing can vouch for it.
        """
        record = self._molecules.get(molecule_uuid)
        if record is None:
            return []
        fresh = [
            stored
            for (_, calculation_input, fingerprint, _method), stored in record.results.items()
            if fingerprints.get(calculation_input) == fingerprint
        ]
        # One result per id and input: where the current method's result is
        # here, a legacy method's result for the same slot is kept in the store
        # (and saved) but not REPLAYED, so a view shows the current method and
        # never both under one id.
        current = {
            (s.identity.result_id, s.identity.calculation_input)
            for s in fresh
            if s.identity.method_version == CURRENT_METHOD_VERSIONS.get(s.identity.result_id, "")
        }
        fresh = [
            s for s in fresh
            if s.identity.method_version == CURRENT_METHOD_VERSIONS.get(s.identity.result_id, "")
            or (s.identity.result_id, s.identity.calculation_input) not in current
        ]
        fresh.sort(key=lambda s: _INPUT_ORDER.get(s.identity.calculation_input, 99))
        return fresh

    def bundle_state(
        self,
        molecule_uuid: str,
        drawing_fingerprint: str,
        expected_parts: set[str],
        application_version: str | None = None,
    ) -> tuple[BundleState, set[str]]:
        """Whether the automatic set can be replayed instead of recomputed.

        Returns the state and the parts that are missing or incomplete. A
        part counts only if it was recorded for THIS input AND every result
        it says it produced is actually held -- which is the check that
        turns a dropped entry into a rerun rather than a gap.

        A FAILED part counts as done. Within a session that is what stops a
        failing sidecar being retried on every selection; failures are never
        written to a file (`to_dict`), so the next session retries.

        **`application_version`, when given, must match every result the
        part holds.** The user guide promises that a project opened in a
        later build gets that build's chemistry perception rather than a
        frozen snapshot of an older one. Saved results would break that
        silently, so the always-on set -- a second or so of work -- is
        replayed only when THIS build computed it. Results a person ran by
        hand are not part of any bundle and are still restored, marked with
        the build that produced them.
        """
        record = self._molecules.get(molecule_uuid)
        if record is None or not record.parts:
            return BundleState.NONE, set(expected_parts)
        missing: set[str] = set()
        for part_id in expected_parts:
            part = record.parts.get((part_id, drawing_fingerprint))
            if part is None:
                missing.add(part_id)
                continue
            # The CURRENT method's result: a legacy one (kept beside it) must
            # not vouch for a set that now computes something else.
            keys = [(rid, DRAWING, drawing_fingerprint, CURRENT_METHOD_VERSIONS.get(rid, ""))
                    for rid in part.result_ids]
            held = all(
                key in record.results
                and (
                    application_version is None
                    or record.results[key].application_version == application_version
                )
                for key in keys
            )
            if not held:
                missing.add(part_id)
        if not missing:
            return BundleState.COMPLETE, set()
        if not any(fingerprint == drawing_fingerprint for _, fingerprint in record.parts):
            return BundleState.STALE, missing
        return BundleState.PARTIAL, missing

    def molecule_uuids(self) -> list[str]:
        return list(self._molecules)

    # --- the persisted envelope -------------------------------------------

    def to_dict(self, current_fingerprints: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
        """The `calculation_results` block of a project file.

        `current_fingerprints` (molecule uuid -> input -> fingerprint), when
        given, drops entries that no longer describe the structure, so a
        file does not accumulate every revision a molecule ever had.

        **WHICH FAILURES ARE WRITTEN, AND THE FIRST RULE WAS WRONG.** "Never
        write a failure" made the always-on set incomplete on EVERY reopen:
        its shape descriptors fail deterministically on a molecule with no
        conformer ("Needs a 3D conformer"), the part lists them, and a part
        whose results are not all in the file is PARTIAL by design. So:

            a failed PART (the producer raised)       not written -- retried
            a FAILED result inside a sound part       written -- the
                                                      producer's own answer
                                                      for this input
            any other FAILED result (a manual run)    not written -- it may
                                                      be an environment
                                                      fault, like a missing
                                                      sidecar

        An entry the codec cannot encode is skipped and logged; saving must
        never fail because of one result. Its part then points at a result
        that is not in the file, which is exactly what makes that part load
        as PARTIAL.
        """
        molecules: dict[str, Any] = {}
        for molecule_uuid, record in self._molecules.items():
            current = (current_fingerprints or {}).get(molecule_uuid)
            if current_fingerprints is not None and current is None:
                continue  # the molecule is no longer in the project
            vouched = {
                (rid, part.input_fingerprint)
                for part in record.parts.values()
                if not part.failed
                for rid in part.result_ids
            }
            results = []
            for stored in record.results.values():
                identity = stored.identity
                if is_failure(stored.result) and (identity.result_id, identity.input_fingerprint) not in vouched:
                    continue
                if current is not None and current.get(identity.calculation_input) != identity.input_fingerprint:
                    continue
                try:
                    encoded = result_codec.encode(stored.result)
                except result_codec.CodecError as exc:
                    logger.warning("Not saving %s for %s: %s", identity.result_id, molecule_uuid, exc)
                    continue
                results.append({
                    "result_id": identity.result_id,
                    "calculation_input": identity.calculation_input,
                    "input_fingerprint": identity.input_fingerprint,
                    "producer": identity.producer,
                    "parameters_key": identity.parameters_key,
                    **({"method_version": identity.method_version} if identity.method_version else {}),
                    "application_version": stored.application_version,
                    "result": encoded,
                })
            parts = [
                {
                    "part_id": part.part_id,
                    "input_fingerprint": part.input_fingerprint,
                    "result_ids": list(part.result_ids),
                }
                for part in record.parts.values()
                if not part.failed
                and (current is None or current.get(DRAWING) == part.input_fingerprint)
            ]
            if results or parts:
                molecules[molecule_uuid] = {
                    "bundle": {"bundle_id": AUTOMATIC_BUNDLE_ID, "parts": parts},
                    "results": results,
                }
        return {
            "envelope_version": ENVELOPE_VERSION,
            "project_uuid": self.project_uuid,
            "molecules": molecules,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None, project_uuid: str) -> SessionResultStore:
        """A store from a saved block. Never raises on CONTENT.

        Unreadable entries are dropped and counted in `load_problems`. A
        block written for a different project, or by a newer envelope, is
        ignored entirely rather than trusted in part -- the manifests would
        otherwise vouch for results from somewhere else.
        """
        store = cls(project_uuid)
        if not data:
            return store
        if data.get("envelope_version", 0) > ENVELOPE_VERSION:
            logger.warning("Saved results use envelope v%s; ignoring them", data.get("envelope_version"))
            store.load_problems[result_codec.UNSUPPORTED_VERSION] += 1
            return store
        if data.get("project_uuid") not in (None, project_uuid):
            logger.warning("Saved results belong to project %s, not %s", data.get("project_uuid"), project_uuid)
            store.load_problems["foreign_project"] += 1
            return store
        for molecule_uuid, block in (data.get("molecules") or {}).items():
            try:
                bundle = block.get("bundle") or {}
                if bundle.get("bundle_id") == AUTOMATIC_BUNDLE_ID:
                    for raw in bundle.get("parts") or []:
                        store.record_part(molecule_uuid, BundlePart(
                            part_id=str(raw["part_id"]),
                            input_fingerprint=str(raw["input_fingerprint"]),
                            result_ids=tuple(str(r) for r in raw["result_ids"]),
                        ))
                entries = block.get("results") or []
            except (AttributeError, KeyError, TypeError) as exc:
                logger.warning("Unreadable saved results for %s: %s", molecule_uuid, exc)
                store.load_problems[result_codec.MALFORMED] += 1
                continue
            for raw in entries:
                store._load_entry(molecule_uuid, raw)
        return store

    def _load_entry(self, molecule_uuid: str, raw: Any) -> None:
        try:
            identity = ResultIdentity(
                molecule_uuid=molecule_uuid,
                result_id=str(raw["result_id"]),
                calculation_input=str(raw["calculation_input"]),
                input_fingerprint=str(raw["input_fingerprint"]),
                producer=str(raw.get("producer", "")),
                parameters_key=str(raw.get("parameters_key", "")),
                method_version=str(raw.get("method_version", "")),
            )
            if identity.result_id in RETIRED_RESULT_IDS:
                # Before decoding: a retired entry is dropped for what it IS,
                # whether or not this build could still read it.
                logger.info("Dropping retired saved result %s for %s: %s", identity.result_id,
                            molecule_uuid, RETIRED_RESULT_IDS[identity.result_id])
                self.load_problems["retired"] += 1
                return
            result = result_codec.decode(raw["result"])
        except result_codec.CodecError as exc:
            logger.warning("Dropping saved result for %s: %s", molecule_uuid, exc)
            self.load_problems[exc.problem] += 1
            return
        except (KeyError, TypeError, AttributeError) as exc:
            logger.warning("Dropping malformed saved result for %s: %s", molecule_uuid, exc)
            self.load_problems[result_codec.MALFORMED] += 1
            return
        migrated_to = MIGRATED_RESULT_IDS.get(
            (identity.result_id, type(result).__name__)
        )
        if migrated_to is not None:
            result = _renamed_result(result, migrated_to)
            logger.info(
                "Migrating saved result %s for %s to %s",
                identity.result_id, molecule_uuid, migrated_to,
            )
            identity = replace(identity, result_id=migrated_to)
            self.load_problems["migrated"] += 1
        if not identity.method_version and identity.result_id in LEGACY_METHOD_VERSIONS:
            # Saved before methods were recorded: by the rule, the legacy method.
            legacy, label = LEGACY_METHOD_VERSIONS[identity.result_id]
            identity = replace(identity, method_version=legacy)
            if hasattr(result, "name"):
                result = replace(result, name=label)  # type: ignore[type-var]
            self.load_problems["legacy_method"] += 1
        try:
            if result_id_of(result) != identity.result_id:
                raise TypeError("result id does not match its entry")
        except TypeError as exc:
            logger.warning("Dropping saved result for %s: %s", molecule_uuid, exc)
            self.load_problems["unaddressable"] += 1
            return
        self.put(StoredResult(
            identity=identity,
            result=result,
            application_version=str(raw.get("application_version", "")),
            restored=True,
        ))
