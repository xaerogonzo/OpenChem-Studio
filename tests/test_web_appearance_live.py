"""The three real pages, told the look: a switch reaches a page that is up, and a page built dark starts dark.

Each assertion reads the PAGE (a style element, an attribute, a script variable), not what Python believes it
sent, which is the distinction the viewer work has had to learn more than once. Pixels are the driven script's
job (`benchmarks/visual/appearance.json`).
"""

from __future__ import annotations

import time

import conftest
import pytest

from openchem.domain.appearance import EffectiveAppearance
from openchem.ui import theme
from openchem.ui.widgets.ketcher_editor_backend import KetcherEditorBackend
from openchem.ui.widgets.mol3d_viewer_backend import Mol3DViewerBackend
from openchem.ui.widgets.molstar_viewer_backend import MolStarViewerBackend
from openchem.ui.widgets.web_appearance import (
    KETCHER_CHROME_SELECTORS,
    KETCHER_DARK_CSS,
    KETCHER_DIALOG_SELECTORS,
)

LIGHT = EffectiveAppearance.LIGHT
DARK = EffectiveAppearance.DARK
_TIMEOUT = 60


@pytest.fixture(autouse=True)
def _back_to_light(cheap_repolish):
    theme.set_effective(LIGHT)
    yield
    theme.set_effective(LIGHT)


def _wait_until(qapp, predicate, timeout_seconds: float = _TIMEOUT) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _page_value(qapp, page, script: str):
    """The script's value, read back from the page (`runJavaScript` marshals primitives only)."""
    result: dict[str, object] = {}
    page.runJavaScript(script, lambda value: result.__setitem__("value", value))
    _wait_until(qapp, lambda: "value" in result, timeout_seconds=10)
    return result.get("value")


def _eventually(qapp, page, script: str, expected, timeout_seconds: float = 15) -> bool:
    return _wait_until(qapp, lambda: _page_value(qapp, page, script) == expected, timeout_seconds)


_KETCHER_CSS = "(document.getElementById('openchem-appearance') || {textContent: null}).textContent"


def test_the_editor_page_is_given_the_dark_surround_and_gives_it_back(qapp):
    backend = KetcherEditorBackend()
    assert _wait_until(qapp, lambda: backend._ketcher_ready)

    theme.set_effective(DARK)
    assert _eventually(qapp, backend._page, _KETCHER_CSS, KETCHER_DARK_CSS)

    theme.set_effective(LIGHT)
    assert _eventually(qapp, backend._page, _KETCHER_CSS, "")


def test_an_editor_built_while_dark_starts_dark(qapp):
    theme.set_effective(DARK)
    backend = KetcherEditorBackend()

    assert _wait_until(qapp, lambda: backend._ketcher_ready)
    assert _eventually(qapp, backend._page, _KETCHER_CSS, KETCHER_DARK_CSS)


def test_every_toolbar_the_dark_stylesheet_names_exists_exactly_once(qapp):
    """A rebuilt editor that renames a CSS module would leave that toolbar light without a sound; this is the sound."""
    backend = KetcherEditorBackend()
    assert _wait_until(qapp, lambda: backend._ketcher_ready)

    for selector in KETCHER_CHROME_SELECTORS:
        count = _page_value(qapp, backend._page, f"document.querySelectorAll('{selector}').length")
        assert count == 1, f"{selector} matches {count} elements"


def test_dark_filters_the_toolbars_and_nothing_that_holds_the_drawing(qapp):
    """The drawing's colours are the editor's own; no filter may sit on the canvas or on anything around it."""
    backend = KetcherEditorBackend()
    assert _wait_until(qapp, lambda: backend._ketcher_ready)
    theme.set_effective(DARK)
    assert _eventually(qapp, backend._page, _KETCHER_CSS, KETCHER_DARK_CSS)

    canvas_chain = (
        "(function () { var e = document.querySelector('[class*=\"StructEditor-module_canvas\"]'); var bad = [];"
        " while (e && e !== document.documentElement) {"
        "   if (getComputedStyle(e).filter !== 'none') bad.push(e.className.toString()); e = e.parentElement; }"
        " return JSON.stringify(bad); })()"
    )
    assert _page_value(qapp, backend._page, canvas_chain) == "[]"

    for selector in KETCHER_CHROME_SELECTORS:
        filtered = _page_value(qapp, backend._page, f"getComputedStyle(document.querySelector('{selector}')).filter")
        assert filtered not in (None, "none"), selector

    theme.set_effective(LIGHT)
    assert _eventually(
        qapp, backend._page, f"getComputedStyle(document.querySelector('{KETCHER_CHROME_SELECTORS[1]}')).filter", "none"
    )


_DIALOG = KETCHER_DIALOG_SELECTORS[0]


