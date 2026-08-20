"""Guards for moving a view into its own window and back.

The feature exists because the 3D Alignment panel's overlay renders into
a strip about 400x90 px at the bottom of a 420 px dock. So these tests
come in two halves, and both are needed:

  * a LIFECYCLE half, because the failure modes here are Qt ownership
    ones -- a view destroyed as a child of a window that outlived its
    usefulness, a restore that never fires because Escape does not send a
    close event, a state machine that only works once;
  * a PURPOSE half, because a pop-out mechanism can be lifecycle-perfect
    and still fail to give the picture any more room, which is the only
    reason any of it was written.

`test_the_detached_view_gets_more_height_than_the_docked_one` is the
second half, and it asserts its own setup for the reason this repository
records over and over: a fixture that stops reproducing the squeeze
turns that test green while proving nothing.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QGuiApplication, QKeyEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from openchem.ui.widgets.empty_state import is_empty_state
from openchem.ui.widgets.pop_out_host import PopOutHost, PopOutWindow
from openchem.ui.widgets.screen_fit import fit_within
from openchem.ui.widgets.tooltip_inventory import iter_documentable_controls


def _dispose(widget) -> None:
    """Destroy one widget deterministically.

    PER WIDGET, never `sendPostedEvents(None, DeferredDelete)`: the global
    form drains every pending deferred delete in the process, including
    ones other test files left queued, which is a double free this
    repository has already paid for.
    """
    widget.setParent(None)
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)


@pytest.fixture
def owner(qapp):
    """A panel-like owner holding a host, disposed of at the end."""
    built: list[QWidget] = []

    def make(content: QWidget | None = None, header=()):
        panel = QWidget()
        content = content if content is not None else QLabel("content")
        host = PopOutHost(content, title="Test view", header=header, parent=panel)
        QVBoxLayout(panel).addWidget(host)
        built.append(panel)
        return panel, host, content

    yield make
    for panel in built:
        _dispose(panel)


# --- identity and ownership ------------------------------------------------


def test_the_content_widget_is_the_same_object_after_a_round_trip(owner):
    """MOVE, NEVER COPY -- the invariant the whole design rests on.

    A `FactView.open_in_window`-style implementation, which builds a
    second view on the same data, passes every other test in this file
    and fails this one. That is the point: for a stateful visualisation
    the camera the user just set is what they are trying to see bigger,
    and a fresh viewer starts at a default camera.
    """
    _panel, host, content = owner()
    host.pop_out()
    host.return_home()
    assert host.content() is content


def test_the_host_still_owns_the_content_while_it_is_detached(owner):
    """Qt's PARENT moves; the host's LOGICAL ownership does not.

    `content()` must not degenerate into "whatever is in the slot" -- the
    slot holds the placeholder while detached, and a caller asking for
    the content means the view.
    """
    _panel, host, content = owner()
    window = host.pop_out()

    # Qt's parent really did move, and it moved INTO the window rather
    # than merely away from the host.
    assert content.parentWidget() is not host
    assert window.isAncestorOf(content)

    # ...and the host is still who you ask.
    assert host.content() is content
    assert host.is_popped_out()
    assert host.detached_window() is window


def test_the_content_returns_to_where_it_came_from(owner):
    _panel, host, content = owner()
    host.pop_out()
    host.return_home()
    assert content.parentWidget() is host
    assert not host.is_popped_out()
    assert host.detached_window() is None


def test_a_header_widget_that_already_has_a_layout_is_refused(qapp):
    """The silent mistake this guard exists for.

        layout.addWidget(style_combo)          # still there
        PopOutHost(..., header=[style_combo])  # and now here too

    Qt re-parents without complaint, so the original row is left with a
    hole and nothing says why.
    """
    panel = QWidget()
    row = QVBoxLayout(panel)
    combo = QLabel("Style:", panel)
    row.addWidget(combo)

    with pytest.raises(ValueError, match="already in a layout"):
        PopOutHost(QLabel("content"), title="x", header=[combo], parent=panel)

    _dispose(panel)


def test_a_header_widget_that_is_merely_parented_is_accepted(qapp):
    """The CONTROL for the guard above, and it is load-bearing.

    Every real call site builds its header widgets with the panel as
    parent and hands them straight over, so a rule that refused any
    parented widget would refuse the only usage there is -- and would
    look like a working guard while making the feature unbuildable.
    """
    panel = QWidget()
    combo = QLabel("Style:", panel)  # parented, but in no layout
    host = PopOutHost(QLabel("content"), title="x", header=[combo], parent=panel)
    assert combo.parentWidget() is host
    _dispose(panel)


# --- lifecycle: one test per transition, plus the illegal one --------------


def test_closing_the_window_returns_the_content_before_the_dialog_dies(owner):
    """The crash guard.

    Destroy the window first and Qt deletes the content as its child,
    leaving the panel holding a dead wrapper -- this repository's
    standing `Internal C++ object already deleted` trap.
    """
    _panel, host, content = owner()
    window = host.pop_out()
    window.close()
    QCoreApplication.sendPostedEvents(window, QEvent.Type.DeferredDelete)

    assert content.parentWidget() is host
    assert content.text() == "content"  # the C++ object is still there


def test_escape_returns_the_view_even_though_it_sends_no_close_event(owner):
    """MEASURED QT BEHAVIOUR, asserted rather than trusted.

        the X button   close() -> QCloseEvent -> closeEvent -> reject()
                       -> done() -> finished
        Escape         keyPressEvent -> reject() -> done() -> finished
                       ... and NO QCloseEvent at all

    So driving the restore from `closeEvent` alone -- which reads as the
    tidier design and was proposed as one -- silently leaks Escape and
    leaves the content inside a hidden window. This is the test that
    mutation fails.
    """
    _panel, host, content = owner()
    window = host.pop_out()

    QCoreApplication.sendEvent(
        window,
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier),
    )

    assert not host.is_popped_out()
    assert content.parentWidget() is host


def test_returning_home_and_then_closing_the_window_is_safe(owner):
    """`finished` fires on an already-restored host.

    The nastier ordering: the Return button restores, and the window then
    goes through its own teardown and emits `finished` at a host that has
    already moved on. Without idempotence this restores a second time
    into a slot that is already full.
    """
    _panel, host, content = owner()
    window = host.pop_out()
    host.return_home()
    window.close()
    QCoreApplication.sendPostedEvents(window, QEvent.Type.DeferredDelete)

    assert content.parentWidget() is host
    assert host.content() is content


def test_return_home_is_idempotent(owner):
    _panel, host, content = owner()
    host.pop_out()
    host.return_home()
    host.return_home()
    host.return_home()
    assert content.parentWidget() is host


def test_destroying_the_owner_while_detached_leaves_no_window_behind(owner):
    """The DISPOSING transition, which nothing else covers.

    An earlier draft of the plan said the owner being destroyed "returns
    the view home", which is incoherent -- once the host is gone there is
    no home to return to. The window is parented to the HOST precisely so
    this is a cascade rather than a policy somebody has to remember:
    panel -> host -> window -> content, one direction, nothing dangling.

    An unparented window would outlive its owner and go on showing a view
    whose panel no longer exists, which is the state machine's one
    forbidden outcome.
    """
    panel = QWidget()
    content = QLabel("content")
    host = PopOutHost(content, title="Test view", parent=panel)
    QVBoxLayout(panel).addWidget(host)
    window = host.pop_out()

    assert window.parent() is host, "the window must be owned by the host, not floating free"

    panel.setParent(None)
    panel.deleteLater()
    QCoreApplication.sendPostedEvents(panel, QEvent.Type.DeferredDelete)

    # Nothing is asserted about `content` here on purpose: it is gone,
    # correctly, along with everything else. What must not happen is a
    # surviving top-level window.
    from PySide6.QtWidgets import QApplication

    assert not [w for w in QApplication.topLevelWidgets() if isinstance(w, PopOutWindow)]


def test_a_second_pop_out_raises_the_window_that_is_already_open(owner):
    """WINDOW IDENTITY, not merely that a window is shown.

    Without this, pressing the button three times gives three windows all
    driving one backend. It is also how a user finds a window that has
    gone behind the main one.
    """
    _panel, host, _content = owner()
    first = host.pop_out()
    second = host.pop_out()
    assert second is first
    assert host.detached_window() is first


def test_the_host_can_be_popped_out_again_after_a_full_cycle(owner):
    """A one-shot state machine survives a test that only ever goes out
    once, so this goes out, comes back, and goes out again."""
    _panel, host, content = owner()
    first = host.pop_out()
    host.return_home()
    second = host.pop_out()

    assert second is not first
    assert host.is_popped_out()
    assert content.parentWidget() is not host
    host.return_home()
    assert content.parentWidget() is host


# --- the window -------------------------------------------------------------


def test_the_window_can_be_maximised_and_carries_a_size_grip(owner):
    """A `QDialog` gets neither by default.

    The periodic table shipped exactly that bug -- a window that opened
    taller than the screen, with no maximise button and no grip to get it
    back -- and a minimum larger than the screen cannot be rescued by
    resizing, because `resize()` is clamped to it.
    """
    _panel, host, _content = owner()
    window = host.pop_out()

    assert window.windowFlags() & Qt.WindowType.WindowMaximizeButtonHint
    assert window.windowFlags() & Qt.WindowType.WindowMinimizeButtonHint
    assert window.isSizeGripEnabled()


@pytest.mark.parametrize(
    "want, screen, expected",
    [
        ((960, 720), (1920, 1032), (960, 720)),      # room to spare
        ((960, 720), (1366, 768), (960, 706)),       # height clamped
        ((960, 720), (800, 600), (760, 552)),        # both clamped
    ],
)
def test_the_window_opens_no_larger_than_the_screen(want, screen, expected):
    """Asserted on the PURE function, never through the window.

    `offscreen` reports an 800x800 screen, so through a real window the
    clamp always bites and calling it is indistinguishable from deleting
    the call. Deleting the CALL is therefore the one mutation nothing
    here catches, and that is written down rather than papered over --
    exactly as `initial_right_dock_width` already records.
    """
    assert fit_within(*want, *screen) == expected


def test_the_detached_view_gets_more_height_than_the_docked_one(qapp):
    """THE REASON THE FEATURE EXISTS, as an assertion.

    Everything else here is lifecycle correctness, and a mechanism can be
    lifecycle-perfect while giving the picture no more room at all.

    The claim is the DELTA, which is what the feature changes. The setup
    assertion is what stops it passing vacuously: if a future fixture
    stops reproducing the squeeze, this fails on its own setup and says
    so rather than quietly measuring nothing.

    BOTH WIDGETS ARE SHOWN. An unshown widget never runs `resizeEvent`
    and `resize()` is clamped to its minimum, so the obvious version of
    this test measures the constructor instead of the layout.
    """
    panel = QWidget()
    panel_layout = QVBoxLayout(panel)
    # Stand-ins for the settings box and the result table, which are what
    # actually squeeze the viewer in the real panel.
    for height in (220, 160):
        filler = QLabel("", panel)
        filler.setFixedHeight(height)
        panel_layout.addWidget(filler)

    content = QLabel("view")
    host = PopOutHost(content, title="Test view", parent=panel)
    panel_layout.addWidget(host, 1)
    panel.resize(420, 480)
    panel.show()
    qapp.processEvents()

    docked_height = content.height()
    assert docked_height < 150, (
        f"the fixture no longer reproduces the squeeze this feature exists for "
        f"(docked view is {docked_height} px). The delta below proves nothing "
        f"without it."
    )

    window = host.pop_out()
    window.show()
    qapp.processEvents()
    detached_height = content.height()

    assert detached_height > docked_height, (
        f"detached {detached_height} px is no better than docked {docked_height} px"
    )

    host.return_home()
    _dispose(panel)


# --- contracts --------------------------------------------------------------


def test_a_pop_out_placeholder_is_not_mistaken_for_an_empty_state(owner):
    """A real collision, not a hypothetical one.

    `QuantumChemistryPanel.empty_message_for_tab` returns the first
    `is_empty_state` widget it finds anywhere under a tab. Building this
    placeholder with `empty_state()` -- which is the helper whose NAME
    sounds right -- would put a hidden marked label inside every host, and
    the tab would start answering for itself with the pop-out's message.
    """
    _panel, host, _content = owner()
    placeholders = [w for w in host.findChildren(QLabel) if is_empty_state(w)]
    assert placeholders == []


def test_a_pop_out_placeholder_is_not_a_documentable_control(owner):
    """A CHANGE DETECTOR, and labelled as one.

    True by construction today: a `QLabel` is not in
    `tooltip_inventory._INTERACTIVE`. It is asserted so that swapping the
    placeholder for something interactive is a decision somebody makes on
    purpose, with a contract, rather than a silent addition to every
    host in the application at once.
    """
    _panel, host, _content = owner()
    controls = list(iter_documentable_controls(host))
    assert [c.widget_class for c in controls] == ["QToolButton"]


def test_the_pop_out_window_defines_exactly_one_control_of_its_own(qapp):
    """What keeps this window from quietly growing a control surface.

    An earlier draft argued a pure container needed no dialog-inventory
    fixture. That stopped being true the moment it gained a Return to
    panel button, and an unregistered dialog's contracts are unguarded --
    the exact mutation the dialog blanket exists to catch.
    """
    host = PopOutHost(QLabel("content"), title="Pop-out")
    window = host.pop_out()

    controls = list(iter_documentable_controls(window))
    assert len(controls) == 1, [c.instance_path for c in controls]
    (control,) = controls
    assert control.status == "tooltip"
    assert control.help_tooltip.help_id == "workspace.return_view_to_panel"

    host.return_home()
    _dispose(host)


def test_the_two_contracts_are_different_concepts(qapp):
    """One `help_id` means exactly one thing.

    The pop-out button and the Return button are adjacent enough that a
    later pass might collapse them; they are opposite actions and their
    texts must not be byte-identical, which is what
    `test_one_concept_is_not_split_across_many_help_ids` reads.

    NOTE WHAT THE WALK DOES HERE, because it caught the first version of
    this test out: the window is parented to the HOST, so a walk of the
    host reaches into the open window and finds BOTH buttons. That is the
    same parenting that makes `DISPOSING` a cascade, seen from the
    documentation side -- and it is why the coverage guard, which builds a
    window that never pops anything out, sees only the panel-side button.
    """
    host = PopOutHost(QLabel("content"), title="Pop-out")
    host.pop_out()

    by_id = {
        control.help_tooltip.help_id: control.help_tooltip
        for control in iter_documentable_controls(host)
        if control.help_tooltip
    }
    assert set(by_id) == {"workspace.pop_out_view", "workspace.return_view_to_panel"}
    assert (
        by_id["workspace.pop_out_view"].text != by_id["workspace.return_view_to_panel"].text
    )

    host.return_home()
    _dispose(host)


def test_the_button_says_which_state_it_is_in_without_changing_its_contract(owner):
    """The CHECKED state and the accessible name move. The glyph and the
    tooltip do not, and both halves were paid for.

    THE STATE IS NOT CARRIED BY A SECOND GLYPH, because the first version
    used one -- U+2B1C WHITE LARGE SQUARE -- and every test in this file
    passed while a magnified screenshot of the running application showed
    a lavender emoji square in the panel chrome. `setChecked` is drawn by
    the platform style and cannot be missing from a font.

    THE TOOLTIP IS FIXED, because a state-dependent one is the
    `docking.derive_box_from_ligand` case: the live string then has to be
    asserted to still CONTAIN its contract, or the coverage guard reports
    the control documented while the user reads something else.
    """
    _panel, host, _content = owner()
    (button,) = [c.target for c in iter_documentable_controls(host)]

    docked_name = button.accessibleName()
    docked_glyph = button.text()
    docked_tip = button.toolTip()
    assert not button.isChecked()

    host.pop_out()
    assert button.isChecked()
    assert button.accessibleName() != docked_name
    assert button.text() == docked_glyph, "the glyph must not depend on the state"
    assert button.toolTip() == docked_tip

    host.return_home()
    assert not button.isChecked()
    assert button.accessibleName() == docked_name


def test_raising_an_open_window_leaves_the_button_telling_the_truth(owner):
    """Qt toggles a checkable button on click BEFORE the handler runs.

    A second press only raises the window that is already open, so
    without `_sync_button` on that path the button would be drawn
    un-checked while the view is still detached.
    """
    _panel, host, _content = owner()
    (button,) = [c.target for c in iter_documentable_controls(host)]
    host.pop_out()

    button.click()  # raises the existing window; does not return it

    assert host.is_popped_out()
    assert button.isChecked(), "the button stopped agreeing with the state"
    host.return_home()


# --- remembering where the window was left ---------------------------------


class _FakeSettings:
    """Just the two methods `PopOutHost` uses, so these tests need no
    `QSettings` and cannot touch the machine's real store."""

    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value) -> None:
        self.values[key] = value


