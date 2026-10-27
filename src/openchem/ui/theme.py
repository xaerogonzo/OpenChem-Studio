"""Colours that depend on whether the window is light or dark, and how a widget keeps them current.

**A STYLESHEET WITH A COLOUR IN IT IS A CACHE OF THE LOOK IT WAS BUILT IN.** `color: #666666` is a
fine muted grey on a light window and 2.9:1 on a dark one, and a widget that wrote it at construction
keeps it when the person switches. So a colour that carries meaning is written through `style()`:

    theme.style(label, "color: #666666;")

The text is written for the LIGHT window, exactly as the code has always had it, and `style()`
resolves it for the look that is on screen and REMEMBERS the widget, so `set_effective()` rewrites it
when the look changes. In light the resolved text is the text given, byte for byte.

**WHAT IS MAPPED, AND WHAT IS NOT.** `_DARK_FOR_LIGHT` names each light literal that is TEXT on a
panel and the value that reads on a dark one, chosen for contrast (`tests/test_theme.py` holds every
value to 4.5:1 on the dark base colour) and kept apart by meaning: a muted note, a status colour and a
caution are different tokens that merely look alike in light. A literal that is not in the table is
left alone on purpose -- the colour-blind-safe series colours, element and plot colours, anything
whose hue is the data. `tests/test_theme.py` fails on a new direct `setStyleSheet` that is not either
routed here or listed, with its reason, so a colour cannot be added unreviewed.

Palette roles (`palette(mid)`, `palette(link)`, a painter's `palette().base()`) follow the application
palette by themselves and need none of this.
"""

from __future__ import annotations

import re
import weakref
from collections.abc import Callable

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from openchem.domain.appearance import EffectiveAppearance

#: Light literal -> the value for a dark window. Keys are lower-case six-digit; `_normal` folds the rest.
_DARK_FOR_LIGHT: dict[str, str] = {
    # Muted notes and captions: a hint, a caption, "Not run". Four strengths of grey in light.
    "#666666": "#a0a0a0",
    "#6e6e6e": "#a0a0a0",
    "#555555": "#b4b4b4",
    "#777777": "#9a9a9a",
    "#444444": "#c8c8c8",
    # A fault: it broke, or the input is invalid.
    "#c62828": "#ff7b7b",
    "#c82828": "#ff7b7b",
    "#c0392b": "#ff7b7b",
    # Checked, nothing flagged.
    "#2e7d32": "#66bb6a",
    "#1f6f3f": "#5fcf8a",
    # A caution: worked, but look.
    "#7a5c00": "#e3b341",
    "#8a6d00": "#e3b341",
    "#8a6d3b": "#e3b341",
    "#b45309": "#fbbf24",
    # The severity colours the structure checker uses as TEXT (Okabe-Ito hues, kept recognisable).
    "#0072b2": "#58b4ee",
    "#d55e00": "#ff8a3d",
}

#: A colour literal inside a stylesheet: three or six hex digits, and not the start of a longer run of letters or digits.
_HEX = re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?(?![0-9a-zA-Z])")

_effective = EffectiveAppearance.LIGHT

#: (id(widget), slot) -> (weak reference, what to run on it when the look changes). Keyed by id because a
#: QWidget is not reliably hashable by value; the callback drops the entry when the widget dies. A widget
#: has one entry per SLOT, so a label that has a stylesheet and also re-renders its text keeps both.
_registry: dict[tuple[int, str], tuple[weakref.ref, Callable[[QWidget], None]]] = {}


def _normal(literal: str) -> str:
    text = literal.lower()
    if len(text) == 4:
        text = "#" + "".join(ch * 2 for ch in text[1:])
    return text


def dark_values() -> dict[str, str]:
    """The mapping, for the tests that hold it to contrast and to the sweep."""
    return dict(_DARK_FOR_LIGHT)


def effective() -> EffectiveAppearance:
    return _effective


def colour(light_literal: str, look: EffectiveAppearance | None = None) -> str:
    """One colour for the look on screen (or `look`): the literal itself in light, or its dark value."""
    look = _effective if look is None else look
    if look is EffectiveAppearance.LIGHT:
        return light_literal
    return _DARK_FOR_LIGHT.get(_normal(light_literal), light_literal)


def resolve(stylesheet: str, look: EffectiveAppearance | None = None) -> str:
    """`stylesheet`, written for a light window, as it should read in `look` (default: the one on screen)."""
    look = _effective if look is None else look
    if look is EffectiveAppearance.LIGHT:
        return stylesheet
    return _HEX.sub(lambda match: _DARK_FOR_LIGHT.get(_normal(match.group(0)), match.group(0)), stylesheet)


def follow(
    widget: QWidget, apply: Callable[[QWidget], None], *, immediately: bool = True, slot: str = "follow"
) -> None:
    """Run `apply(widget)` now and again each time the look changes, for as long as `widget` lives.

    For whatever cannot be a stylesheet: rich text with a colour in it, a cached `QColor`, a painted
    chart that has to be redrawn. One entry per widget and `slot`; following again replaces the earlier one.
    `apply` must not hold the widget itself (it is handed it), or the widget could never be freed.
    """
    key = (id(widget), slot)
    _registry[key] = (weakref.ref(widget, lambda _ref, key=key: _registry.pop(key, None)), apply)
    if immediately:
        apply(widget)


def style(widget: QWidget, light_stylesheet: str) -> None:
    """Give `widget` this stylesheet, resolved now and again whenever the look changes."""
    if not light_stylesheet:
        _registry.pop((id(widget), "style"), None)
        widget.setStyleSheet("")
        return
    follow(widget, lambda w: w.setStyleSheet(resolve(light_stylesheet)), slot="style")


