"""Read-only dump of an open Calculator Inspector.

The helper parses molblocks the dialog already holds, reads Qt widgets, and
returns JSON-safe values. It does not run a calculator or mutate the dialog.
"""

from __future__ import annotations

import json
import math
from typing import Any

from openchem.chem.molblock_summary import same_if_both, summarize_molblock
from openchem.domain.molecule import MoleculeModel

SCHEMA_VERSION = 1

#: Provenance.parameters keys that identify the calculation without dumping paths.
_PROVENANCE_PARAMETER_KEYS = (
    "pH",
    "charge_method",
    "include_hydrogens",
    "hydrogen_aggregation",
    "method",
)

INSPECT_REPORT_EXPECT_KEYS = frozenset(
    {
        "structure",
        "formal_charge",
        "depiction_charge",
        "drawing_charge",
        "pane_2d_width_px",
        "pane_2d_min_width_px",
        "pane_3d_width_px",
        "pane_3d_min_width_px",
        "2d_share",
    }
)


def json_safe(value: Any) -> Any:
    """JSON-encodable form: non-finite floats become ``None``."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return value
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if hasattr(value, "value") and not isinstance(value, type):
        return json_safe(value.value)
    return str(value)


def encode_inspect_dump(payload: dict[str, Any]) -> str:
    """One compact JSON object. Non-finite floats are already ``None``."""
    return json.dumps(
        json_safe(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _label_text(widget) -> str:
    if widget is None:
        return ""
    return str(widget.text())


def _structure_record(engine, molblock: str | None, *, with_coordinates: bool) -> dict[str, Any]:
    return summarize_molblock(engine, molblock, with_coordinates=with_coordinates)


def inspect_dump(dialog, molecule: MoleculeModel | None = None, *, tag: str = "") -> dict[str, Any]:
    """Facts about ``dialog`` and the molecule it was built for.

    Never raises: a malformed molblock becomes ``null`` fields and ``dump_status``.
    """
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "tag": tag,
        "dump_status": "ok",
        "dump_error": None,
    }
    try:
        view = getattr(dialog, "_view", None)
        engine = getattr(dialog, "_engine", None) or getattr(view, "_engine", None)
        subject = molecule if molecule is not None else getattr(view, "_molecule", None)
        result = getattr(dialog, "_result", None)
        if subject is not None:
            payload["molecule"] = {
                "name": getattr(subject, "display_name", "") or "",
                "uuid": getattr(subject, "uuid", "") or "",
            }
        else:
            payload["molecule"] = {"name": "", "uuid": ""}
        payload["calculator"] = _calculator_section(dialog, result)
        payload["provenance"] = _provenance_section(result)
        drawing_block = getattr(subject, "molblock", None) if subject is not None else None
        depiction_block = getattr(view, "_depiction_molblock", None)
        shown_block = getattr(view, "_conformer_molblock", None)
        drawing = _structure_record(engine, drawing_block, with_coordinates=False) if engine else _absent()
        depiction = _structure_record(engine, depiction_block, with_coordinates=False) if engine else _absent()
        shown_3d = _structure_record(engine, shown_block, with_coordinates=True) if engine else _absent(with_coordinates=True)
        payload["drawing"] = drawing
        payload["depiction"] = depiction
        payload["shown_3d"] = shown_3d
        payload["structure_source"] = getattr(view, "_structure_source", None)
        payload["comparison"] = {
            "depiction_same_formal_charge_as_drawing": same_if_both(
                depiction.get("net_formal_charge"), drawing.get("net_formal_charge")
            ),
            "depiction_same_heavy_atom_count_as_drawing": same_if_both(
                depiction.get("heavy_atom_count"), drawing.get("heavy_atom_count")
            ),
            "shown_3d_same_formal_charge_as_drawing": same_if_both(
                shown_3d.get("net_formal_charge"), drawing.get("net_formal_charge")
            ),
            "shown_3d_same_heavy_atom_count_as_drawing": same_if_both(
                shown_3d.get("heavy_atom_count"), drawing.get("heavy_atom_count")
            ),
        }
        # Expect aliases: formal_charge is the 3D-supplied structure, not the drawing.
        payload["drawing_charge"] = drawing.get("net_formal_charge")
        payload["depiction_charge"] = depiction.get("net_formal_charge")
        payload["formal_charge"] = shown_3d.get("net_formal_charge")
        payload["text"] = {
            "placement": _label_text(getattr(view, "_placement_label", None)),
            "name": _label_text(getattr(view, "_name_label", None)),
            "summary": _label_text(getattr(view, "_summary_label", None)),
            "summary_note": _label_text(getattr(view, "_note_label", None)),
            "balance": _label_text(getattr(view, "_balance_label", None)),
        }
        payload["layout"] = _layout_section(dialog, view)
        payload["table"] = _table_section(view)
    except Exception as exc:  # noqa: BLE001 - a dump must not abort the drive
        payload["dump_status"] = "partial"
        payload["dump_error"] = f"{type(exc).__name__}: {exc}"
    return json_safe(payload)


def _absent(*, with_coordinates: bool = False) -> dict[str, Any]:
    record = {
        "present": False,
        "parse_ok": None,
        "atom_count": None,
        "heavy_atom_count": None,
        "explicit_hydrogen_count": None,
        "net_formal_charge": None,
    }
    if with_coordinates:
        record["has_3d_coordinates"] = None
        record["z_span_angstrom"] = None
    return record


def _calculator_section(dialog, result) -> dict[str, Any]:
    cache = getattr(result, "cache_state", None)
    cache_state = cache.value if hasattr(cache, "value") else cache
    error = getattr(result, "error", None) if result is not None else None
    return {
        "id": getattr(dialog, "_requested_calculator_id", None),
        "result_property_id": getattr(result, "property_id", None) if result is not None else None,
        "result_name": getattr(result, "name", None) if result is not None else None,
        "method": getattr(result, "method", None) if result is not None else None,
        "cache_state": cache_state,
        "inapplicable": bool(getattr(result, "inapplicable", False)) if result is not None else None,
        "error_present": bool(error),
        "error_summary": getattr(result, "error_summary", None) if result is not None else None,
        "error": error,
    }


def _provenance_section(result) -> dict[str, Any]:
    provenance = getattr(result, "provenance", None) if result is not None else None
    parameters = dict(getattr(provenance, "parameters", None) or {})
    picked = {key: parameters[key] for key in _PROVENANCE_PARAMETER_KEYS if key in parameters}
    method = getattr(provenance, "method", None) if provenance is not None else getattr(result, "method", None)
    return {"method": method, "parameters": picked}


def _layout_section(dialog, view) -> dict[str, Any]:
    splitter = getattr(view, "_views_splitter", None)
    pane_2d = getattr(view, "_svg_widget", None)
    pane_3d = None
    viewer = getattr(view, "_viewer3d", None)
    if viewer is not None and hasattr(viewer, "widget"):
        pane_3d = viewer.widget()
    sizes = list(splitter.sizes()) if splitter is not None else []
    total = sum(sizes)
    share = (sizes[0] / total) if total else None
    return {
        "dialog_width": dialog.width() if dialog is not None else None,
        "dialog_height": dialog.height() if dialog is not None else None,
        "views_splitter_width": splitter.width() if splitter is not None else None,
        "views_splitter_sizes": sizes,
        "2d_share": share,
        "pane_2d_width_px": pane_2d.width() if pane_2d is not None else None,
        "pane_2d_min_width_px": pane_2d.minimumWidth() if pane_2d is not None else None,
        "pane_3d_width_px": pane_3d.width() if pane_3d is not None else None,
        "pane_3d_min_width_px": pane_3d.minimumWidth() if pane_3d is not None else None,
    }


def _table_section(view) -> dict[str, Any]:
    model = getattr(view, "_table_model", None)
    proxy = getattr(view, "_table_proxy", None)
    layer = getattr(view, "_layer_2d", None)
    labels = getattr(layer, "atom_labels", None) if layer is not None else None
    filt = getattr(view, "_table_filter", None)
    selected = view.selected_atom() if view is not None and hasattr(view, "selected_atom") else None
    return {
        "model_rows": model.rowCount() if model is not None else None,
        "visible_rows": proxy.rowCount() if proxy is not None else None,
        "filter": filt.text() if filt is not None else "",
        "labels_2d": len(labels or {}) if layer is not None else 0,
        "selected_atom": selected,
        "emphasised_atom": getattr(view, "_emphasised", None),
    }


def evaluate_inspect_expect(dump: dict[str, Any], expect: dict[str, Any] | None) -> list[str] | None:
    """Problems for a nonempty ``expect`` object, or ``None`` when no assertion is due.

    Unknown keys are a failed assertion, never a silent pass.
    """
    if not expect:
        return None
    unknown = sorted(str(key) for key in expect if key not in INSPECT_REPORT_EXPECT_KEYS)
    problems: list[str] = []
    if unknown:
        problems.append(f"unknown expect keys: {', '.join(unknown)}")
        return problems
    checks = {
        "structure": dump.get("structure_source"),
        "formal_charge": dump.get("formal_charge"),
        "depiction_charge": dump.get("depiction_charge"),
        "drawing_charge": dump.get("drawing_charge"),
        "pane_2d_width_px": (dump.get("layout") or {}).get("pane_2d_width_px"),
        "pane_2d_min_width_px": (dump.get("layout") or {}).get("pane_2d_min_width_px"),
        "pane_3d_width_px": (dump.get("layout") or {}).get("pane_3d_width_px"),
        "pane_3d_min_width_px": (dump.get("layout") or {}).get("pane_3d_min_width_px"),
        "2d_share": (dump.get("layout") or {}).get("2d_share"),
    }
    for key, expected in expect.items():
        actual = checks[key]
        if actual != expected:
            problems.append(f"{key} {actual}, expected {expected}")
    return problems


def dispose_driver_inspector(dialog) -> None:
    """Close and schedule deletion of a driver-owned Inspector. Hide-only is not enough."""
    if dialog is None:
        return
    dialog.close()
    dialog.deleteLater()
