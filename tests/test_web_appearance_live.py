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
from openchem.ui.widgets.web_appearance import KETCHER_CHROME_SELECTORS, KETCHER_DARK_CSS

LIGHT = EffectiveAppearance.LIGHT
DARK = EffectiveAppearance.DARK
_TIMEOUT = 60


@pytest.fixture(autouse=True)
def _back_to_light():
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
