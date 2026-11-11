"""Read-only dump of the Results reader.

Reads widgets and the merged reports the reader already holds.
"""

from __future__ import annotations

from typing import Any

from openchem.app.inspector_dump import encode_inspect_dump, json_safe

#: Results dump JSON schema version. Bump when the record shape changes.
SCHEMA_VERSION = 1

#: Keys the results step may assert. An unknown expect key fails closed.
RESULTS_DUMP_EXPECT_KEYS = frozenset(
    {
        "focus",
        "search",
        "all_results_visible",
        "jumps_at_least",
        "reports",
        "facts",
        "detached",
    }
)


def encode_results_dump(payload: dict[str, Any]) -> str:
    return encode_inspect_dump(payload)


def results_dump(
    reader,
    *,
    tag: str = "",
    detached: bool | None = None,
    dock_hidden: bool | None = None,
) -> dict[str, Any]:
    """Facts about a ``ResultsView``. Never raises."""
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "tag": tag,
        "dump_status": "ok",
        "dump_error": None,
        "detached": detached,
        "dock_hidden": dock_hidden,
    }
    try:
        merged = reader.merged() if hasattr(reader, "merged") else None
        search = reader._selector_search.text() if getattr(reader, "_selector_search", None) is not None else ""
        all_button = getattr(reader, "_all_results_button", None)
        open_button = getattr(reader, "_open_button", None)
        jumps = list(reader._view.section_jumps()) if hasattr(getattr(reader, "_view", None), "section_jumps") else []
        reports = list(getattr(merged, "reports", ()) or ())
        payload["focus"] = reader.focus() if hasattr(reader, "focus") else ""
        payload["search"] = search
        payload["all_results_visible"] = bool(all_button.isVisible()) if all_button is not None else None
        payload["jumps"] = jumps
        payload["reports"] = len(reports)
        payload["facts"] = len(getattr(merged, "facts", ()) or ())
        payload["stale"] = list(merged.stale_report_ids()) if merged is not None else []
        payload["report_ids"] = [getattr(report, "report_id", "") for report in reports]
        payload["open_button"] = {
            "visible": bool(open_button.isVisible()) if open_button is not None else None,
            "text": open_button.text() if open_button is not None else "",
        }
        payload["layout"] = {
            "reader_width": reader.width() if reader is not None else None,
            "reader_height": reader.height() if reader is not None else None,
        }
        payload["molecule_uuid"] = getattr(reader, "_molecule_uuid", "") or ""
    except Exception as exc:  # noqa: BLE001 - a dump must not abort the drive
        payload["dump_status"] = "partial"
        payload["dump_error"] = f"{type(exc).__name__}: {exc}"
    return json_safe(payload)


def evaluate_results_expect(dump: dict[str, Any], expect: dict[str, Any] | None) -> list[str] | None:
    if not expect:
        return None
    unknown = sorted(str(key) for key in expect if key not in RESULTS_DUMP_EXPECT_KEYS)
    if unknown:
        return [f"unknown expect keys: {', '.join(unknown)}"]
    problems: list[str] = []
    if "focus" in expect and dump.get("focus") != expect["focus"]:
        problems.append(f"focus {dump.get('focus')!r}, expected {expect['focus']!r}")
    if "search" in expect and dump.get("search") != expect["search"]:
        problems.append(f"search {dump.get('search')!r}, expected {expect['search']!r}")
    if "all_results_visible" in expect and dump.get("all_results_visible") != bool(expect["all_results_visible"]):
        problems.append(f"All results visible={dump.get('all_results_visible')}")
    if "jumps_at_least" in expect and len(dump.get("jumps") or []) < int(expect["jumps_at_least"]):
        problems.append(
            f"{len(dump.get('jumps') or [])} jumps, expected at least {expect['jumps_at_least']}"
        )
    if "reports" in expect and dump.get("reports") != expect["reports"]:
        problems.append(f"reports {dump.get('reports')}, expected {expect['reports']}")
    if "facts" in expect and dump.get("facts") != expect["facts"]:
        problems.append(f"facts {dump.get('facts')}, expected {expect['facts']}")
    if "detached" in expect and dump.get("detached") != bool(expect["detached"]):
        problems.append(f"detached {dump.get('detached')}, expected {expect['detached']}")
    return problems