def repolish_styled_widgets() -> None:
    """Make every widget that carries a stylesheet of its own take the application palette again.

    **A WIDGET WITH A STYLESHEET KEEPS THE PALETTE IT WAS POLISHED WITH.** Qt's stylesheet style resolves a
    widget's colours once, from the application palette of that moment, and a later palette change does not
    reach it: measured on the real window, a collapsible section's header (`QToolButton { border: none; }`)
    stayed black on a dark window and the rail's buttons stayed light grey with white icons, both only after a
    LIVE switch. Setting the same stylesheet again makes the style resolve it afresh. Widgets with no
    stylesheet follow the palette on their own and are not touched.
    """
    if QApplication.instance() is None:
        return
    for widget in QApplication.allWidgets():
        sheet = widget.styleSheet()
        if sheet:
            widget.setStyleSheet(sheet)


def set_effective(look: EffectiveAppearance) -> None:
    """Record the look that is on screen and tell everything that follows it.

    A call that names the look already in force does nothing: every stylesheet in the process is set
    again on a real switch (see `repolish_styled_widgets`), which costs about 20 ms per live window, so
    a repeat that changed nothing must not pay it. Measured: 60 leftover windows made one test file
    that resets the look around every test take 214 s instead of 4.7 s, and a CI shard timed out on it.
    """
    global _effective
    if look is _effective:
        return
    _effective = look
    repolish_styled_widgets()
    for key, (ref, apply) in list(_registry.items()):
        widget = ref()
        if widget is None:
            _registry.pop(key, None)
            continue
        try:
            apply(widget)
        except RuntimeError:
            # Its C++ object went before the Python wrapper did. One dead follower must not stop the
            # switch for every follower after it.
            _registry.pop(key, None)


def registered_count() -> int:
    """How many live widgets are kept current; a test reads it to see a widget leave."""
    return sum(1 for ref, _ in _registry.values() if ref() is not None)


#: The colour a painted chart's ink must read against in a dark window: the application's text-edit
#: background, which is the lighter of the two dark surfaces, so passing here passes on both.
_DARK_SURFACE = QColor("#2d2d2d")
#: WCAG's floor for text, which a plotted line that carries a legend is held to as well.
MIN_CONTRAST = 4.5


def _relative_luminance(colour: QColor) -> float:
    def channel(value: float) -> float:
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(colour.redF()) + 0.7152 * channel(colour.greenF()) + 0.0722 * channel(colour.blueF())
    )


def contrast(first: QColor | str, second: QColor | str) -> float:
    """WCAG contrast ratio between two colours, 1 (none) to 21 (black on white)."""
    high, low = sorted((_relative_luminance(QColor(first)), _relative_luminance(QColor(second))), reverse=True)
    return (high + 0.05) / (low + 0.05)


def ink(colour: QColor | str, look: EffectiveAppearance | None = None) -> QColor:
    """A painted line or glyph colour for the look on screen: itself in light, lifted in dark if it would sink.

    For what a widget DRAWS (a spectrum's sticks, a trace), where a stylesheet is not involved. The hue is
    kept and only the lightness rises, in small steps, until it reads against a dark surface; a colour that
    already does is returned as it was, so a palette that was readable keeps its look.
    """
    look = _effective if look is None else look
    result = QColor(colour)
    if look is EffectiveAppearance.LIGHT:
        return result
    hue, saturation, lightness, alpha = result.hslHueF(), result.hslSaturationF(), result.lightnessF(), result.alphaF()
    while contrast(result, _DARK_SURFACE) < MIN_CONTRAST and lightness < 1.0:
        lightness = min(1.0, lightness + 0.02)
        result = QColor.fromHslF(max(hue, 0.0), saturation, lightness, alpha)
    return result


def repaint_on_change(widget: QWidget) -> None:
    """Have a custom-painted widget redraw itself when the look changes (its `paintEvent` reads `ink()`)."""
    follow(widget, lambda w: w.update(), immediately=False, slot="repaint")


def panel_fill(alpha: int = 255) -> QColor:
    """The fill of a box drawn over a plot (a legend key): white in light, the dark surface in dark."""
    base = QColor("#ffffff") if _effective is EffectiveAppearance.LIGHT else QColor(_DARK_SURFACE)
    base.setAlpha(alpha)
    return base


def faint(colour: QColor | str, look: EffectiveAppearance | None = None) -> QColor:
    """A grid line or rule drawn in a very light grey for a light window: the same weight, but dark, in a dark one."""
    look = _effective if look is None else look
    result = QColor(colour)
    if look is EffectiveAppearance.LIGHT:
        return result
    return QColor.fromHslF(0.0, 0.0, 0.26, result.alphaF())


def paper(widget: QWidget) -> None:
    """Show `widget` on white paper in a dark window, and exactly as it was in a light one.

    For a view that hosts a CHEMICAL DRAWING in a vector file (the Lewis diagram, an electron-density
    heatmap): their ink is chosen for a white page (black bonds, the atom palette's blues and reds) and is
    often drawn with no background of its own, so on a dark panel it would vanish. The drawing area of the 2D
    editor is white in a dark window for the same reason, and a drawing that already carries its own white
    rectangle (RDKit's) is unaffected. Colours that mean something are never recoloured to fit a theme.
    """

    def apply(target: QWidget) -> None:
        dark = _effective is EffectiveAppearance.DARK
        target.setAutoFillBackground(dark)
        if dark:
            palette = QPalette(target.palette())
            palette.setColor(QPalette.ColorRole.Window, QColor("#ffffff"))
            target.setPalette(palette)
        else:
            target.setPalette(QPalette())

    follow(widget, apply, slot="paper")
