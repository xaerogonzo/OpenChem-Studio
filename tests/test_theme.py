"""`ui.theme`: the dark values, how a widget keeps its colours current, and the guard that nobody adds one unreviewed.

The mapping is a table of judgements, so the tests hold it to what it promises (contrast, identity in light,
no residue after repeated switches) rather than to its own contents.
"""

from __future__ import annotations

import gc
import re
from pathlib import Path

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel

from openchem.domain.appearance import EffectiveAppearance
from openchem.ui import theme

#: The real stylesheet pass, taken before `cheap_repolish` replaces it for a test.
_REAL_REPOLISH = theme.repolish_styled_widgets
LIGHT = EffectiveAppearance.LIGHT
DARK = EffectiveAppearance.DARK

_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _back_to_light(cheap_repolish):
    """The look is module state, so no test may leave the suite dark."""
    theme.set_effective(LIGHT)
    yield
    theme.set_effective(LIGHT)


# --- the table --------------------------------------------------------------------------------


@pytest.mark.parametrize(("light", "dark"), sorted(theme.dark_values().items()))
def test_every_dark_value_reads_on_the_dark_surface(light, dark):
    """4.5:1 against the lighter dark surface, which is the harder of the two."""
    assert theme.contrast(dark, "#2d2d2d") >= theme.MIN_CONTRAST, (light, dark)


def test_a_literal_is_never_mapped_to_itself():
    """An entry that changes nothing is a decision somebody forgot to make."""
    assert all(light != dark for light, dark in theme.dark_values().items())


def test_every_key_is_a_normal_six_digit_lowercase_literal():
    assert all(re.fullmatch(r"#[0-9a-f]{6}", key) for key in theme.dark_values())


# --- resolving --------------------------------------------------------------------------------


@pytest.mark.parametrize("sheet", ["color: #666666;", "color: #666; font-weight: bold;", "", "font-weight: bold;"])
def test_light_text_is_returned_byte_for_byte(sheet):
    assert theme.resolve(sheet, LIGHT) == sheet


def test_dark_replaces_a_mapped_literal():
    assert theme.resolve("color: #666666;", DARK) == f"color: {theme.dark_values()['#666666']};"


def test_a_three_digit_literal_and_upper_case_are_folded():
    assert theme.resolve("color: #666;", DARK) == theme.resolve("color: #666666;", DARK)
    assert theme.resolve("color: #C62828;", DARK) == theme.resolve("color: #c62828;", DARK)


def test_a_literal_the_table_does_not_know_is_left_alone():
    """Hue that carries meaning, or a colour that already reads: not the table's to change."""
    sheet = "border: 1px solid #123456; color: #888;"
    assert theme.resolve(sheet, DARK) == sheet


def test_a_longer_hex_run_is_not_cut_short():
    """`#6666660` is not `#666666` followed by a zero."""
    assert theme.resolve("color: #6666660;", DARK) == "color: #6666660;"


def test_colour_follows_the_look_on_screen():
    assert theme.colour("#666666") == "#666666"
    theme.set_effective(DARK)
    assert theme.colour("#666666") == theme.dark_values()["#666666"]


# --- keeping a widget current -----------------------------------------------------------------


def test_a_styled_widget_is_rewritten_when_the_look_changes(qapp):
    label = QLabel("note")
    theme.style(label, "color: #666666;")
    assert label.styleSheet() == "color: #666666;"

    theme.set_effective(DARK)
    assert label.styleSheet() == f"color: {theme.dark_values()['#666666']};"

    theme.set_effective(LIGHT)
    assert label.styleSheet() == "color: #666666;"


def test_a_widget_built_in_the_dark_starts_dark(qapp):
    theme.set_effective(DARK)
    label = QLabel("note")

    theme.style(label, "color: #666666;")

    assert label.styleSheet() == f"color: {theme.dark_values()['#666666']};"


def test_naming_the_look_already_in_force_does_nothing(qapp):
    """Resetting to the look on screen is the common case in a test fixture, and it must not pay for a switch."""
    heard = []
    label = QLabel("x")
    theme.follow(label, lambda _w: heard.append(theme.effective()), immediately=False, slot="repeat")

    theme.set_effective(LIGHT)
    theme.set_effective(DARK)
    theme.set_effective(DARK)

    assert heard == [DARK]


def test_a_follower_whose_object_is_gone_does_not_stop_the_switch(qapp):
    """A view can outlive the C++ page it followed; the others must still hear about the change."""
    heard = []
    dead, alive = QLabel("dead"), QLabel("alive")

    def explode(_widget):
        raise RuntimeError("Internal C++ object (Page) already deleted.")

    theme.follow(dead, explode, immediately=False, slot="dead-page")
    theme.follow(alive, lambda _w: heard.append(theme.effective()), immediately=False, slot="alive")

    theme.set_effective(DARK)

    assert heard == [DARK]
    assert theme.registered_count() >= 1