def test_the_settings_key_comes_from_the_id_and_not_the_title(qapp):
    """PERSISTENT IDENTITY IS NOT PRESENTATION TEXT.

    A title can be reworded, translated, or collide -- two panels could
    each call a view "Preview". Keying storage on it means a rename
    silently discards somebody's saved geometry with nothing to say why.

    Exactly the line `HelpTooltip.help_id` already draws against
    `instance_path`, one layer up.
    """
    settings = _FakeSettings()
    host = PopOutHost(
        QLabel("content"),
        title="3D Alignment",
        settings_id="alignment.overlay",
        settings=settings,
    )
    assert host.geometry_key() == "ui/popout/alignment.overlay/geometry"

    renamed = PopOutHost(
        QLabel("content"),
        title="Something Else Entirely",
        settings_id="alignment.overlay",
        settings=settings,
    )
    assert renamed.geometry_key() == host.geometry_key(), (
        "renaming the window moved its saved geometry"
    )
    _dispose(host)
    _dispose(renamed)


def test_a_host_with_no_settings_persists_nothing_and_still_opens(qapp):
    """A panel with no `Settings` to hand is a real configuration.

    It degrades to `_PREFERRED_SIZE` rather than raising -- and because
    the keys are new on every install, a missing value can never restore
    something stale. That is why this needed no `_LAYOUT_VERSION` bump.
    """
    host = PopOutHost(QLabel("content"), title="No settings")
    assert host.geometry_key() is None
    window = host.pop_out()
    assert window.isVisible() or window.size().isValid()
    host.return_home()
    _dispose(host)