def test_the_editors_own_dialog_is_dark_while_it_is_open_and_the_drawing_is_still_unfiltered(qapp):
    """A real Atom Properties dialog, opened through the backend: it was a white box in a dark window."""
    backend = KetcherEditorBackend()
    assert _wait_until(qapp, lambda: backend._ketcher_ready)
    _draw_methylamine(qapp, backend)
    theme.set_effective(DARK)
    assert _eventually(qapp, backend._page, _KETCHER_CSS, KETCHER_DARK_CSS)

    backend.open_atom_editor(1)
    filter_of_dialog = f"(document.querySelector('{_DIALOG}') ? getComputedStyle(document.querySelector('{_DIALOG}')).filter : 'no dialog')"
    assert _wait_until(
        qapp, lambda: "invert" in str(_page_value(qapp, backend._page, filter_of_dialog)), timeout_seconds=20
    ), "the editor's dialog is not filtered (a renamed CSS module?)"

    canvas_chain = (
        "(function () { var e = document.querySelector('[class*=\"StructEditor-module_canvas\"]'); var bad = [];"
        " while (e && e !== document.documentElement) {"
        "   if (getComputedStyle(e).filter !== 'none') bad.push(e.className.toString()); e = e.parentElement; }"
        " return JSON.stringify(bad); })()"
    )
    assert _page_value(qapp, backend._page, canvas_chain) == "[]"

    theme.set_effective(LIGHT)
    assert _eventually(qapp, backend._page, filter_of_dialog, "none")


_CANVAS_PAINT = (
    # `desc` and `defs` draw nothing but report the initial fill, black, so they are left out of the tally.
    "(function () { var t = {}; document.querySelectorAll('[class*=\"StructEditor-module_canvas\"] svg *:not(desc):not(defs)').forEach(function (e) {"
    " var cs = getComputedStyle(e); [cs.fill, cs.stroke].forEach(function (v) { t[v] = (t[v] || 0) + 1; }); });"
    " return JSON.stringify(t); })()"
)


def _canvas_paint(qapp, backend) -> dict[str, int]:
    import json

    return json.loads(_page_value(qapp, backend._page, _CANVAS_PAINT))


def _draw_methylamine(qapp, backend) -> None:
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.MolFromSmiles("NCC(=O)Cl")
    AllChem.Compute2DCoords(mol)
    backend.load_molblock(Chem.MolToMolBlock(mol))
    assert _wait_until(qapp, lambda: backend._loading_token is None, timeout_seconds=20)
    assert _wait_until(qapp, lambda: "rgb(48, 79, 247)" in _canvas_paint(qapp, backend), timeout_seconds=20)


def test_dark_turns_the_drawings_black_ink_light_and_leaves_every_atom_colour_alone(qapp):
    """The editor's own nitrogen, oxygen and chlorine are the same values dark and light; only black moved."""
    backend = KetcherEditorBackend()
    assert _wait_until(qapp, lambda: backend._ketcher_ready)
    _draw_methylamine(qapp, backend)
    light = _canvas_paint(qapp, backend)
    assert light.get("rgb(0, 0, 0)", 0) > 0

    theme.set_effective(DARK)
    assert _eventually(qapp, backend._page, _KETCHER_CSS, KETCHER_DARK_CSS)
    assert _wait_until(qapp, lambda: "rgb(0, 0, 0)" not in _canvas_paint(qapp, backend), timeout_seconds=15)
    dark = _canvas_paint(qapp, backend)
    assert dark.get("rgb(232, 232, 232)", 0) >= light["rgb(0, 0, 0)"] - 1  # every black became the light ink
    for colour in ("rgb(48, 79, 247)", "rgb(255, 13, 13)", "rgb(31, 208, 31)"):  # nitrogen, oxygen, chlorine
        assert dark.get(colour, 0) == light.get(colour, 0) > 0, colour

    theme.set_effective(LIGHT)
    assert _wait_until(qapp, lambda: _canvas_paint(qapp, backend).get("rgb(0, 0, 0)", 0) > 0, timeout_seconds=15)


def test_an_exported_picture_is_the_same_dark_and_light(qapp):
    """The theme is a stylesheet on the page; the editor's own image export is drawn from the structure."""
    backend = KetcherEditorBackend()
    assert _wait_until(qapp, lambda: backend._ketcher_ready)
    _draw_methylamine(qapp, backend)
    start = (
        "window.__image = null; window.ketcher.generateImage('NCC(=O)Cl', {outputFormat: 'svg'})"
        ".then(function (b) { return b.text(); }).then(function (t) { window.__image = t; }); 'started'"
    )
    pictures = {}
    for look in (LIGHT, DARK):
        theme.set_effective(look)
        assert _eventually(qapp, backend._page, _KETCHER_CSS, KETCHER_DARK_CSS if look is DARK else "")
        _page_value(qapp, backend._page, start)
        assert _wait_until(qapp, lambda: bool(_page_value(qapp, backend._page, "window.__image")), timeout_seconds=30)
        pictures[look] = _page_value(qapp, backend._page, "window.__image")
    assert "e8e8e8" not in pictures[DARK].lower()
    assert pictures[DARK] == pictures[LIGHT]


def _molblock_of(qapp, backend) -> str | None:
    got: list[str | None] = []
    backend.get_molblock(got.append)
    assert _wait_until(qapp, lambda: bool(got), timeout_seconds=20)
    return got[0]


