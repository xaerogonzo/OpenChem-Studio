"""Read-only Results reader dump: focus, search, jumps, expects."""

from __future__ import annotations

from openchem.app.results_dump import (
    SCHEMA_VERSION,
    encode_results_dump,
    evaluate_results_expect,
    results_dump,
)
from openchem.ui.widgets.results_view import ResultsView
from tests.conftest import dispose
from test_results_reader import _two


def test_dump_matches_the_reader(qapp):
    window = ResultsView("mol-1")
    window.set_reports(_two())
    window.resize(480, 600)
    window.show()
    qapp.processEvents()
    dump = results_dump(window, tag="all", detached=False, dock_hidden=False)
    assert dump["schema_version"] == SCHEMA_VERSION
    assert dump["tag"] == "all"
    assert dump["focus"] == ""
    assert dump["reports"] == 2
    assert dump["facts"] == 2
    assert dump["report_ids"] == ["elemental_analysis", "lewis_sites"]
    assert dump["detached"] is False
    assert "Formula" in dump["jumps"]
    encoded = encode_results_dump(dump)
    assert "elemental_analysis" in encoded
    dispose(window)


def test_focus_and_search_are_in_the_dump(qapp):
    window = ResultsView("mol-1")
    window.set_reports(_two())
    window._selector_search.setText("Formula")
    window.set_focus("elemental_analysis")
    dump = results_dump(window, tag="jump")
    assert dump["search"] == "Formula"
    assert dump["focus"] == "elemental_analysis"
    dispose(window)


def test_results_expect_unknown_key_fails():
    dump = {
        "focus": "",
        "search": "Formula",
        "all_results_visible": False,
        "jumps": ["Formula"],
        "reports": 2,
        "facts": 2,
        "detached": False,
    }
    assert evaluate_results_expect(dump, None) is None
    assert evaluate_results_expect(dump, {"focus": "", "search": "Formula", "jumps_at_least": 1}) == []
    problems = evaluate_results_expect(dump, {"focus": "elemental_analysis"})
    assert problems and "focus" in problems[0]
    unknown = evaluate_results_expect(dump, {"pretty": True})
    assert unknown and "unknown expect keys" in unknown[0]