def test_the_window_reopens_where_it_was_left(qapp):
    settings = _FakeSettings()
    host = PopOutHost(
        QLabel("content"), title="View", settings_id="test.view", settings=settings
    )

    window = host.pop_out()
    window.resize(640, 480)
    qapp.processEvents()
    host.return_home()

    assert settings.values, "closing the window stored nothing"

    reopened = host.pop_out()
    qapp.processEvents()
    assert abs(reopened.width() - 640) <= 40 and abs(reopened.height() - 480) <= 40, (
        f"reopened at {reopened.width()}x{reopened.height()}, not near 640x480"
    )
    host.return_home()
    _dispose(host)


def test_a_geometry_saved_on_a_bigger_screen_is_clamped_to_this_one(qapp):
    """RESTORE THEN FIT, and this is the assertion that pins the order.

    The obvious order -- fit, then restore -- lets the restore overwrite
    the clamp. Measured on a real display: a saved 1924x1061 came back as
    1918x999 against a 1920x1032 screen, i.e. flush to every edge, which
    is the case `_SCREEN_FRACTION` exists to prevent. Restore-then-fit
    gives 1824x949.

    Asserted against `fit_within` rather than a pixel count, because
    `offscreen` reports an 800x800 screen and any absolute number here
    would be a statement about the platform.
    """
    settings = _FakeSettings()
    host = PopOutHost(
        QLabel("content"), title="View", settings_id="test.view", settings=settings
    )

    donor = host.pop_out()
    donor.resize(4000, 3000)  # larger than any screen the suite runs on
    qapp.processEvents()
    host.return_home()

    reopened = host.pop_out()
    qapp.processEvents()
    screen = QGuiApplication.primaryScreen()
    available = screen.availableGeometry()
    ceiling = fit_within(
        available.width(), available.height(), available.width(), available.height()
    )
    assert reopened.width() <= ceiling[0] and reopened.height() <= ceiling[1], (
        f"reopened at {reopened.width()}x{reopened.height()}, past the "
        f"{ceiling} this screen allows -- the restore overwrote the clamp"
    )
    host.return_home()
    _dispose(host)
