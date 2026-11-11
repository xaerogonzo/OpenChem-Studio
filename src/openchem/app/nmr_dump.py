"""Read-only dump of an open NMR viewer.

Parses no chemistry. It reads the widgets the viewer already holds.
"""

from __future__ import annotations

from typing import Any

from openchem.app.inspector_dump import encode_inspect_dump, evaluate_keyed_expect, json_safe

#: NMR dump JSON schema version. Bump when the record shape changes.
SCHEMA_VERSION = 1

#: Keys nmr_panes may assert. An unknown expect key fails closed.
NMR_PANES_EXPECT_KEYS = frozenset(
    {
        "2d",
        "3d",
        "splitter",
        "spectrum",
        "table",
        "floor",
        "2d_share",
        "pane_2d_width_px",
        "pane_2d_min_width_px",
        "pane_3d_width_px",
        "pane_3d_min_width_px",
    }
)


def encode_nmr_dump(payload: dict[str, Any]) -> str:
    return encode_inspect_dump(payload)


def nmr_dump(view, *, tag: str = "") -> dict[str, Any]:
    """Facts about an ``NmrViewWidget``. Never raises."""
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "tag": tag,
        "dump_status": "ok",
        "dump_error": None,
    }
    try:
        svg = getattr(view, "_svg_widget", None)
        pane_3d = getattr(view, "_structure_3d", None)
        splitter = getattr(view, "_structures_splitter", None)
        spectrum = getattr(view, "_spectrum_widget", None)
        table = getattr(view, "_table_tabs", None)
        hide_2d = getattr(view, "_hide_2d_action", None)
        hide_3d = getattr(view, "_hide_3d_action", None)
        sizes = list(splitter.sizes()) if splitter is not None else []
        total = sum(sizes)
        share = (sizes[0] / total) if total else None
        min_2d = svg.minimumWidth() if svg is not None else None
        min_3d = pane_3d.minimumWidth() if pane_3d is not None else None
        floor = None if min_2d is None or min_3d is None else min(min_2d, min_3d)
        visible_2d = bool(svg is not None and not svg.isHidden())
        visible_3d = bool(pane_3d is not None and not pane_3d.isHidden())
        payload["2d"] = visible_2d
        payload["3d"] = visible_3d
        payload["splitter"] = bool(splitter is not None and not splitter.isHidden())
        payload["spectrum"] = bool(spectrum is not None and spectrum.isVisible())
        payload["table"] = bool(table is not None and table.isVisible())
        payload["floor"] = floor
        payload["hide"] = {
            "2d_checked": bool(hide_2d.isChecked()) if hide_2d is not None else None,
            "3d_checked": bool(hide_3d.isChecked()) if hide_3d is not None else None,
        }
        payload["layout"] = {
            "2d_share": share,
            "structures_splitter_sizes": sizes,
            "pane_2d_width_px": svg.width() if svg is not None else None,
            "pane_2d_min_width_px": min_2d,
            "pane_3d_width_px": pane_3d.width() if pane_3d is not None else None,
            "pane_3d_min_width_px": min_3d,
            "viewer_width": view.width() if view is not None else None,
            "viewer_height": view.height() if view is not None else None,
        }
        combo = getattr(view, "_element_combo", None)
        payload["nucleus"] = combo.currentText() if combo is not None else ""
        payload["signal_rows"] = view._table.rowCount() if getattr(view, "_table", None) is not None else None
    except Exception as exc:  # noqa: BLE001 - a dump must not abort the drive
        payload["dump_status"] = "partial"
        payload["dump_error"] = f"{type(exc).__name__}: {exc}"
    return json_safe(payload)


def evaluate_nmr_expect(dump: dict[str, Any], expect: dict[str, Any] | None) -> list[str] | None:
    layout = dump.get("layout") or {}
    return evaluate_keyed_expect(
        expect,
        NMR_PANES_EXPECT_KEYS,
        {
            "2d": dump.get("2d"),
            "3d": dump.get("3d"),
            "splitter": dump.get("splitter"),
            "spectrum": dump.get("spectrum"),
            "table": dump.get("table"),
            "floor": dump.get("floor"),
            "2d_share": layout.get("2d_share"),
            "pane_2d_width_px": layout.get("pane_2d_width_px"),
            "pane_2d_min_width_px": layout.get("pane_2d_min_width_px"),
            "pane_3d_width_px": layout.get("pane_3d_width_px"),
            "pane_3d_min_width_px": layout.get("pane_3d_min_width_px"),
        },
    )
