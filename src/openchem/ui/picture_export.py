"""Copy or save a result's PICTURE, wherever that picture is being read.

**SHARED CHROME, NOT PER-DIALOG BEHAVIOUR.** Exporting a drawing existed in
exactly one place -- `LewisDiagramDialog`'s Copy SVG / Save SVG buttons --
so every other picture this application draws could be read and not taken
away. The charts and depictions in the results reader had none, and a
reader that cannot hand you its picture is a dead end of the same kind as a
summary with no way back to the result.

This module is the behaviour; the reader installs it on whatever widget it
just built, so the DOCKED reader, the POPPED-OUT one and a copy opened in
its own window export identically by construction rather than by three
implementations agreeing.

**SVG WHEN THERE IS ONE, PNG ALWAYS.** A structure drawing is vector and is
exactly the kind of picture somebody scales into a document; a chart drawn
with `QPainter` is not, and offering "Save as SVG" for it would produce a
file holding a bitmap in an SVG wrapper. So the offer is derived from what
the widget can actually produce -- `rendered_svg()` -- rather than from a
flag somebody has to remember to set.

**AND `widget.grab()` IS CORRECT HERE, WHICH IT IS NOT FOR THE 3D VIEW.**
These are ordinary in-process Qt widgets and Qt has their pixels. A
`QWebEngineView` renders out of PROCESS, so the same call there returns a
correctly-sized blank rectangle -- measured, and asserted in
`tests/test_mol3d_viewer_backend.py`. That one reads the page's own canvas
through `Mol3DViewerBackend.grab_png`. Two different answers because they
are two different situations, and conflating them produces a picture-shaped
lie rather than an error.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtWidgets import QFileDialog, QMenu, QMessageBox, QWidget

logger = logging.getLogger("openchem.ui")

#: What a widget must offer to export as vector. Duck-typed, like the
#: reader's own `facts`/`by_category()`/`find()` contract: a widget that can
#: hand back the SVG it drew is exportable as SVG, and no registry has to be
#: kept in step with the widget types.
_SVG_METHOD = "rendered_svg"


def file_stem(title: str) -> str:
    """A chart's title as something a file system will accept.

    **A DEFAULT FILE NAME, NOT A SANITISER FOR ARBITRARY INPUT.** The title
    comes from a producer's own annotation, so this is about `/` and `:` in
    "Solubility vs pH (mg/mL)" rather than about hostile paths -- the file
    dialog owns where the file actually goes, and the user can rename it.
    Empty titles fall back rather than producing a file called `.png`.
    """
    kept = [c if (c.isalnum() or c in "-_") else "-" for c in title.strip().lower()]
    stem = "".join(kept).strip("-")
    while "--" in stem:
        stem = stem.replace("--", "-")
    return stem[:60] or "picture"


def vector_source(widget: QWidget) -> str:
    """The SVG `widget` actually drew, or `""`.

    Empty covers three cases that are all the same to a caller -- the widget
    draws no vector at all, it drew a message instead of a picture, and it
    has not drawn yet. All three mean "there is no SVG to give you", and a
    caller that distinguished them would still offer the same thing.
    """
    source = getattr(widget, _SVG_METHOD, None)
    if not callable(source):
        return ""
    try:
        return str(source() or "")
    except Exception as exc:  # noqa: BLE001 - an export must not kill a paint path
        logger.warning("Could not read a widget's SVG: %s", exc)
        return ""


def raster_source(widget: QWidget) -> QImage:
    """What `widget` looks like, as an image.

    **THE WIDGET'S OWN SIZE, NOT THE SCREEN'S.** `grab()` captures at the
    device pixel ratio, so this is already a high-DPI image on a high-DPI
    display and needs no scaling of its own.
    """
    return widget.grab().toImage()


def is_blank(image: QImage) -> bool:
    """Whether an image carries no picture -- one colour, or no pixels.

    **AN EXPORT THAT WRITES A BLANK FILE IS WORSE THAN ONE THAT REFUSES**,
    because the file opens and looks like the answer. This is the cheap
    structural check that catches the shapes that have actually occurred
    here: a zero-sized widget, and a widget whose content had not been
    painted when it was grabbed.

    Deliberately NOT a judgement about whether the picture is *right* --
    a legitimately flat chart would be refused by this, which is why it
    guards the export rather than the rendering.
    """
    # **OUTCOME-REDUNDANT, AND KEPT FOR A DIFFERENT REASON.** The scan
    # below also answers True for a null image -- its loop runs zero times
    # -- so a mutation removing this line changes no answer, and no test
    # can honestly claim to cover it. What it prevents is the `pixel(0, 0)`
    # read further down: on a null QImage that returns garbage (measured:
    # 12345) and emits a Qt warning on every blank check.
    if image.isNull() or image.width() == 0 or image.height() == 0:
        return True
    # A sample rather than every pixel: this runs on a click, and a picture
    # with any content at all differs somewhere in a 32x32 grid.
    scaled = image.scaled(32, 32, Qt.AspectRatioMode.IgnoreAspectRatio)
    first = scaled.pixel(0, 0)
    for x in range(scaled.width()):
        for y in range(scaled.height()):
            if scaled.pixel(x, y) != first:
                return False
    return True


def copy_picture(widget: QWidget, as_vector: bool = False) -> str:
    """Put `widget`'s picture on the clipboard. Returns a status line.

    Vector goes on as TEXT, because that is what an SVG is and what every
    editor that accepts one reads. The image goes on as an image.
    """
    clipboard = QGuiApplication.clipboard()
    if clipboard is None:  # pragma: no cover - defensive
        return "No clipboard is available."
    if as_vector:
        svg = vector_source(widget)
        if not svg:
            return "There is no vector drawing to copy."
        clipboard.setText(svg)
        return "Copied the drawing as SVG."
    image = raster_source(widget)
    if is_blank(image):
        return "There is nothing drawn to copy."
    clipboard.setImage(image)
    return f"Copied the picture ({image.width()}x{image.height()})."


def save_picture(widget: QWidget, parent: QWidget | None = None, stem: str = "picture") -> str:
    """Ask where to put `widget`'s picture, and write it. Returns a status line.

    **THE FORMAT FOLLOWS THE CHOSEN SUFFIX, NOT A SEPARATE CONTROL.** A
    dialog that offered both and then wrote whichever a hidden radio button
    said is how a `.svg` full of PNG bytes gets made. `.svg` is offered only
    when the widget really drew one.
    """
    svg = vector_source(widget)
    filters = ["PNG image (*.png)"]
    if svg:
        # SVG FIRST when it exists: a structure drawing is the case somebody
        # scales into a document, and the first filter is the default.
        filters.insert(0, "SVG image (*.svg)")
    path, _chosen = QFileDialog.getSaveFileName(
        parent, "Save picture", f"{stem}.{'svg' if svg else 'png'}", ";;".join(filters)
    )
    if not path:
        return ""
    try:
        if path.lower().endswith(".svg"):
            if not svg:
                return "This picture has no vector form -- save it as PNG."
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(svg)
            return "Saved the drawing as SVG."
        image = raster_source(widget)
        if is_blank(image):
            return "There is nothing drawn to save."
        if not image.save(path, "PNG"):
            return "Could not write that file."
        return f"Saved the picture ({image.width()}x{image.height()})."
    except OSError as exc:
        if parent is not None:
            QMessageBox.warning(parent, "Save picture", str(exc))
        return f"Could not save: {exc}"


def add_picture_actions(
    menu: QMenu, widget: QWidget, parent: QWidget | None = None, stem: str = "picture"
) -> None:
    """Append this widget's picture actions to `menu`.

    **WHAT THE WIDGET CAN DO, NOT WHAT ITS TYPE USUALLY DOES.** A depiction
    that refused to draw -- a stale result, an unresolvable structure --
    holds no SVG, and offering "Copy as SVG" for it would hand back an empty
    string that pastes as nothing. `vector_source` is asked each time the
    menu opens rather than once when it was built.
    """
    if vector_source(widget):
        menu.addAction(
            "Copy as SVG",
            lambda: _report(parent, copy_picture(widget, as_vector=True)),
        )
    menu.addAction("Copy picture", lambda: _report(parent, copy_picture(widget)))
    menu.addAction("Save picture...", lambda: _report(parent, save_picture(widget, parent, stem)))


def _report(parent: QWidget | None, message: str) -> None:
    """Say what happened, through the host's own status line if it has one.

    A silent copy and a failed copy look identical, and this project's
    reader already answers "Copied N facts as Markdown" for the text half --
    the picture half must not be quieter than the text it sits beside.
    """
    if not message:
        return
    setter = getattr(parent, "set_status", None)
    if callable(setter):
        setter(message)
        return
    logger.info("%s", message)