def _without_stamp(molblock: str | None) -> list[str]:
    """A molblock's second line carries the writer's name and the MINUTE it was written; nothing else varies."""
    lines = (molblock or "").splitlines()
    return lines[:1] + lines[2:]


def test_a_structure_survives_a_switch_untouched(qapp):
    """The look never reloads the page, so what is drawn is exactly what was -- read back from Ketcher itself."""
    backend = KetcherEditorBackend()
    assert _wait_until(qapp, lambda: backend._ketcher_ready)
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.MolFromSmiles("CCO")
    AllChem.Compute2DCoords(mol)
    ethanol = Chem.MolToMolBlock(mol)
    edits: list[bool] = []
    backend.edited.connect(lambda: edits.append(True))
    backend.load_molblock(ethanol)
    assert _wait_until(qapp, lambda: backend._loading_token is None, timeout_seconds=20)
    before = _molblock_of(qapp, backend)
    assert before and "O" in before
    edits.clear()

    for look in (DARK, LIGHT, DARK, LIGHT, DARK):
        theme.set_effective(look)
        _wait_until(qapp, lambda: False, timeout_seconds=0.3)

    assert _without_stamp(_molblock_of(qapp, backend)) == _without_stamp(before)
    assert edits == []  # a change of look is never an edit


def test_the_macromolecule_page_is_told_and_is_told_again(qapp):
    backend = MolStarViewerBackend()
    backend.ensure_built()
    assert _wait_until(qapp, lambda: backend._viewer_ready)

    theme.set_effective(DARK)
    assert _eventually(qapp, backend._page, "document.documentElement.style.colorScheme", "dark")

    theme.set_effective(LIGHT)
    assert _eventually(qapp, backend._page, "document.documentElement.style.colorScheme", "light")


_MOLSTAR_PANELS = (".msp-layout-top", ".msp-layout-left", ".msp-layout-right")
_MOLSTAR_CANVAS_CHAIN = (
    "(function () { var e = document.querySelector('.msp-viewport'); var bad = [];"
    " while (e && e !== document.documentElement) {"
    "   if (getComputedStyle(e).filter !== 'none') bad.push(e.className.toString()); e = e.parentElement; }"
    " return e === null ? 'no canvas' : JSON.stringify(bad); })()"
)


def _molstar_filters(qapp, backend) -> dict[str, str]:
    script = (
        "(function () { var out = {}; %s.forEach(function (s) { var e = document.querySelector(s);"
        " out[s] = e ? getComputedStyle(e).filter : 'missing'; }); return JSON.stringify(out); })()"
    ) % list(_MOLSTAR_PANELS)
    import json

    return json.loads(_page_value(qapp, backend._page, script))


def test_the_macromolecule_panels_are_dark_and_the_canvas_is_never_filtered(qapp):
    """Mol*'s panels were one light skin in a dark window; they are filtered, and nothing above the 3D canvas is."""
    backend = MolStarViewerBackend()
    backend.ensure_built()
    assert _wait_until(qapp, lambda: backend._viewer_ready)

    theme.set_effective(DARK)
    assert _wait_until(
        qapp, lambda: all("invert" in value for value in _molstar_filters(qapp, backend).values()), timeout_seconds=20
    ), _molstar_filters(qapp, backend)
    # The viewport is built after the viewer reports ready, and later still when the machine is busy
    # (the whole suite lost the GPU context mid-run and read "no canvas" once); wait for it, then assert.
    assert _wait_until(
        qapp, lambda: _page_value(qapp, backend._page, _MOLSTAR_CANVAS_CHAIN) != "no canvas", timeout_seconds=20
    )
    assert _page_value(qapp, backend._page, _MOLSTAR_CANVAS_CHAIN) == "[]"

    theme.set_effective(LIGHT)
    assert _wait_until(
        qapp, lambda: set(_molstar_filters(qapp, backend).values()) == {"none"}, timeout_seconds=20
    ), _molstar_filters(qapp, backend)


def test_the_3d_page_follows_the_look_and_keeps_its_structure(qapp):
    reason = conftest.webgl_skip_reason(qapp)
    if reason:
        pytest.skip(reason)
    backend = Mol3DViewerBackend()
    assert _wait_until(qapp, lambda: backend._page_ready)

    theme.set_effective(DARK)
    assert _eventually(qapp, backend._page, "document.documentElement.getAttribute('data-look')", "dark")
    assert _eventually(qapp, backend._page, "backgroundColour", "#1e1e1e")

    theme.set_effective(LIGHT)
    assert _eventually(qapp, backend._page, "document.documentElement.getAttribute('data-look')", "light")
    assert _eventually(qapp, backend._page, "backgroundColour", "white")


def test_a_3d_page_built_while_dark_starts_dark(qapp):
    reason = conftest.webgl_skip_reason(qapp)
    if reason:
        pytest.skip(reason)
    theme.set_effective(DARK)
    backend = Mol3DViewerBackend()

    assert _wait_until(qapp, lambda: backend._page_ready)
    assert _eventually(qapp, backend._page, "backgroundColour", "#1e1e1e")
