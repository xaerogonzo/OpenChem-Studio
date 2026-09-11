"""A result's picture can be taken away from wherever it is being read.

Before this, exporting a drawing existed in exactly ONE dialog -- Lewis --
so every other picture the application draws was read-only. The charts and
depictions in the results reader had none, which is a dead end of the same
kind as a summary with no way back to the result.

**THE REFUSALS ARE THE POINT, AND THEY ARE ASSERTED BESIDE THE EXPORTS.**
"It exported" is satisfied by a function that writes a blank file, and a
blank file is worse than an error because it opens and looks like the
answer.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QMenu, QWidget

from openchem.ui.picture_export import (
    add_picture_actions,
    copy_picture,
    file_stem,
    is_blank,
    save_picture,
    vector_source,
)

_ETHANOL = "\n  Mrv2014 01010000002D\n\n  3  2  0  0  0  0            999 V2000\n    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n    1.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n    2.0000    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\n  1  2  1  0  0  0  0\n  2  3  1  0  0  0  0\nM  END\n"

_METHANOL = "\n  Mrv2014 01010000002D\n\n  2  1  0  0  0  0            999 V2000\n    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n    1.0000    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\n  1  2  1  0  0  0  0\nM  END\n"

_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
    '<rect width="10" height="10" fill="red"/></svg>'
)


class _Painted(QWidget):
    """An ordinary in-process widget that draws something."""

    def paintEvent(self, event):  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("white"))
        painter.fillRect(0, 0, self.width() // 2, self.height(), QColor("navy"))
        painter.end()


class _Vector(_Painted):
    def __init__(self, svg: str = _SVG, parent=None) -> None:
        super().__init__(parent)
        self._svg = svg

    def rendered_svg(self) -> str:
        return self._svg


class _Broken(QWidget):
    def rendered_svg(self) -> str:
        raise RuntimeError("the renderer fell over")


def _shown(qapp, widget: QWidget) -> QWidget:
    widget.resize(80, 40)
    widget.show()
    qapp.processEvents()
    return widget


# --- what a widget can produce, asked of the widget ----------------------


def test_a_widget_with_no_vector_offers_none(qapp):
    assert vector_source(_shown(qapp, _Painted())) == ""


def test_a_widget_that_drew_svg_hands_it_back(qapp):
    assert vector_source(_shown(qapp, _Vector())) == _SVG


def test_a_widget_whose_svg_RAISES_is_treated_as_having_none(qapp):
    """**AN EXPORT MUST NOT KILL A PAINT PATH.** This is reached while a
    context menu is opening over a live reader, so a renderer that falls
    over costs the SVG entry and nothing else."""
    assert vector_source(_Broken()) == ""


def test_a_depiction_that_never_drew_offers_no_svg(qapp):
    from openchem.ui.widgets.depiction_widget import DepictionWidget

    widget = _shown(qapp, DepictionWidget(None, molblock=""))

    assert vector_source(widget) == ""


def test_a_depiction_that_DREW_AND_THEN_REFUSED_gives_up_its_drawing(qapp):
    """**THE TRANSITION, AND A FRESH WIDGET DOES NOT TEST IT.**

    A stale result or an unresolvable structure makes `DepictionWidget` show
    a message instead of a picture -- but it drew a real one first, and the
    SVG of that earlier molecule is still in hand. Offering "Copy as SVG"
    then hands back the PREVIOUS molecule's drawing, which is exactly the
    plausible-looking lie this reader refuses everywhere else.

    A mutation arm proved a fresh-widget test cannot see this: removing the
    line that clears the retained SVG survived a full run, because
    `__init__` had already set it empty and the test never made the widget
    draw anything.
    """
    from openchem.domain.visualization import VisualizationLayer
    from openchem.ui.widgets.depiction_widget import DepictionAnnotation, DepictionWidget

    annotation = DepictionAnnotation(
        title="Sites",
        layer=VisualizationLayer(name="sites", atom_colors={0: "#ff0000"}, atom_labels={0: "x"}),
    )
    widget = _shown(qapp, DepictionWidget(annotation, molblock=_ETHANOL))
    drawn = vector_source(widget)
    assert drawn, "the setup did not draw anything, so this would pass vacuously"

    widget.set_molblock("")

    assert vector_source(widget) == "", (
        "the widget is showing a message and still handing out the drawing "
        "it made for the previous structure"
    )


def test_the_svg_handed_out_is_the_one_DRAWN_not_a_fresh_render(qapp):
    """Re-rendering on demand would run against whatever the widget holds
    NOW, so an export taken after the structure moved would be a picture
    nobody had seen -- and for a stale result, one drawn against the wrong
    molecule."""
    from openchem.domain.visualization import VisualizationLayer
    from openchem.ui.widgets.depiction_widget import DepictionAnnotation, DepictionWidget

    annotation = DepictionAnnotation(
        title="Sites",
        layer=VisualizationLayer(name="sites", atom_colors={0: "#ff0000"}, atom_labels={0: "x"}),
    )
    widget = _shown(qapp, DepictionWidget(annotation, molblock=_ETHANOL))
    drawn = vector_source(widget)
    assert drawn

    # The structure moves underneath WITHOUT a redraw, the way a stale
    # result's does.
    widget._molblock = _METHANOL

    assert vector_source(widget) == drawn, (
        "the export re-rendered against the current structure instead of "
        "handing back the picture on screen"
    )


# --- and the refusals --------------------------------------------------


def test_a_blank_image_is_recognised():
    image = QImage(20, 20, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))

    assert is_blank(image)


def test_a_zero_sized_image_is_blank_rather_than_an_error():
    assert is_blank(QImage())
    assert is_blank(QImage(0, 0, QImage.Format.Format_RGB32))


def test_an_image_with_content_is_not_blank():
    image = QImage(20, 20, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    for x in range(10):
        image.setPixelColor(x, 5, QColor("navy"))

    assert not is_blank(image)


def test_copying_a_blank_widget_REFUSES_rather_than_copying_nothing(qapp):
    """A silent copy of nothing is indistinguishable from a successful one
    until you paste it somewhere else entirely."""
    blank = _shown(qapp, QWidget())

    message = copy_picture(blank)

    assert "nothing drawn" in message.lower(), message


def test_copying_a_drawn_widget_says_what_it_copied(qapp):
    message = copy_picture(_shown(qapp, _Painted()))

    assert "copied the picture" in message.lower(), message
    assert "x" in message, "the size is what tells a blank copy from a real one"


def test_copying_as_svg_from_a_widget_that_has_none_refuses(qapp):
    message = copy_picture(_shown(qapp, _Painted()), as_vector=True)

    assert "no vector" in message.lower(), message


def test_copying_as_svg_puts_the_drawing_on_as_TEXT(qapp):
    from PySide6.QtGui import QGuiApplication

    copy_picture(_shown(qapp, _Vector()), as_vector=True)

    assert QGuiApplication.clipboard().text() == _SVG


# --- saving -------------------------------------------------------------


def test_saving_png_writes_an_image_that_opens(qapp, tmp_path, monkeypatch):
    target = tmp_path / "chart.png"
    monkeypatch.setattr(
        "PySide6.QtWidgets.QFileDialog.getSaveFileName",
        lambda *a, **k: (str(target), "PNG image (*.png)"),
    )

    message = save_picture(_shown(qapp, _Painted()))

    assert target.exists(), message
    assert not QImage(str(target)).isNull(), "the file is not a readable image"
    assert not is_blank(QImage(str(target)))


def test_saving_svg_writes_the_DRAWING_not_a_bitmap(qapp, tmp_path, monkeypatch):
    target = tmp_path / "sites.svg"
    monkeypatch.setattr(
        "PySide6.QtWidgets.QFileDialog.getSaveFileName",
        lambda *a, **k: (str(target), "SVG image (*.svg)"),
    )

    save_picture(_shown(qapp, _Vector()))

    assert target.read_text(encoding="utf-8") == _SVG


def test_a_svg_suffix_on_a_widget_with_no_vector_REFUSES(qapp, tmp_path, monkeypatch):
    """**A `.svg` FULL OF PNG BYTES IS A FILE NOTHING OPENS.** The format
    follows the suffix, so a caller that asked for one the widget cannot
    produce is told, rather than handed a bitmap under the wrong name."""
    target = tmp_path / "chart.svg"
    monkeypatch.setattr(
        "PySide6.QtWidgets.QFileDialog.getSaveFileName",
        lambda *a, **k: (str(target), "SVG image (*.svg)"),
    )

    message = save_picture(_shown(qapp, _Painted()))

    assert not target.exists(), "a bitmap was written under an .svg name"
    assert "no vector form" in message.lower(), message


def test_saving_a_blank_widget_writes_no_file(qapp, tmp_path, monkeypatch):
    target = tmp_path / "blank.png"
    monkeypatch.setattr(
        "PySide6.QtWidgets.QFileDialog.getSaveFileName",
        lambda *a, **k: (str(target), "PNG image (*.png)"),
    )

    message = save_picture(_shown(qapp, QWidget()))

    assert not target.exists(), "a blank file was written"
    assert "nothing drawn" in message.lower(), message


def test_cancelling_the_dialog_writes_nothing_and_says_nothing(qapp, monkeypatch):
    monkeypatch.setattr(
        "PySide6.QtWidgets.QFileDialog.getSaveFileName", lambda *a, **k: ("", "")
    )

    assert save_picture(_shown(qapp, _Painted())) == ""


# --- the menu offers what the widget can actually do ---------------------


def test_the_menu_offers_svg_only_when_there_is_one(qapp):
    with_svg = QMenu()
    add_picture_actions(with_svg, _shown(qapp, _Vector()))
    without = QMenu()
    add_picture_actions(without, _shown(qapp, _Painted()))

    assert [a.text() for a in with_svg.actions()][0] == "Copy as SVG"
    assert "Copy as SVG" not in [a.text() for a in without.actions()]
    assert "Copy picture" in [a.text() for a in without.actions()]


def test_the_menu_always_offers_a_raster_export(qapp):
    """Even for a widget drawing nothing: the REFUSAL is what tells a user
    there is no picture, and an action that silently vanishes tells them
    nothing at all."""
    menu = QMenu()
    add_picture_actions(menu, _shown(qapp, QWidget()))

    assert [a.text() for a in menu.actions()] == ["Copy picture", "Save picture..."]


# --- file names ----------------------------------------------------------


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Solubility vs pH (mg/mL)", "solubility-vs-ph-mg-ml"),
        ("Lewis sites", "lewis-sites"),
        ("", "picture"),
        ("///", "picture"),
        ("Isotope pattern: M+1", "isotope-pattern-m-1"),
    ],
)
def test_a_chart_title_becomes_a_usable_file_name(title, expected):
    assert file_stem(title) == expected


def test_a_very_long_title_is_bounded():
    assert len(file_stem("x" * 500)) <= 60


# --- the layering rule this module exists to state -----------------------


def test_the_3d_view_is_NOT_exported_through_this_module():
    """**`widget.grab()` IS CORRECT HERE AND WRONG FOR THE 3D VIEW**, and
    the distinction has to survive somebody tidying.

    These are ordinary in-process Qt widgets and Qt has their pixels. A
    `QWebEngineView` renders out of PROCESS, so the same call there returns
    a correctly-sized BLANK rectangle -- measured, and asserted against the
    real page by `test_widget_grab_is_the_blank_frame_THIS_EXISTS_TO_AVOID`.
    The 3D view therefore goes through `Mol3DViewerBackend.grab_png`, which
    reads the page's own canvas.

    A source check because the failure is invisible from here: both routes
    return an image, and only one of them has a molecule in it.
    **AND THE FIRST VERSION OF THIS GUARD MATCHED ITS OWN PROSE**, which is
    the EIGHTH recorded instance in this repository -- `grab_png`'s docstring
    explains the ban using the banned words, so a plain substring scan over
    `inspect.getsource` failed on the explanation. The docstring is stripped
    before the code is searched, which is the fix the other seven arrived at.
    """
    import ast
    import inspect
    import textwrap

    from openchem.ui import picture_export
    from openchem.ui.widgets import mol3d_viewer_backend

    assert "grab_png" in dir(mol3d_viewer_backend.Mol3DViewerBackend)
    tree = ast.parse(
        textwrap.dedent(inspect.getsource(mol3d_viewer_backend.Mol3DViewerBackend.grab_png))
    )
    function = tree.body[0]
    if (
        function.body
        and isinstance(function.body[0], ast.Expr)
        and isinstance(function.body[0].value, ast.Constant)
        and isinstance(function.body[0].value.value, str)
    ):
        del function.body[0]
    code = ast.unparse(function)

    assert "widget.grab" not in code, (
        "the 3D backend grabs the widget, which photographs an empty frame"
    )
    assert "pngURI" in code

    assert "QWebEngineView" in picture_export.__doc__, (
        "picture_export no longer records why the 3D view is not its job"
    )


def test_the_picture_menu_connects_a_BOUND_METHOD_not_a_closure():
    """**PySide6 HOLDS A CONNECTED PLAIN CALLABLE STRONGLY**, so a closure
    capturing `self` survives refcounting AND the cyclic collector --
    recorded twice in `app/main_window.py`, where it leaked whole windows.
    The first version of the picture menu did exactly that: a nested
    `show(position)` capturing both the view and a chart widget the view
    owns.

    **THIS IS THE WEAK HALF, AND THE STRONG ONE WAS TRIED AND DOES NOT
    WORK.** A weakref test was written first and is not kept: the project's
    `conftest.dispose` force-deletes the C++ object, so the reference clears
    whatever holds the Python wrapper, and a mutation arm putting the
    closure back SURVIVED it. An inert guard is worse than none, so what
    remains is a source check that can actually fail -- it reads the
    connection rather than the leak.

    **NOR WAS THE CLOSURE PROVEN TO HAVE CAUSED THE SUITE CRASH** that led
    here. The full suite died with an access violation inside
    `conftest.dispose` and zero failures; the file alone passes, and this
    repository records that crash class as pre-existing and victim-varying
    on a byte-identical tree. The closure is fixed because it breaks a
    recorded rule, which is reason enough on its own.
    """
    import ast
    import inspect
    import textwrap

    from openchem.ui.widgets.fact_view import FactView

    source = textwrap.dedent(inspect.getsource(FactView._install_picture_menu))
    tree = ast.parse(source)

    connects = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "connect"
    ]
    assert connects, "the picture menu is not connected to anything"
    for call in connects:
        handler = call.args[0]
        assert isinstance(handler, ast.Attribute) and isinstance(handler.value, ast.Name), (
            f"the picture menu connects {ast.unparse(handler)}, which is not a "
            "bound method -- a connected closure capturing `self` pins the reader"
        )
        assert handler.value.id == "self", ast.unparse(handler)

    assert not [n for n in ast.walk(tree) if isinstance(n, (ast.Lambda, ast.FunctionDef))][1:], (
        "a callable is defined inside _install_picture_menu; if it is connected "
        "it will pin the reader"
    )
