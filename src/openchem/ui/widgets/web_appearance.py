"""What the three embedded web pages are told about the look, and the rules for telling them.

The pages (the 2D editor, the 3D viewer, the macromolecule viewer) are documents of their own, so
neither the application palette nor the operating system's preference reaches them: the application can
be forced Dark while Windows is Light. Each is TOLD the look, as the word `light` or `dark`, by a short
script.

**THE RULES, AND WHY THERE IS NO QUEUE.** `theme.effective()` is the one latest value. A page that is
not ready yet is told it once, when it becomes ready, and that is the value at that moment -- so a
switch before the page loads, and three switches while it loads, all settle on the final one without
anything being replayed. A page that is ready is told on every change. The script touches the page's
own surfaces only: it never reloads, and it never touches the structure, the camera or the layers.

Pure and Qt-free apart from the colour the page is painted before its first frame, so the rules and
the scripts can be tested without a browser.
"""

from __future__ import annotations

import json
import weakref
from collections.abc import Callable

from PySide6.QtGui import QColor
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import QWidget
from shiboken6 import isValid

from openchem.domain.appearance import EffectiveAppearance
from openchem.ui import theme

#: The background Chromium paints before the page's own first frame, so a dark window never flashes white.
_PAGE_BACKGROUND = {EffectiveAppearance.LIGHT: "#ffffff", EffectiveAppearance.DARK: "#1e1e1e"}


def word(look: EffectiveAppearance) -> str:
    """`light` or `dark`: what a page is told."""
    return "dark" if look is EffectiveAppearance.DARK else "light"


def page_background(look: EffectiveAppearance) -> QColor:
    return QColor(_PAGE_BACKGROUND[look])


def call_script(api: str, look: EffectiveAppearance) -> str:
    """`window.<api>.setAppearance('dark')`, guarded: a page that has not defined it yet is not an error."""
    return (
        f"if (window.{api} && window.{api}.setAppearance) "
        f"window.{api}.setAppearance({json.dumps(word(look))});"
    )


# --- the 2D editor ------------------------------------------------------------------------------

#: The editor page has no script of ours, so the look is a stylesheet it is given. LIGHT is no stylesheet at
#: all: the editor the application has always shown.
#:
#: DARK darkens the editor's CHROME (the four toolbars) and leaves the DRAWING AREA UNTOUCHED, white, with
#: nothing between it and the page. That is the whole point: atom colours (nitrogen blue, oxygen red), bond
#: styles, selection and hover feedback are drawn by the editor in the colours chemists read, and must not be
#: recoloured by a theme. Each chrome container is inverted on its own (`invert(0.88)` takes the editor's
#: white to the application's dark surface, #1f1f1f; `hue-rotate(180deg)` brings the coloured element
#: buttons back to their own hues, approximately, which is acceptable for a button's label and was NOT for a
#: drawing).
#:
#: **THE WHOLE-PAGE INVERSION WAS TRIED AND FAILED, MEASURED.** Inverting `#root` and inverting the drawing
#: back leaves the canvas colours changed: nitrogen (48, 139, 249) came back as (97, 120, 249) and oxygen
#: (255, 13, 13) as (255, 103, 103), because a hue rotation is clamped per channel and does not undo. It is
#: not offered; `docs/APPEARANCE_DESIGN.md` has the numbers. The selectors name the editor's own CSS-module
#: classes by their stable prefix (the build appends a hash), so a rebuilt editor that renames one simply
#: leaves that toolbar light -- and `tests/test_web_appearance_live.py` fails, so it cannot go unnoticed.
KETCHER_CHROME_SELECTORS = (
    '[class*="App-module_top"]',
    '[class*="LeftToolbar-module_root"]',
    '[class*="RightToolbar-module_root"]',
    '[class*="BottomToolbar-module_root"]',
)
#: The dark stylesheet: the page background, then the four toolbars inverted. Light is the empty string.
KETCHER_DARK_CSS = (
    "html, body, #root { background: #1f1f1f; }"
    + ", ".join(KETCHER_CHROME_SELECTORS)
    + " { filter: invert(0.88) hue-rotate(180deg); }"
)

#: The one `<style>` element the editor page is given; created on the first dark, emptied on light.
_KETCHER_STYLE_ID = "openchem-appearance"


def ketcher_script(look: EffectiveAppearance) -> str:
    """Create or update the one `<style id="openchem-appearance">` element; empty for light."""
    css = KETCHER_DARK_CSS if look is EffectiveAppearance.DARK else ""
    return (
        "(function (css) {"
        f"var id = {json.dumps(_KETCHER_STYLE_ID)};"
        "var style = document.getElementById(id);"
        "if (!style) { style = document.createElement('style'); style.id = id; document.head.appendChild(style); }"
        "style.textContent = css;"
        f"document.documentElement.style.colorScheme = {json.dumps(word(look))};"
        f"}})({json.dumps(css)});"
    )


class PageLook:
    """Keeps one web page told the look, by the rules in the module docstring.

    Owned by the backend that owns the page. It follows the look through `theme.follow` on the view and
    holds the backend's page only; the registry holds this object weakly, so neither outlives the other.
    """

    def __init__(self, view: QWidget, page: QWebEnginePage, script_for: Callable[[EffectiveAppearance], str]) -> None:
        self._page = page
        self._script_for = script_for
        self._ready = False
        page.setBackgroundColor(page_background(theme.effective()))
        reference = weakref.ref(self)
        theme.follow(
            view,
            lambda _view, reference=reference: (own := reference()) and own._changed(),
            immediately=False,
            slot="page-look",
        )

    def ready(self) -> None:
        """The page can run scripts: tell it the look as it is NOW (never an earlier one)."""
        self._ready = True
        self._page.runJavaScript(self._script_for(theme.effective()))

    def not_ready(self) -> None:
        """The page is going away or reloading; the next `ready()` tells it again."""
        self._ready = False

    def _changed(self) -> None:
        if not isValid(self._page):
            # The view outlived its page (the wrapper is still referenced, the C++ object is gone).
            return
        look = theme.effective()
        self._page.setBackgroundColor(page_background(look))
        if self._ready:
            self._page.runJavaScript(self._script_for(look))
