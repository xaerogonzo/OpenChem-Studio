from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QComboBox, QSpinBox

from openchem.ui.widgets.scroll_safe import ScrollSafeFilter, make_scroll_safe


class _FakeWheelEvent:
    """Only what `ScrollSafeFilter.eventFilter` reads or calls -- `type()`,
    `ignore()`, `isAccepted()` -- constructed directly rather than through a
    real `QWheelEvent`, the same approach already used for
    `NmrCorrelationPlotWidget` and `Mol3DViewerBackend`'s own filter: the
    filter is called directly here, never through Qt's own dispatch, so the
    event only needs to answer what it is asked."""

    def __init__(self, event_type=QEvent.Type.Wheel) -> None:
        self._type = event_type
        self._accepted = True  # Qt's own default before a handler runs

    def type(self):
        return self._type

    def angleDelta(self):
        return QPoint(0, -120)

    def ignore(self) -> None:
        self._accepted = False

    def accept(self) -> None:
        self._accepted = True

    def isAccepted(self) -> bool:  # noqa: N802 - Qt naming
        return self._accepted


class _FakeControl:
    """Stands in for a `QComboBox`/`QSpinBox` -- only `hasFocus()` is read."""

    def __init__(self, focused: bool = False) -> None:
        self._focused = focused

    def hasFocus(self) -> bool:
        return self._focused


def test_an_unfocused_control_has_its_wheel_event_ignored_and_consumed(qapp):
    control = _FakeControl(focused=False)
    event = _FakeWheelEvent()

    consumed = ScrollSafeFilter().eventFilter(control, event)

    assert consumed is True, "an unfocused control must not let its own wheelEvent run"
    assert event.isAccepted() is False, "ignore() must be called so Qt can propagate it onward"


def test_a_focused_control_lets_the_wheel_event_through(qapp):
    control = _FakeControl(focused=True)
    event = _FakeWheelEvent()

    consumed = ScrollSafeFilter().eventFilter(control, event)

    assert consumed is False, "a control the user has clicked into must still respond to the wheel"
    assert event.isAccepted() is True, "untouched -- the filter must not call ignore() when passing through"


def test_non_wheel_events_are_left_alone(qapp):
    control = _FakeControl(focused=False)
    event = _FakeWheelEvent(event_type=QEvent.Type.MouseMove)

    assert ScrollSafeFilter().eventFilter(control, event) is False


def test_make_scroll_safe_installs_on_a_real_combo_box(qapp):
    combo = QComboBox()
    combo.addItems(["a", "b", "c"])

    guard = make_scroll_safe(combo)

    assert isinstance(guard, ScrollSafeFilter)
    assert guard.parent() is combo


def test_make_scroll_safe_installs_on_a_real_spin_box(qapp):
    spin = QSpinBox()

    guard = make_scroll_safe(spin)

    assert isinstance(guard, ScrollSafeFilter)
    assert guard.parent() is spin


def test_a_real_unfocused_combo_box_ignores_a_real_wheel_event_without_changing_its_index(qapp):
    """End-to-end through Qt's own dispatch, not a direct call -- the thing
    that actually matters is that `QApplication.sendEvent` to the real,
    unfocused combo box leaves `currentIndex()` untouched, confirming the
    filter genuinely intercepts before `QComboBox.wheelEvent` runs."""
    combo = QComboBox()
    combo.addItems(["a", "b", "c"])
    combo.setCurrentIndex(1)
    make_scroll_safe(combo)
    assert not combo.hasFocus(), "setup: a freshly built, unshown combo box must start unfocused"

    event = QWheelEvent(
        QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(combo, event)

    assert combo.currentIndex() == 1, "the wheel must not have changed the selection"


def test_a_real_unfocused_spin_box_ignores_a_real_wheel_event_without_changing_its_value(qapp):
    """`QSpinBox` itself is where the filter is installed, but a REAL wheel
    event is actually delivered first to its internal `QLineEdit`, which
    ignores it, and Qt's own native propagation-to-parent-on-ignore is what
    carries it to the `QSpinBox` next -- `QApplication.sendEvent` to a
    single widget does not reproduce that native hop (confirmed live with
    `OPENCHEM_DRIVE`'s `wheel` step: sending to the line edit alone left
    the spin box's value untouched in BOTH the focused and unfocused case,
    which proved nothing about this filter). Sending straight to the
    `QSpinBox` itself is what actually exercises the filter installed on
    it, which is the same thing the native propagation hop would hand it."""
    spin = QSpinBox()
    spin.setRange(-10, 10)
    spin.setValue(0)
    make_scroll_safe(spin)
    assert not spin.hasFocus(), "setup: a freshly built, unshown spin box must start unfocused"

    event = QWheelEvent(
        QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(spin, event)

    assert spin.value() == 0, "the wheel must not have changed the value"


def test_a_real_focused_spin_box_still_responds_to_the_wheel(qapp):
    """The other half of the contract: a spin box the user has clicked into
    must keep working exactly as it always did."""
    spin = QSpinBox()
    spin.setRange(-10, 10)
    spin.setValue(0)
    make_scroll_safe(spin)
    spin.show()
    spin.setFocus()
    qapp.processEvents()
    assert spin.hasFocus(), "setup: a shown, explicitly focused spin box must report focus"

    event = QWheelEvent(
        QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(spin, event)

    assert spin.value() == -1, "a focused spin box must still change on a wheel event"
    spin.close()


def test_a_real_unfocused_editable_combo_box_ignores_a_real_wheel_event(qapp):
    """`_method_combo` (`ui/panels/quantum_chemistry_panel.py`) is
    editable, which gives it an internal `QLineEdit` too -- the same
    structural shape as a spin box. Proving this separately rather than
    assuming the plain-combo-box test above covers it."""
    combo = QComboBox()
    combo.setEditable(True)
    combo.addItems(["B3LYP def2-SVP", "PBE0 def2-TZVP", "HF-3c"])
    combo.setCurrentIndex(0)
    make_scroll_safe(combo)
    assert not combo.hasFocus(), "setup: a freshly built, unshown combo box must start unfocused"

    event = QWheelEvent(
        QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(combo, event)

    assert combo.currentIndex() == 0, "the wheel must not have changed the selection"
