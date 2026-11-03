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
#: DARK darkens the editor's CHROME (the four toolbars) and its DRAWING AREA, but recolours the drawing by
#: ONE rule only: ink the editor draws in black becomes the dark surface's light ink. Atom colours (nitrogen
#: blue, oxygen red), selection and hover feedback are drawn by the editor in the colours chemists read and
#: are never touched, because no rule names them and nothing is filtered. Each chrome container is inverted
#: on its own (`invert(0.88)` takes the editor's white to the application's dark surface, #1f1f1f;
#: `hue-rotate(180deg)` brings the coloured element buttons back to their own hues, approximately, which is
#: acceptable for a button's label and was NOT for a drawing -- hence the drawing is not filtered).
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
#: The editor's modal dialogs (Atom Properties, Bond Properties, Settings, the periodic table and the rest), which
#: are one `<dialog>` element each and exist only while one is open, so unlike a toolbar they are not counted on a
#: page at rest. They are filtered exactly as a toolbar is: a dialog is chrome (forms, buttons, labels), it was a
#: white box in a dark window, and it never contains the drawing. Measured on the live page: every one carries
#: `Dialog-module_dialog` and sits in `Modal-module_modalOverlay`, a sibling of the editor, not inside it.
KETCHER_DIALOG_SELECTORS = ('dialog[class*="Dialog-module_dialog"]',)
#: The drawing's own container: the one element whose subtree is the structure's SVG.
KETCHER_CANVAS = '[class*="StructEditor-module_canvas"]'
#: What the drawing's INK is, as the editor writes it: bonds, carbon and hydrogen labels, charges and
#: stereo marks carry the attribute value black (measured on the live page: `#000000` on 27 elements of a
#: six-atom drawing, never `#333` or a toolbar colour), while every element colour is its own value
#: (nitrogen `#304ff7`, oxygen `#ff0d0d`, chlorine `#1fd01f`). So a rule on the BLACK values alone turns the
#: ink light and cannot reach an atom colour, a selection or a hover, which is the thing the rejected
#: filter could not do.
_KETCHER_BLACKS = ("#000000", "#000", "black")
#: The ink as the dark surface shows it: the editor's own near-white.
_KETCHER_LIGHT_INK = "#e8e8e8"
#: The two rules that turn the drawing's black ink light, inside the canvas container and nowhere else.
KETCHER_INK_CSS = (
    ", ".join(f'{KETCHER_CANVAS} svg [stroke="{black}"]' for black in _KETCHER_BLACKS)
    + f" {{ stroke: {_KETCHER_LIGHT_INK} !important; }}"
    + ", ".join(f'{KETCHER_CANVAS} svg [fill="{black}"]' for black in _KETCHER_BLACKS)
    + f" {{ fill: {_KETCHER_LIGHT_INK} !important; }}"
)
#: The dark stylesheet: the page and the editor's own surface dark, the four toolbars inverted, and the
#: drawing's black ink light. Light is the empty string.
KETCHER_DARK_CSS = (
    "html, body, #root, .Ketcher-root { background: #1f1f1f; }"
    + ", ".join(KETCHER_CHROME_SELECTORS + KETCHER_DIALOG_SELECTORS)
    + " { filter: invert(0.88) hue-rotate(180deg); }"
    + KETCHER_INK_CSS
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