def test_repeated_switches_leave_no_residue(qapp):
    label = QLabel("note")
    theme.style(label, "color: #c62828; font-weight: bold;")

    for _ in range(5):
        theme.set_effective(DARK)
        theme.set_effective(LIGHT)

    assert label.styleSheet() == "color: #c62828; font-weight: bold;"


def test_styling_again_replaces_the_earlier_stylesheet(qapp):
    label = QLabel("note")
    theme.style(label, "color: #666666;")
    theme.style(label, "color: #2e7d32;")

    theme.set_effective(DARK)

    assert label.styleSheet() == f"color: {theme.dark_values()['#2e7d32']};"


def test_an_empty_stylesheet_clears_and_forgets(qapp):
    label = QLabel("note")
    theme.style(label, "color: #666666;")

    theme.style(label, "")
    theme.set_effective(DARK)

    assert label.styleSheet() == ""


def test_a_widget_that_dies_is_forgotten(qapp):
    before = theme.registered_count()
    label = QLabel("note")
    theme.style(label, "color: #666666;")
    assert theme.registered_count() == before + 1

    del label
    gc.collect()

    assert theme.registered_count() == before


def test_follow_runs_now_and_on_every_change_and_per_slot(qapp):
    label = QLabel("note")
    seen = []
    theme.follow(label, lambda w: seen.append(("a", theme.effective())), slot="a")
    theme.follow(label, lambda w: seen.append(("b", theme.effective())), slot="b", immediately=False)
    theme.style(label, "color: #666666;")  # a third slot on the same widget

    theme.set_effective(DARK)

    assert ("a", LIGHT) in seen and ("a", DARK) in seen and ("b", DARK) in seen
    assert ("b", LIGHT) not in seen
    assert label.styleSheet() != "color: #666666;"


# --- painted colours --------------------------------------------------------------------------


def test_ink_is_the_colour_itself_in_light():
    assert theme.ink(QColor(30, 100, 200)).getRgb() == QColor(30, 100, 200).getRgb()


@pytest.mark.parametrize("rgb", [(0, 0, 0), (30, 100, 200), (60, 60, 60), (49, 91, 173), (120, 120, 120)])
def test_ink_lifts_a_colour_that_would_sink_on_dark(rgb):
    lifted = theme.ink(QColor(*rgb), DARK)
    assert theme.contrast(lifted, "#2d2d2d") >= theme.MIN_CONTRAST


def test_ink_leaves_a_colour_that_already_reads():
    already = QColor("#f5f5f5")
    assert theme.ink(already, DARK).getRgb() == already.getRgb()


def test_ink_keeps_the_hue_of_what_it_lifts():
    blue = QColor(30, 100, 200)
    assert abs(theme.ink(blue, DARK).hslHue() - blue.hslHue()) <= 2


def test_ink_keeps_transparency():
    assert theme.ink(QColor(0, 0, 0, 90), DARK).alpha() == 90


def test_faint_is_light_in_light_and_dark_in_dark():
    assert theme.faint(QColor(226, 226, 226), LIGHT).getRgb() == QColor(226, 226, 226).getRgb()
    assert theme.faint(QColor(226, 226, 226), DARK).lightnessF() < 0.4


def test_panel_fill_follows_the_look():
    assert theme.panel_fill(200).getRgb() == (255, 255, 255, 200)
    theme.set_effective(DARK)
    assert theme.panel_fill(200).lightnessF() < 0.3
    assert theme.panel_fill(200).alpha() == 200


# --- the guard: no colour reaches a stylesheet unreviewed ------------------------------------

#: Direct `setStyleSheet` calls that carry no mapped colour, kept because they are not about the look:
#: weight, size, spacing, a palette role (which follows the application palette by itself), or a swatch whose
#: fill IS the data. Anything new that is not here must go through `theme.style`.
_DIRECT_ALLOWED = {
    # (file, the exact argument text)
    ("ui/dialogs/external_tools_pages.py", '"font-family: monospace;"'),
    ("ui/dialogs/lewis_pairing_dialog.py", '"font-weight: bold;"'),
    ("ui/dialogs/particle_dialog.py", '"font-weight: bold;"'),
    ("ui/panels/quantum_chemistry_panel.py", '"font-weight: bold;"'),
    ("ui/widgets/collapsible_section.py", '"QToolButton { border: none; font-weight: bold; }"'),
    ("ui/widgets/collapsible_section.py", "self.styleSheet()"),
    ("ui/widgets/fact_view.py", '"color: palette(link); padding: 0 4px; text-align: right;"'),
    ("ui/widgets/fact_view.py", "sheet"),
    ("ui/widgets/fact_view.py", '"font-weight: bold;"'),
    ("ui/widgets/fact_view.py", '"padding: 2px 0;"'),
    ("ui/widgets/panel_rail.py", '"font-weight: bold; padding: 4px 6px 0 6px;"'),
    ("ui/widgets/panel_rail.py", '"padding: 0 6px 4px 6px; color: palette(mid);"'),
    ("ui/widgets/results_view.py", '"font-weight: bold;"'),
    ("ui/widgets/substance_card.py", '"font-size: 13px; font-weight: bold;"'),
    ("ui/widgets/tautomer_overlay_controls.py", '"font-weight: bold;"'),
}

