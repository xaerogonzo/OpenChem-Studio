"""Read-only NMR viewer dump: pane visibility, splitter share, expects."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from openchem.app.nmr_dump import (
    SCHEMA_VERSION,
    encode_nmr_dump,
    evaluate_nmr_expect,
    nmr_dump,
)
from test_nmr_view_widget import _make_view


def _show(view, qapp) -> None:
    view.resize(900, 700)
    view.show()
    qapp.processEvents()


def test_dump_matches_widgets_after_show(qapp):
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    _show(view, qapp)
    dump = nmr_dump(view, tag="both")
    assert dump["schema_version"] == SCHEMA_VERSION
    assert dump["tag"] == "both"
    assert dump["2d"] is True
    assert dump["3d"] is True
    assert dump["splitter"] is True
    assert dump["spectrum"] is True
    assert dump["table"] is True
    assert dump["floor"] == min(view._svg_widget.minimumWidth(), view._structure_3d.minimumWidth())
    sizes = view._structures_splitter.sizes()
    total = sum(sizes)
    assert dump["layout"]["structures_splitter_sizes"] == sizes
    assert dump["layout"]["2d_share"] == sizes[0] / total
    assert dump["layout"]["pane_2d_min_width_px"] == view._svg_widget.minimumWidth()
    assert dump["signal_rows"] == view._table.rowCount()
    encoded = encode_nmr_dump(dump)
    assert encoded.startswith("{")
    assert "schema_version" in encoded


def test_hide_2d_then_both_is_in_the_dump(qapp):
    view, _backend, _molecule, _spectrum = _make_view(qapp)
    _show(view, qapp)
    view._hide_2d_action.trigger()
    QApplication.processEvents()
    hidden_2d = nmr_dump(view, tag="hide-2d")
    assert hidden_2d["2d"] is False
    assert hidden_2d["3d"] is True
    assert hidden_2d["splitter"] is True
    assert hidden_2d["hide"]["2d_checked"] is True
    view._hide_3d_action.trigger()
    QApplication.processEvents()
    hidden_both = nmr_dump(view, tag="hide-both")
    assert hidden_both["2d"] is False
    assert hidden_both["3d"] is False
    assert hidden_both["splitter"] is False


def test_nmr_expect_unknown_key_fails():
    dump = {"2d": True, "3d": True, "splitter": True, "spectrum": True, "table": True, "floor": 80, "layout": {}}
    assert evaluate_nmr_expect(dump, None) is None
    assert evaluate_nmr_expect(dump, {"2d": True, "floor": 80}) == []
    unknown = evaluate_nmr_expect(dump, {"janky": True})
    assert unknown and "unknown expect keys" in unknown[0]
