"""What the web pages are told about the look: the scripts, and the rules for sending them.

The scripts and rules are tested without a browser. The live pages are covered by the driven script
`benchmarks/visual/appearance.json`, and `tests/test_web_appearance_live.py` for the one that needs no GPU.
"""

from __future__ import annotations

import json

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget

from openchem.domain.appearance import EffectiveAppearance
from openchem.ui import theme
from openchem.ui.widgets import web_appearance
from openchem.ui.widgets.web_appearance import (
    KETCHER_CHROME_SELECTORS,
    KETCHER_DARK_CSS,
    PageLook,
    call_script,
    ketcher_script,
    page_background,
    word,
)

LIGHT = EffectiveAppearance.LIGHT
DARK = EffectiveAppearance.DARK


@pytest.fixture(autouse=True)
def _back_to_light():
    theme.set_effective(LIGHT)
    yield
    theme.set_effective(LIGHT)


class _FakePage:
    """The slice of `QWebEnginePage` a `PageLook` uses, recording what it is asked."""

    def __init__(self) -> None:
        self.scripts: list[str] = []
        self.backgrounds: list[str] = []

    def runJavaScript(self, script: str) -> None:  # noqa: N802 - Qt's own casing
        self.scripts.append(script)

    def setBackgroundColor(self, colour: QColor) -> None:  # noqa: N802
        self.backgrounds.append(colour.name())


def test_a_page_is_told_a_word_never_system():
    assert word(LIGHT) == "light"
    assert word(DARK) == "dark"


def test_the_call_names_the_api_and_the_look_and_tolerates_a_page_without_it():
    script = call_script("openchemViewer", DARK)
    assert script == (
        'if (window.openchemViewer && window.openchemViewer.setAppearance) '
        'window.openchemViewer.setAppearance("dark");'
    )


def test_the_editor_script_is_a_stylesheet_that_light_empties():
    dark, light = ketcher_script(DARK), ketcher_script(LIGHT)

    assert json.dumps(KETCHER_DARK_CSS) in dark
    assert "openchem-appearance" in dark and "openchem-appearance" in light
    assert json.dumps(KETCHER_DARK_CSS) not in light
    assert '""' in light.split("})(")[-1]


def test_the_drawing_area_is_never_named_by_the_dark_stylesheet():
    """Atom colours, bonds, selection and hover are the editor's own, in the colours chemists read.

    Only the four toolbars are filtered; nothing that contains or is contained by the canvas is.
    """
    assert len(KETCHER_CHROME_SELECTORS) == 4
    for selector in KETCHER_CHROME_SELECTORS:
        assert "canvas" not in selector.lower()
        assert "StructEditor" not in selector
    css_rules = KETCHER_DARK_CSS.split("}")
    filtered = [rule for rule in css_rules if "filter" in rule]
    assert len(filtered) == 1
    assert all(selector in filtered[0] for selector in KETCHER_CHROME_SELECTORS)


def test_only_the_toolbars_are_filtered_and_the_editor_surround_is_a_plain_background():
    surround = KETCHER_DARK_CSS.split("}")[0]
    assert "filter" not in surround and "background" in surround


def test_the_page_behind_a_dark_window_is_not_white():
    assert page_background(LIGHT).lightnessF() > 0.9
    assert page_background(DARK).lightnessF() < 0.2


# --- the rules --------------------------------------------------------------------------------


def _look(qapp):
    page = _FakePage()
    view = QWidget()
    look = PageLook(view, page, lambda value: f"look:{word(value)}")
    return view, page, look


def test_a_page_that_is_not_ready_is_sent_nothing(qapp):
    view, page, look = _look(qapp)

    theme.set_effective(DARK)

    assert page.scripts == []


def test_it_is_painted_before_its_first_frame_even_when_not_ready(qapp):
    view, page, look = _look(qapp)

    theme.set_effective(DARK)

    assert page.backgrounds[-1] == page_background(DARK).name()


def test_a_page_that_becomes_ready_is_told_the_look_as_it_is_then(qapp):
    """Three switches while it loads, one send: the last."""
    view, page, look = _look(qapp)

    theme.set_effective(DARK)
    theme.set_effective(LIGHT)
    theme.set_effective(DARK)
    look.ready()

    assert page.scripts == ["look:dark"]


def test_a_ready_page_is_told_every_change(qapp):
    view, page, look = _look(qapp)
    look.ready()
    page.scripts.clear()

    theme.set_effective(DARK)
    theme.set_effective(LIGHT)

    assert page.scripts == ["look:dark", "look:light"]


def test_a_page_built_while_dark_is_told_dark_when_ready(qapp):
    theme.set_effective(DARK)
    view, page, look = _look(qapp)

    look.ready()

    assert page.backgrounds[0] == page_background(DARK).name()
    assert page.scripts == ["look:dark"]


def test_a_page_that_goes_away_is_sent_nothing_until_ready_again(qapp):
    view, page, look = _look(qapp)
    look.ready()
    look.not_ready()
    page.scripts.clear()

    theme.set_effective(DARK)
    assert page.scripts == []

    look.ready()
    assert page.scripts == ["look:dark"]


def test_a_dead_view_stops_being_followed(qapp):
    import gc

    before = theme.registered_count()
    view, page, look = _look(qapp)
    assert theme.registered_count() == before + 1

    del view, look
    gc.collect()

    assert theme.registered_count() == before


def test_module_has_no_unreviewed_scripts():
    """Every script this module can send is covered above; a new one needs a test."""
    public = {name for name in dir(web_appearance) if name.endswith("_script")}
    assert public == {"call_script", "ketcher_script"}