#: Calls whose argument is a computed or multi-part string, listed by file and a distinctive fragment.
_DIRECT_ALLOWED_FRAGMENTS = {
    # An element cell's fill is the periodic-table category colour with fixed dark text on it: data, on a pastel.
    ("ui/dialogs/periodic_table_dialog.py", "QToolButton {{ background: {fill}"),
    # The rail's own buttons: layout only (the icon follows the palette through `theme.follow`).
    ("ui/widgets/panel_rail.py", "QPushButton { text-align: left"),
}

_CALL = re.compile(r"(?P<w>[A-Za-z_][\w.\[\]]*)\.setStyleSheet\(")


def _argument(text: str, start: int) -> str:
    depth, index, quote = 1, start, None
    while index < len(text):
        char = text[index]
        if quote:
            if char == "\\":
                index += 1
            elif char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start:index].strip()
        index += 1
    raise AssertionError("unbalanced setStyleSheet call")


def _direct_calls():
    for base in (_ROOT / "src" / "openchem", _ROOT / "plugins"):
        for path in sorted(base.rglob("*.py")):
            if path.name == "theme.py":
                continue
            text = path.read_text(encoding="utf-8")
            for match in _CALL.finditer(text):
                yield path.relative_to(base) if base.name == "openchem" else Path("plugins") / path.relative_to(base), (
                    _argument(text, match.end())
                ), text.count("\n", 0, match.start()) + 1


def test_the_guard_actually_finds_the_calls_it_guards():
    """An empty scan passes every check; the codebase has dozens of these calls, so finding few is a broken scan."""
    assert len(list(_direct_calls())) >= 15


def test_no_stylesheet_is_set_around_the_theme_without_a_reason():
    unreviewed = []
    for path, argument, line in _direct_calls():
        key = (path.as_posix(), argument)
        if key in _DIRECT_ALLOWED:
            continue
        if any(path.as_posix() == file and fragment in argument for file, fragment in _DIRECT_ALLOWED_FRAGMENTS):
            continue
        # The two swatch/background calls inside `theme.follow` lambdas are routed through the theme already.
        if "theme.ink(" in argument:
            continue
        unreviewed.append(f"{path.as_posix()}:{line}: setStyleSheet({argument[:80]})")
    assert not unreviewed, (
        "A stylesheet was set directly. Route it through `theme.style(widget, light_stylesheet)` so it follows "
        "the look, or add it to `_DIRECT_ALLOWED` with the reason it carries no colour that depends on it:\n"
        + "\n".join(unreviewed)
    )


def test_no_direct_call_carries_a_colour_the_table_would_change():
    """The allow-list must not become a way round the table."""
    mapped = set(theme.dark_values())
    hexes = re.compile(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?(?![0-9a-zA-Z])")
    offenders = [
        f"{path.as_posix()}:{line}"
        for path, argument, line in _direct_calls()
        if "theme.ink(" not in argument and any(theme._normal(h) in mapped for h in hexes.findall(argument))
    ]
    assert not offenders, offenders


# --- paper, and the refresh of widgets that carry a stylesheet ---------------------------------


def test_paper_is_nothing_in_light_and_white_in_dark(qapp):
    from PySide6.QtGui import QPalette
    from PySide6.QtSvgWidgets import QSvgWidget

    view = QSvgWidget()
    theme.paper(view)
    assert not view.autoFillBackground()

    theme.set_effective(DARK)
    assert view.autoFillBackground()
    assert view.palette().color(QPalette.ColorRole.Window).name() == "#ffffff"

    theme.set_effective(LIGHT)
    assert not view.autoFillBackground()


def test_paper_leaves_no_residue_over_repeated_switches(qapp):
    from PySide6.QtGui import QPalette
    from PySide6.QtSvgWidgets import QSvgWidget

    view = QSvgWidget()
    original = view.palette().color(QPalette.ColorRole.Window).name()
    theme.paper(view)

    for _ in range(4):
        theme.set_effective(DARK)
        theme.set_effective(LIGHT)

    assert view.palette().color(QPalette.ColorRole.Window).name() == original


def test_widgets_with_a_stylesheet_are_set_again_and_the_rest_are_left(qapp):
    """A stylesheet-styled widget keeps the palette it was polished with until its stylesheet is set again."""
    from PySide6.QtWidgets import QToolButton

    class Counting(QToolButton):
        sets = 0

        def setStyleSheet(self, sheet):  # noqa: N802 - Qt's own casing
            type(self).sets += 1
            super().setStyleSheet(sheet)

    styled, plain = Counting(), Counting()
    styled.setStyleSheet("QToolButton { border: none; }")
    Counting.sets = 0

    _REAL_REPOLISH()

    assert Counting.sets == 1
    assert styled.styleSheet() == "QToolButton { border: none; }"
    assert plain.styleSheet() == ""
