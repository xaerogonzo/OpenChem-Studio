"""Move a cramped view into its own window, and back.

WHY THIS EXISTS. Reported against the 3D Alignment panel: after aligning
two molecules on a common scaffold, the superimposed conformers render
into a strip about 400x90 px at the bottom of the right-hand dock. The
overlay IS that panel's entire output and it is the one thing you cannot
read. The cause is structural rather than a bug -- a settings group box,
a 160 px result table and a header row sit above the viewer, all of them
fixed height, in a dock that opens at 420 px and whose minimum is 280.

Floating the whole dock does not answer it: that detaches the settings,
the table and the note along with the picture, and the picture is still
last in the stack.

THIS MOVES THE VIEW, IT DOES NOT COPY IT -- and that is the one thing to
understand before changing anything here.

`FactView.open_in_window` builds a SECOND `FactView` on the same report,
which is right for a report (cheap to re-render, and two side by side is
the use case) and wrong for a 3D view: the camera angle the user has just
set is the whole reason they want it bigger, and a fresh viewer would
start at a default camera and cost another QtWebEngine process set. An
agent meeting `open_in_window()` will assume the `FactView` pattern, so
the rule this project now follows is written down in CLAUDE.md: for a
stateful visualisation, the documentation and the help contract must say
whether the action MOVES the existing view or CREATES another. Never
infer it from the button label.

RE-PARENTING A `QWebEngineView` WAS MEASURED BEFORE ANY OF THIS WAS
WRITTEN, because nothing in this repository had ever done it and "Qt
handles it" is an assumption this file's neighbours have been wrong about
six times. On a real display, with an ensemble loaded and the camera
turned to a distinctive angle:

    stage                    identity   parent chain              ink%  black%
    docked                   same       View -> host -> panel     10.5  0.2
    detached                 same       View -> QDialog -> ...    10.7  0.2
    drag while detached      --         camera MOVED              --    --
    returned                 same       View -> host -> panel      9.7  0.1
    3x round trip            same       stable                     9.0  0.2
    destroyed after return   ALIVE      View -> host -> panel      9.7  0.1

The camera quaternion came back byte-identical across the move, a drag
landed while detached, and the canvas genuinely re-laid out (796x596 ->
1800x1400 -> 796x596) rather than freezing on a last frame. Black
fraction was counted SEPARATELY from ink, because a failed render is a
BLACK canvas and scores as heavily inked -- this project has read that
metric backwards once already.

THE LIFECYCLE. Three states, four transitions, nothing else:

                        pop_out()
            DOCKED  ---------------->  DETACHED
              |     <----------------      |
              |      return_home()         |
              |      window closed         |
              |                            |
              |   owner destroyed          |  owner destroyed
              +----------> DISPOSING <-----+

    DOCKED      content.parentWidget() is this host's slot
    DETACHED    content.parentWidget() is the window's container, and
                THIS HOST IS STILL THE LOGICAL OWNER -- `content()`
                returns the same object either way, never "whatever is
                in the slot"
    DISPOSING   the owner is going away. The window is parented to the
                host, so it is destroyed with it and there is no restore,
                because there is no longer a home to restore into.

"Looked away from" and "destroyed" are different things, and conflating
them is the mistake this docstring exists to prevent. Six Qt events mean
"the panel went away" and only two of them bring the view home:

    another dock selected                stays open
    another tab selected                 stays open
    the dock hidden or closed            stays open (retained, not destroyed)
    the dock floated                     stays open
    a new job / the result cleared       RETURNS HOME (a semantic reset)
    the owner destroyed / app shutdown   DISPOSING, no restore

Which is why there is deliberately NO `hideEvent` hook here: a tab page
receives hide events when you switch away from it, so a hideEvent-driven
return would snap the window shut every time the user glanced elsewhere.
The first four rows above are all hideEvent.

`finished` IS THE PRIMARY HOOK AND `closeEvent` IS NOT, which is the
opposite of the obvious reading. Measured against Qt's own behaviour:

    the X button   close() -> QCloseEvent -> QDialog::closeEvent
                   -> reject() -> done() -> finished
    Escape         keyPressEvent -> reject() -> done() -> finished
                   ... and NO QCloseEvent at all

So a `closeEvent`-only implementation silently leaks the Escape key,
leaving the content in a hidden window. `closeEvent` is kept as an
additional EARLIER hook on the X path so the restore happens before the
window starts tearing down, and `return_home` is idempotent so both
firing is harmless.

VIEW-SPECIFIC CONTROLS STAY IN THE PANEL. The header strip never moves.
The Alignment panel's `Style:` combo goes on driving the detached view
from the dock, because the backend holds the page and the channel rather
than the parent; the window carries only a Return to panel button. A
duplicate control in the window would be two widgets for one setting,
which is a synchronisation bug waiting to be written.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from openchem.ui.widgets.help_tooltip import HelpTooltip, apply_help_tooltip
from openchem.ui.widgets.screen_fit import fit_within

#: TWO CONCEPTS, ONE RENDERING PER HOST.
#:
#: The same shape `DockTitleBar`'s three buttons already have across
#: twelve docks: one `help_id` each, with `DocumentableControl.instance_path`
#: telling the renderings apart. They live here rather than at each call
#: site so that adding a host cannot mean forgetting a contract.
_HELP = {
    "pop_out": HelpTooltip(
        text=(
            "Moves this view into its own resizable window.\n\n"
            "The view MOVES rather than being copied, so the angle you have "
            "set and what is loaded carry over, and this panel's own controls "
            "stay here and keep driving it. Press again to bring the window to "
            "the front; close it to bring the view back."
        ),
        tier=1,
        help_id="workspace.pop_out_view",
        topic="panels",
        help_anchor="properties",
    ),
    "return": HelpTooltip(
        text=(
            "Puts this view back into the panel it came from and closes this "
            "window.\n\n"
            "Closing the window does the same thing."
        ),
        tier=1,
        help_id="workspace.return_view_to_panel",
        topic="panels",
        help_anchor="properties",
    ),
}

#: What a detached window would LIKE to open at, before the screen has its
#: say. Generous on purpose -- the whole point is room the dock cannot
#: give -- and `fit_within` clamps it on a smaller display.
_PREFERRED_SIZE = (960, 720)

#: The button's face. ONE glyph in both states -- the STYLE draws the
#: difference, through the button's checked state, and the accessible
#: name says it in words.
#:
#: THE SECOND GLYPH WAS MEASURED AND THROWN AWAY, which is the part worth
#: keeping. The first version showed U+2B1C WHITE LARGE SQUARE while
#: detached; every test in this repository passed, and a magnified
#: screenshot of the running application showed a **lavender emoji
#: square** sitting in the panel chrome. Windows resolves that codepoint
#: to a colour emoji font, and the obvious alternatives do the same --
#: U+25FB, U+29C9 and U+1F5D6 all come back in colour.
#:
#: A PROBE THAT COUNTS COLOURED PIXELS CANNOT SETTLE THIS, which was the
#: second thing measured. At button size ClearType's sub-pixel fringes
#: are genuinely coloured, so an unassigned control codepoint scores as
#: "drew, in colour" as well and the test cannot discriminate.
#: `QFontMetrics.inFont()` is no help either -- CLAUDE.md records it
#: answering False for glyphs that render perfectly, because it asks
#: about one nominated font rather than the fallback chain Qt paints
#: with. The screenshot was the oracle.
#:
#: So the state is not carried by a glyph at all. `setChecked` is drawn
#: by the platform style, is themed, cannot be missing from a font, and
#: is the conventional way to show a toggle that is on.
#:
#: U+2197 is kept because it was confirmed in a screenshot of the real
#: application, at the real size, in the real panel.
_GLYPH_POP_OUT = "↗"


def _is_managed_by_a_layout(widget: QWidget) -> bool:
    """Is some layout already responsible for placing `widget`?

    `QLayout.indexOf` is not recursive and a panel's controls are usually
    two or three layouts deep, so this walks the parent's layout tree.

    It exists for one specific mistake, which is easy to make and silent:

        layout.addWidget(style_combo)          # still there
        PopOutHost(..., header=[style_combo])  # and now here too

    Qt re-parents rather than complaining, so the original row is left
    with a hole and nothing says why.
    """
    parent = widget.parentWidget()
    if parent is None:
        return False
    layout = parent.layout()
    return _layout_contains(layout, widget) if layout is not None else False


def _layout_contains(layout: QLayout, widget: QWidget) -> bool:
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item is None:
            continue
        if item.widget() is widget:
            return True
        child = item.layout()
        if child is not None and _layout_contains(child, widget):
            return True
    return False


class PopOutWindow(QDialog):
    """The window a `PopOutHost` moves its content into.

    Parented to the HOST, which is what makes `DISPOSING` a cascade
    rather than a policy somebody has to remember: destroying the panel
    destroys the host, which destroys this, which destroys the content --
    one direction, no dangling wrapper. An unparented window would
    outlive its owner, which the state machine forbids.

    It defines exactly ONE control of its own, the Return to panel
    button, and that is asserted rather than left as a claim -- see
    `tests/test_pop_out_host.py`. Everything else inside it belongs to the
    content widget and is already walked in the panel that owns it.
    """

    def __init__(self, host: "PopOutHost", title: str) -> None:
        super().__init__(host)
        self.setWindowTitle(title)
        self._host = host

        # A QDialog gets neither by default, so a window that opened too
        # tall could not be shrunk, moved back into view or maximised --
        # the periodic table shipped exactly that bug and this is its fix
        # applied one layer up.
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setSizeGripEnabled(True)

        self._slot = QWidget(self)
        slot_layout = QVBoxLayout(self._slot)
        slot_layout.setContentsMargins(0, 0, 0, 0)
        self._slot_layout = slot_layout

        # NOT a QDialogButtonBox: a button inside one is exempt from the
        # help-contract walk, and "Return to panel" is not a standard
        # dialog role. Exempting it would be dodging the documentation
        # rather than satisfying it.
        self._return_button = QPushButton("Return to panel", self)
        apply_help_tooltip(self._return_button, _HELP["return"])
        self._return_button.clicked.connect(self._on_return_clicked)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self._return_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._slot, 1)
        layout.addLayout(buttons)

        self._fit_to_screen()

    def content_slot(self) -> QVBoxLayout:
        return self._slot_layout

    def _fit_to_screen(self) -> None:
        """Open large, but never larger than the screen can show.

        The arithmetic is in `fit_within` because the suite's `offscreen`
        platform reports an 800x800 screen, where this clamp always
        bites -- so calling it and deleting the call are indistinguishable
        through the window, and only the pure function can be tested.
        """
        screen = QGuiApplication.primaryScreen()
        if screen is None:  # pragma: no cover - no display
            self.resize(*_PREFERRED_SIZE)
            return
        available = screen.availableGeometry()
        self.resize(
            *fit_within(
                _PREFERRED_SIZE[0], _PREFERRED_SIZE[1], available.width(), available.height()
            )
        )

    def _on_return_clicked(self) -> None:
        self._host.return_home()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        """The X button's path, taken EARLY.

        Not the only path -- Escape reaches `reject()` without ever
        sending a close event -- so this is a convenience that gets the
        content out before teardown begins, and `finished` is what
        guarantees the restore happens at all.
        """
        self._host.return_home()
        super().closeEvent(event)


class PopOutHost(QWidget):
    """Holds one view, with a button that moves it into its own window.

    `content` is the widget to move. `header` widgets are the panel's own
    controls, which sit beside the pop-out button and NEVER move (see the
    module docstring). They become children of this host but stay
    semantically the panel's, so they must not already belong to another
    layout -- passing one that does is refused rather than silently
    stealing it.
    """

    def __init__(
        self,
        content: QWidget,
        *,
        title: str,
        header: Sequence[QWidget] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._content = content
        self._window: PopOutWindow | None = None

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        for widget in header:
            if _is_managed_by_a_layout(widget):
                raise ValueError(
                    f"{type(widget).__name__} is already in a layout. A header widget "
                    "moves into the host; leaving it in its original row as well "
                    "silently steals it and leaves a hole there."
                )
            header_row.addWidget(widget)
        header_row.addStretch(1)

        self._pop_out_button = QToolButton(self)
        self._pop_out_button.setText(_GLYPH_POP_OUT)
        self._pop_out_button.setAccessibleName("Show in its own window")
        self._pop_out_button.setAutoRaise(True)
        # Checkable so the STYLE draws "this view is currently out"
        # rather than a second glyph doing it -- see `_GLYPH_POP_OUT`.
        # Qt flips this itself on a click, before the handler runs, so
        # `_sync_button` overwrites it with the real state on every path.
        self._pop_out_button.setCheckable(True)
        self._pop_out_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        apply_help_tooltip(self._pop_out_button, _HELP["pop_out"])
        self._pop_out_button.clicked.connect(self._on_pop_out_clicked)
        header_row.addWidget(self._pop_out_button)

        # BUILT HERE AND HIDDEN, never added at pop-out time. CLAUDE.md
        # records a placeholder added to a surface that already held
        # content corrupting the heap 5/5; that was traced to the teardown
        # collect and is fixed, but building both slots up front sidesteps
        # the class entirely and costs nothing.
        #
        # A PLAIN QLabel, deliberately NOT `empty_state()`. That helper
        # marks itself with a Qt property, and
        # `QuantumChemistryPanel.empty_message_for_tab` returns the first
        # marked widget it finds anywhere under a tab -- a hidden pop-out
        # placeholder would be found and would answer for the tab with
        # the wrong message entirely.
        self._placeholder = QLabel(
            "Showing in its own window.\nClose that window to bring it back here.",
            self,
        )
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setWordWrap(True)
        self._placeholder.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self._placeholder.setVisible(False)

        self._slot = QVBoxLayout()
        self._slot.setContentsMargins(0, 0, 0, 0)
        self._slot.addWidget(content, 1)
        self._slot.addWidget(self._placeholder, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(header_row)
        layout.addLayout(self._slot, 1)

    # --- state ------------------------------------------------------------

    def content(self) -> QWidget:
        """The same object wherever it currently lives.

        Never "whatever is in the slot": while DETACHED the slot holds the
        placeholder, and a caller asking for the content means the view.
        """
        return self._content

    def detached_window(self) -> PopOutWindow | None:
        """The open window, or None. Stable for one detached session."""
        return self._window

    def is_popped_out(self) -> bool:
        return self._window is not None

    # --- transitions --------------------------------------------------------

    def pop_out(self) -> PopOutWindow:
        """DOCKED -> DETACHED, or raise the window that is already open.

        Returns the SAME window object on a second call rather than making
        another. Three windows all driving one backend is the failure this
        forecloses, and it is also how a user finds a window that has gone
        behind the main one.
        """
        if self._window is not None:
            self._window.show()
            self._window.raise_()
            self._window.activateWindow()
            # A click Qt has already toggled must not be left drawn in
            # the wrong state: this path RAISES rather than returning.
            self._sync_button()
            return self._window

        window = PopOutWindow(self, self._title)
        window.content_slot().addWidget(self._content, 1)
        window.finished.connect(self._on_window_finished)
        self._window = window
        self._placeholder.setVisible(True)
        self._sync_button()
        window.show()
        window.raise_()
        window.activateWindow()
        return window

    def return_home(self) -> None:
        """DETACHED -> DOCKED. Idempotent, and safe at any point of teardown.

        Called from three places -- the window's Return button, its
        `closeEvent`, and its `finished` signal -- precisely because no one
        of them covers every route out. Escape never sends a close event;
        the Return button fires before either.
        """
        window = self._window
        if window is None:
            return
        self._window = None
        # Before the window is touched further, so the content is out of
        # it and owned by this host again even if the teardown that
        # follows is abrupt.
        self._slot.insertWidget(0, self._content, 1)
        self._placeholder.setVisible(False)
        self._sync_button()
        try:
            window.finished.disconnect(self._on_window_finished)
        except (RuntimeError, TypeError):
            # Already disconnected, or the C++ object has gone. Either way
            # there is nothing left to detach from.
            pass
        window.close()
        window.deleteLater()

    def _on_window_finished(self, _result: int = 0) -> None:
        self.return_home()

    def _on_pop_out_clicked(self) -> None:
        self.pop_out()

    def _sync_button(self) -> None:
        """The checked state and the accessible name follow the state.
        The glyph and the TOOLTIP do not.

        The tooltip is fixed on purpose. A state-dependent tooltip is the
        `docking.derive_box_from_ligand` case, where the live string has
        to be asserted to still CONTAIN its contract or the coverage
        guard goes on reporting the control documented while the user
        reads something else. The contract already describes both states,
        so nothing here needs that machinery.
        """
        detached = self.is_popped_out()
        self._pop_out_button.setChecked(detached)
        self._pop_out_button.setAccessibleName(
            "Bring its window to the front" if detached else "Show in its own window"
        )
