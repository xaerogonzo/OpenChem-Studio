"""What a Results reader should show for ONE molecule, built from its stored results alone.

**WHY THIS EXISTS: A READER THAT IS NOT THE SELECTED MOLECULE'S.** `PropertyPanel` assembles
what the Results reader shows out of events that arrive while a molecule is selected
(`_on_report_computed`, `_on_alert_computed`, `_show_result`, ...), so it can only describe the
selected one. A second reader pinned to another molecule (Compare's side-by-side readers) needs the
same entries without selecting it, and without `ResultStoreService.replay`, which PUBLISHES every
stored result on the global event bus: every subscriber (the Property panel, Compare, the
descriptor aggregate) would process another molecule's results as if they had just been computed.

So this reads `ResultStore.fresh_results` directly and converts each result the way the panel's
handler for it does, using the same pure converters (`summarise`, `report_from_alert`,
`aggregate_descriptors`). Nothing here touches the bus, the selection or any widget.

**WHAT IT DOES NOT SHOW, and why that is stated rather than hidden.** Only results whose input
still matches the molecule's current structure (what a replay would restore); a stale result the
selected molecule's panel still holds is not here. `tests/test_reader_entries.py` holds this to the
panel on the kinds it covers.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import replace

from openchem.chem.report_adapter import report_from_alert
from openchem.domain.descriptor import DescriptorValue
from openchem.domain.descriptor_aggregate import aggregate_descriptors
from openchem.domain.report import StructureReport
from openchem.domain.result_store import StoredResult
from openchem.domain.scientific_result import (
    AlertResult,
    PerAtomDataset,
    PhCurveResult,
    SpectrumResult,
    StructureSetResult,
    TrajectoryResult,
)
from openchem.ui.result_adapters import summarise

#: Kinds a stored result can have that this builder does not know how to show. They are skipped,
#: and a caller that wants to say so can read what `entries_from_stored` returns as `skipped`.
Projection = Callable[[str, int], Sequence]


def _summarised(result, result_id, name, category, version):
    return summarise(
        result, result_id=result_id, name=name, category=category, structure_version=version
    )


def entries_from_stored(
    stored: Iterable[StoredResult],
    *,
    structure_version: int,
    category_of: Callable[[str], str],
) -> tuple[list, list[str]]:
    """The reader entries for these stored results, and the ids of any it could not show.

    One entry per result id (a later result replaces an earlier one, as the panel's dict does),
    the descriptors folded into the ONE aggregate entry the panel builds, in the panel's order:
    reports, then the descriptor aggregate.
    """
    reports: dict[str, object] = {}
    descriptors: dict[tuple[str, str], DescriptorValue] = {}
    molecule_uuid = ""
    skipped: list[str] = []
    for item in stored:
        result = item.result
        if isinstance(result, DescriptorValue):
            descriptors[(result.provider, result.descriptor_id)] = result
            molecule_uuid = molecule_uuid or result.molecule_uuid
        elif isinstance(result, AlertResult):
            reports[result.alert_id] = replace(
                report_from_alert(result), structure_version=structure_version
            )
        elif isinstance(result, StructureReport):
            # Re-stamped, as `event_for` does on a replay: the stored stamp is a counter from
            # whichever session computed it, and the fingerprint match is what vouches for it now.
            restamped = replace(result, structure_version=structure_version)
            reports[restamped.report_id] = restamped
        elif isinstance(result, PerAtomDataset):
            reports[result.property_id] = _summarised(
                result, result.property_id, result.name,
                result.category or category_of(result.property_id), structure_version,
            )
        elif isinstance(result, SpectrumResult):
            reports[result.spectrum_type] = _summarised(
                result, result.spectrum_type, result.name,
                category_of(result.spectrum_type), structure_version,
            )
        elif isinstance(result, StructureSetResult):
            name = getattr(result, "name", result.set_id)
            reports[result.set_id] = _summarised(
                result, result.set_id, name, category_of(result.set_id), structure_version
            )
        elif isinstance(result, PhCurveResult):
            name = getattr(result, "name", result.curve_id)
            reports[result.curve_id] = _summarised(
                result, result.curve_id, name, category_of(result.curve_id), structure_version
            )
        elif isinstance(result, TrajectoryResult):
            name = getattr(result, "name", result.trajectory_id)
            reports[result.trajectory_id] = _summarised(
                result, result.trajectory_id, name,
                category_of(result.trajectory_id), structure_version,
            )
        else:
            skipped.append(item.identity.result_id)
    entries = list(reports.values())
    if descriptors:
        entries.append(
            aggregate_descriptors(
                molecule_uuid, descriptors.values(), structure_version=structure_version
            )
        )
    return entries, skipped


def entries_for_molecule(
    molecule_uuid: str,
    *,
    fresh_results: Callable[[], Iterable[StoredResult]],
    structure_version: int,
    category_of: Callable[[str], str],
    projections: Iterable[Projection] = (),
) -> tuple[list, int]:
    """Everything a reader pinned to `molecule_uuid` shows, and the version it describes.

    `projections` are the entries that are not stored results: the recipe answers kept in the
    project and the user's score answers, each a callable `(molecule_uuid, version) -> entries`,
    exactly as `PropertyPanel` is handed them. One that raises is logged and left out, as the
    panel does, so one unreadable answer cannot take the others with it.
    """
    entries, _skipped = entries_from_stored(
        fresh_results(), structure_version=structure_version, category_of=category_of
    )
    for projection in projections:
        try:
            entries.extend(projection(molecule_uuid, structure_version))
        except Exception:  # noqa: BLE001 - see docstring
            import logging

            logging.getLogger(__name__).exception(
                "Could not read a projection for %s", molecule_uuid
            )
    return entries, structure_version
